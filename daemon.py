import time
import sys
import logging
import os
import pwd
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import magic

# The script is run from sudo, but we need the login user's Downloads folder
def get_downloads_dir():
    # Get the UID of the script file's owner
    script_uid = os.stat(__file__).st_uid
    # Get the home directory of that user
    home_dir = pwd.getpwuid(script_uid).pw_dir
    return os.path.join(home_dir, "Downloads")

# ================== Configuration ==================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__)) # Directory for this project
DOWNLOADS_DIR = get_downloads_dir() # Find Downloads Path
LOG_FILE = f"{PROJECT_DIR}/download_daemon.log" # Python logging file
TXT_LOG = f"{PROJECT_DIR}/downloads.txt"        # Plain text log file

# Extensions of temporary/incomplete files to ignore
TEMP_EXTENSIONS = {'.part', '.crdownload', '.tmp', '.download'}

# Set up Python logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(message)s')

# ================== Event Handler ==================
class DownloadHandler(FileSystemEventHandler):
    """Handles file creation events in the Downloads folder."""
    def on_created(self, event):
        """Triggered when a file is created."""
        if event.is_directory:
            return                      # Ignore directories
        filepath = Path(event.src_path)
        if filepath.suffix in TEMP_EXTENSIONS:
            return                      # Ignore temporary files

        # Allow a short time for the file to be completely written
        time.sleep(1)
        self.process_file(filepath)

    def process_file(self, filepath):
        """Extract info, log it, and append to text file."""
        try:
            filename = filepath.name
            mime = magic.from_file(str(filepath), mime=True)  # Detect MIME type
            log_entry = f"Downloaded: {filename} | MIME: {mime}"
            logging.info(log_entry)                           # Python logging

            with open(TXT_LOG, 'a') as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {log_entry}\n")
        except Exception as e:
            logging.error(f"Error processing {filepath}: {e}")

def main():
    logging.info("Daemon started")

    """Start the file system observer and keep it running."""
    event_handler = DownloadHandler()
    observer = Observer()
    observer.schedule(event_handler, DOWNLOADS_DIR, recursive=False)
    observer.start()


    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Daemon stopped by user.")
        sys.exit(0)
