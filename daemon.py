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
# Imports from local config
# =============================

from config import *

from watcher import schedule_watch_directory, start_open_monitor

# =============================
# Logging configuration ?? Can it be in config?
# =============================

# Keep logging timestamps aligned with local system time.
logging.Formatter.converter = time.localtime

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
# Open watches once on the directories from the Cold Start
# =============================

def seed_watches_from_db():
    """Add watches for all directories that currently contain tracked files."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Get unique parent directories of all tracked files
            rows = conn.execute(
                "SELECT DISTINCT path FROM files WHERE path IS NOT NULL"
            ).fetchall()
        for (dir_path,) in rows:
            schedule_watch_directory(dir_path)
            logging.info(f"Queued watch for directory: {dir_path}")
    except Exception as e:
        logging.error(f"Failed to start monitors from DB aftert Cold Start: {e}")

# =============================
# Daemon entrypoint
# =============================

def main():
    """Start filesystem monitoring and keep the daemon process alive."""

    logging.info(f"Daemon started")
    event_handler = DownloadHandler()
    observer = Observer()
    observer.schedule(event_handler, DOWNLOADS_DIR, recursive=False)
    observer.start()
    
    seed_watches_from_db()

    # --- Inotify for file‑open events (in a separate thread) ---
    initial_watch_dirs = [DOWNLOADS_DIR] if os.path.isdir(DOWNLOADS_DIR) else []

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
