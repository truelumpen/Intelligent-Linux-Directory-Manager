import time
import sys
import logging
import os
import pwd
import sqlite3
import shutil
import joblib
import magic
from datetime import datetime, timedelta
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ================== Configuration ==================

# [UPDATE: Hansol] Synchronize logging with the local system timezone (e.g., EST)
# This ensures timestamps match the actual time the user sees.
logging.Formatter.converter = time.localtime

def get_real_user_info():
    """[UPDATE: Hansol] Dynamically find the real user even when run via sudo."""
    try:
        script_stat = os.stat(__file__)
        user_info = pwd.getpwuid(script_stat.st_uid)
        return user_info.pw_name, user_info.pw_dir
    except Exception:
        return os.getlogin(), os.path.expanduser("~")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
REAL_USER, USER_HOME = get_real_user_info()
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")

LOG_FILE = f"{PROJECT_DIR}/download_daemon.log"
TXT_LOG = f"{PROJECT_DIR}/downloads.txt"
DB_PATH = os.path.join(PROJECT_DIR, "file_tracker.db")
MODEL_PATH = os.path.join(PROJECT_DIR, "file_classifier.pkl")
VECTORIZER_PATH = os.path.join(PROJECT_DIR, "vectorizer.pkl")

TEMP_EXTENSIONS = {'.part', '.crdownload', '.tmp', '.download'}

# [UPDATE: Hansol] Standardized logging format with local timestamps
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(message)s')

def init_db():
    """Initializes the SQLite tracker for file lifecycle management."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS tracked_files (id INTEGER PRIMARY KEY, path TEXT, date TIMESTAMP)")

def cleanup_expired_files():
    """[UPDATE: Hansol] Automated 2-hour retention policy (Test Mode)."""
    limit = datetime.now() - timedelta(hours=2) 
    with sqlite3.connect(DB_PATH) as conn:
        expired = conn.execute("SELECT id, path FROM tracked_files WHERE date < ?", (limit,)).fetchall()
        for fid, fpath in expired:
            if os.path.exists(fpath):
                os.remove(fpath)
                logging.info(f"Cleanup: Deleted expired file {fpath}")
            conn.execute("DELETE FROM tracked_files WHERE id = ?", (fid,))

# ================== Event Handler ==================

class DownloadHandler(FileSystemEventHandler):
    def __init__(self):
        # [UPDATE: Hansol] Load AI engine into memory at startup
        self.model = joblib.load(MODEL_PATH)
        self.vectorizer = joblib.load(VECTORIZER_PATH)
        init_db()

    def on_created(self, event):
        if event.is_directory: return
        filepath = Path(event.src_path)
        if filepath.suffix in TEMP_EXTENSIONS: return
        
        time.sleep(1) # Allow for complete file write
        self.process_file(filepath)

    def process_file(self, filepath):
        """Leader's flow + Hansol's AI movement logic."""
        try:
            filename = filepath.name
            mime = magic.from_file(str(filepath), mime=True)
            
            # [UPDATE: Hansol] Local AI Classification
            vec = self.vectorizer.transform([filename])
            category = self.model.predict(vec)[0]
            
            # [UPDATE: Hansol] Dynamic destination based on real user home
            target_dir = os.path.join(USER_HOME, category)
            if not os.path.exists(target_dir): 
                os.makedirs(target_dir)
            
            dest_path = os.path.join(target_dir, filename)
            shutil.move(str(filepath), dest_path)

            # Record in DB for the 2-hour retention task
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("INSERT INTO tracked_files (path, date) VALUES (?, ?)", (dest_path, datetime.now()))

            # [UPDATE: Hansol] Log with explicit local time format
            log_time = time.strftime('%Y-%m-%d %H:%M:%S')
            log_entry = f"Processed: {filename} ({mime}) -> {category}"
            logging.info(log_entry)
            
            with open(TXT_LOG, 'a') as f:
                f.write(f"{log_time} - {log_entry}\n")

        except Exception as e:
            logging.error(f"Error processing {filepath}: {e}")

def main():
    logging.info(f"Daemon started for user: {REAL_USER} (Timezone: Local)")
    event_handler = DownloadHandler()
    observer = Observer()
    observer.schedule(event_handler, DOWNLOADS_DIR, recursive=False)
    observer.start()
    
    try:
        while True:
            # Check for expired files every 10 minutes
            cleanup_expired_files()
            time.sleep(600) 
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Daemon stopped.")
        sys.exit(0)
