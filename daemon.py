"""
Project: Intelligent Linux Directory Manager
Course: CMSC 495
Team Members: Elisei Khmelev, Han Kim, Kenneth Murray, Robert Wells, and Saad Ahmad

File: daemon.py

Description:
This script runs as a background daemon that continuously monitors the user's
Downloads directory for new files. It uses a machine learning model to classify
files, moves them into appropriate category folders, and records file metadata
in a SQLite database. The daemon utilizes the watchdog library to detect file
system events in real time and ensures files are fully downloaded before
processing.
"""

# =============================
# Standard library imports
# =============================
import time
import sys
import logging
import os
import pwd
import sqlite3
import shutil
import joblib
import magic
import signal
import threading
import queue
from inotify_simple import INotify, flags
from send2trash import send2trash
from datetime import datetime, timedelta
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# =============================
# Runtime configuration
# =============================

# [UPDATE: Hansol] Synchronize logging with the local system timezone (e.g., EST)
# This ensures timestamps match the actual time the user sees.
logging.Formatter.converter = time.localtime
INACTIVE_DAYS = 1 / (24*60) # change to 3 in PROD
CLEANUP_INTERVAL = 60 # Change to 600 in PROD

def get_downloads_dir():
    """Determine the Downloads folder of the script owner."""
    script_uid = os.stat(__file__).st_uid
    home_dir = pwd.getpwuid(script_uid).pw_dir
    return os.path.join(home_dir, "Downloads")

def get_real_user_info():
    """Resolve the real user account owning this script and its home directory."""
    try:
        script_stat = os.stat(__file__)
        user_info = pwd.getpwuid(script_stat.st_uid)
        return user_info.pw_name, user_info.pw_dir
    except Exception:
        return os.getlogin(), os.path.expanduser("~")

REAL_USER, USER_HOME = get_real_user_info()
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = f"{PROJECT_DIR}/download_daemon.log"
DB_PATH = os.path.join(PROJECT_DIR, "file_tracker.db")
MODEL_PATH = os.path.join(PROJECT_DIR, "file_classifier.pkl")
VECTORIZER_PATH = os.path.join(PROJECT_DIR, "vectorizer.pkl")

TEMP_EXTENSIONS = {'.part', '.crdownload', '.tmp', '.download'}

_watch_queue = queue.Queue()
_watched_dirs_lock = threading.Lock()
_watched_dirs = set()

# [UPDATE: Hansol] Standardized logging format with local timestamps
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(message)s')

# =============================
# Deferred retention policy notes
# =============================

def move_to_trash():
    """Move files not accessed for INACTIVE_DAYS to Trash and remove from DB."""
    now = datetime.now()
    cutoff = now - timedelta(days=INACTIVE_DAYS)
    cutoff_time = cutoff.isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT id, path, filename FROM files WHERE last_accessed < ?", (cutoff_time,)).fetchall()

        for fid, path, filename in rows:
            try:
                if os.path.exists(path):
                    send2trash(path)
                    logging.info(f"Moved to Trash: {filename}")
                # Remove DB entry regardless (file may have been deleted manually)
                conn.execute("DELETE FROM files WHERE id = ?", (fid,))
            except Exception as e:
                logging.error(f"Failed to trash {filename}: {e}")

def is_file_finished(filepath):
    try:
        if os.path.getsize(filepath) == 0:
            return False
        size1 = os.path.getsize(filepath)
        time.sleep(0.5)
        size2 = os.path.getsize(filepath)
        return size1 == size2
    except OSError:
        return False

class DownloadHandler(FileSystemEventHandler):
    """Watchdog event handler for classifying and moving downloaded files."""

    def __init__(self):
        # [UPDATE: Hansol] Load AI engine into memory at startup
        self.model = joblib.load(MODEL_PATH)
        self.vectorizer = joblib.load(VECTORIZER_PATH)

    def on_created(self, event):
        """Handle new file creation events from the Downloads directory."""
        if not event.is_directory: self.handle_event(event.src_path)

    def on_moved(self, event):
        """Catch files renamed by browsers (e.g., .crdownload -> .avi)."""
        if not event.is_directory: self.handle_event(event.dest_path)

    # def on_modified(self, event):
    #     if not event.is_directory:
    #         update_access_time(event.src_path)

    def handle_event(self, src_path):
        """Gate temporary files and process finalized files when ready."""
        filepath = Path(src_path)
        if filepath.suffix.lower() in TEMP_EXTENSIONS: return

        # Try to process the file as soon as it's ready
        for _ in range(10):
            if is_file_finished(str(filepath)):
                self.process_file(filepath)
                break
            time.sleep(1)

    def process_file(self, filepath):
        """Classify, move, and persist metadata for a downloaded file."""

        time.sleep(1)
        if not filepath.exists():
            return

        """Leader's flow + Hansol's AI movement logic."""
        try:
            filename = filepath.name
            mime = magic.from_file(str(filepath), mime=True)
            size = os.path.getsize(filepath)

            """
            Elisei's note: the prediction should be made based on MIME, ext, filename, and size'
            """
            
            # [UPDATE: Hansol] Local AI Classification
            vec = self.vectorizer.transform([filename])
            category = self.model.predict(vec)[0]
            
            # [UPDATE: Hansol] Dynamic destination based on real user home
            target_dir = os.path.join(USER_HOME, category)
            if not os.path.exists(target_dir): 
                os.makedirs(target_dir)
            
            dest_path = os.path.join(target_dir, filename)
            shutil.move(str(filepath), dest_path)
            now = datetime.now().isoformat()

            # Record in DB for the 2-hour retention task
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(''' INSERT INTO files (path, filename, size, created_at, last_accessed) VALUES (?, ?, ?, ?, ?) ''', (dest_path, filename, size, now, now))

            # Add a monitor to track if the file was used
            dest_dir = os.path.dirname(dest_path)
            schedule_watch_directory(dest_dir)

            # [UPDATE: Hansol] Log with explicit local time format
            log_time = time.strftime('%Y-%m-%d %H:%M:%S')
            log_entry = f"Categorized: {filename} -> {category}"
            logging.info(log_entry)
            

        except Exception as e:
            logging.error(f"Error processing {filepath}: {e}")

