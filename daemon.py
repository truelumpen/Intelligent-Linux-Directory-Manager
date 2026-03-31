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

def get_downloads_dir():
    """Determine the Downloads folder of the script owner."""
    script_uid = os.stat(__file__).st_uid
    home_dir = pwd.getpwuid(script_uid).pw_dir
    return os.path.join(home_dir, "Downloads")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = f"{PROJECT_DIR}/download_daemon.log"
DB_PATH = os.path.join(PROJECT_DIR, "file_tracker.db")
MODEL_PATH = os.path.join(PROJECT_DIR, "file_classifier.pkl")
VECTORIZER_PATH = os.path.join(PROJECT_DIR, "vectorizer.pkl")

TEMP_EXTENSIONS = {'.part', '.crdownload', '.tmp', '.download'}

# [UPDATE: Hansol] Standardized logging format with local timestamps
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(message)s')


"""
Elisei's note: potential change to just notofying the user that they
didn't use that file instead of deleting it
"""
# def cleanup_expired_files():
#     """[UPDATE: Hansol] Automated 2-hour retention policy (Test Mode)."""
#     limit = datetime.now() - timedelta(hours=2)
#     with sqlite3.connect(DB_PATH) as conn:
#         expired = conn.execute("SELECT id, path FROM tracked_files WHERE date < ?", (limit.isoformat(),)).fetchall()
#         for fid, fpath in expired:
#             if os.path.exists(fpath):
#                 os.remove(fpath)
#                 logging.info(f"Cleanup: Deleted expired file {fpath}")
#             conn.execute("DELETE FROM tracked_files WHERE id = ?", (fid,))

# ================== Event Handler ==================

class DownloadHandler(FileSystemEventHandler):
    def __init__(self):
        # [UPDATE: Hansol] Load AI engine into memory at startup
        self.model = joblib.load(MODEL_PATH)
        self.vectorizer = joblib.load(VECTORIZER_PATH)

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

            # Record in DB for the 2-hour retention task
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (dest_path, filename, size, datetime.now()))

            # [UPDATE: Hansol] Log with explicit local time format
            log_time = time.strftime('%Y-%m-%d %H:%M:%S')
            log_entry = f"Categorized: {filename} ({mime}) -> {category}"
            logging.info(log_entry)
            

        except Exception as e:
            logging.error(f"Error processing {filepath}: {e}")



def main():

    logging.info(f"Daemon started")
    event_handler = DownloadHandler()
    observer = Observer()
    observer.schedule(event_handler, get_downloads_dir(), recursive=False)
    observer.start()
    
    try:
        while True:
            # Check for expired files every 10 minutes
            # cleanup_expired_files()
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Daemon stopped.")
        sys.exit(0)