# =============================
# File‑open monitoring using inotify_simple
# =============================

def schedule_watch_directory(path):
    """Thread‑safe request to watch a directory and its subdirectories."""
    _watch_queue.put(path)

def start_open_monitor(initial_dirs, stop_event):
    """
    Watch given directories recursively for file open events.
    Dynamically adds new directories from _watch_queue.
    """
    inotify = INotify()
    watch_descriptors = {}

    def add_watch_recursively(path):
        """Add watch for IN_OPEN on path and all subdirs, skip if already watched."""
        with _watched_dirs_lock:
            if path in _watched_dirs:
                return
            _watched_dirs.add(path)
        try:
            wd = inotify.add_watch(path, flags.OPEN)
            watch_descriptors[wd] = path
            logging.debug(f"Watching: {path}")
        except Exception as e:
            logging.error(f"Failed to add watch on {path}: {e}")
            return
        # Recurse into subdirectories
        for entry in os.scandir(path):
            if entry.is_dir(follow_symlinks=False):
                add_watch_recursively(entry.path)

    # Initial watches (only Downloads)
    for d in initial_dirs:
        if os.path.isdir(d):
            add_watch_recursively(d)
        else:
            logging.warning(f"Initial watch directory does not exist: {d}")

    logging.info(f"Open monitoring active on {_watched_dirs}")

    while not stop_event.is_set():
        # Process any pending watch requests
        try:
            while True:
                new_dir = _watch_queue.get_nowait()
                if os.path.isdir(new_dir):
                    add_watch_recursively(new_dir)
                else:
                    logging.debug(f"Requested watch on non-existent dir: {new_dir}")
        except queue.Empty:
            pass

        events = inotify.read(timeout=1000)
        for event in events:
            if event.mask & flags.OPEN:
                base_path = watch_descriptors.get(event.wd)
                if base_path:
                    full_path = os.path.join(base_path, event.name)
                    if os.path.isdir(full_path):
                        continue
                    if any(full_path.lower().endswith(ext) for ext in TEMP_EXTENSIONS):
                        continue
                    logging.info(f"FILE OPENED: {full_path}")
                    now = datetime.now().isoformat()
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute(''' UPDATE files SET last_accessed = ? WHERE path = ?;''', (now, full_path))

    inotify.close()
    logging.info("Open monitoring stopped.")


# =============================
# Daemon entrypoint
# =============================

def main():
    """Start filesystem monitoring and keep the daemon process alive."""

    logging.info(f"Daemon started")
    event_handler = DownloadHandler()
    observer = Observer()
    observer.schedule(event_handler, get_downloads_dir(), recursive=False)
    observer.start()
    
    # --- Inotify for file‑open events (in a separate thread) ---
    downloads_dir = get_downloads_dir()
    initial_watch_dirs = [downloads_dir] if os.path.isdir(downloads_dir) else []

    stop_open_event = threading.Event()
    open_thread = threading.Thread(
        target=start_open_monitor,
        args=(initial_watch_dirs, stop_open_event),
        daemon=True
    )
    open_thread.start()

    # --- Signal handlers for clean shutdown ---
    def shutdown(signum, frame):
        logging.info(f"Received signal {signum}, shutting down...")
        observer.stop()
        if open_thread is not None:
            stop_open_event.set()
            open_thread.join(timeout=2)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)   # Ctrl+C also works

    # --- Main loop (retention cleanup every CLEANUP_INTERVAL seconds) ---
    try:
        last_cleanup = 0
        while True:
            now = time.time()
            if now - last_cleanup > CLEANUP_INTERVAL:
                move_to_trash()
                last_cleanup = now
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown(None, None)
    finally:
        observer.join()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Daemon stopped.")
        sys.exit(0)
