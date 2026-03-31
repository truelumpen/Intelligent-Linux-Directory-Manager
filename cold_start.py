import os
import sqlite3
import magic
import time
import logging
import pwd
from datetime import datetime

# --- CONFIGURATION ---
# 1. MIME Prefixes (The "Magic" check)
MIME_PREFIXES = {
    'video/': 'Video',
    'audio/': 'Audio',
    'image/': 'Image',
    'font/': 'Font',
}

# 2. Specific MIME/Extension Mapping (The "Filesamples.com" Structure)
# We map both MIME types and extensions to the same target folder
CATEGORY_MAPPING = {
    'Document': {
        'mimes': ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument', 'application/vnd.oasis.opendocument'],
        'exts': ['.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt']
    },
    'Ebook': {
        'mimes': ['application/epub+zip', 'application/x-mobipocket-ebook'],
        'exts': ['.epub', '.mobi', '.azw3']
    },
    'Code': {
        'mimes': ['text/html', 'application/json', 'application/javascript', 'application/xml', 'text/xml', 'text/csv', 'text/x-python', 'text/x-java'],
        'exts': ['.py', '.java', '.cpp', '.c', '.h', '.js', '.ts', '.html', '.css', '.json', '.xml', '.csv', '.sql', '.sh', '.php']
    }
}

logging.Formatter.converter = time.localtime

def get_downloads_dir():
    """Determine the Downloads folder of the script owner."""
    script_uid = os.stat(__file__).st_uid
    home_dir = pwd.getpwuid(script_uid).pw_dir
    return os.path.join(home_dir, "Downloads")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = f"{PROJECT_DIR}/download_daemon.log"
DB_PATH = os.path.join(PROJECT_DIR, "file_tracker.db")

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(message)s')

def main():

    # --- DB SETUP ---
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT,
            filename TEXT,
            size INTEGER,
            data TIMESTAMP
        )
    ''')
    conn.commit()

    fmagic = magic.Magic(mime=True)

    # --- SCANNING ---
    with os.scandir(get_downloads_dir()) as entries:
        for entry in entries:
            if not entry.is_file():
                continue

            filepath = entry.path
            filename = entry.name
            ext = os.path.splitext(filename)[1].lower()

            try:
                mime_type = fmagic.from_file(filepath)
                category = None

                # PHASE 1: Check MIME Prefixes (Media/Fonts)
                for prefix, cat in MIME_PREFIXES.items():
                    if mime_type.startswith(prefix):
                        category = cat
                        break

                # PHASE 2: Check Specific Mapping (MIME or Extension)
                if not category:
                    for cat_name, criteria in CATEGORY_MAPPING.items():
                        # Check if MIME matches
                        if any(m in mime_type for m in criteria['mimes']):
                            category = cat_name
                            break
                        # Check if Extension matches
                        if ext in criteria['exts']:
                            category = cat_name
                            break

                # PHASE 3: Database Insertion
                if category:
                    formatted_path = f"~/{category}"
                    file_size = entry.stat().st_size
                    # Using isoformat() to fix Python 3.12 DeprecationWarning
                    current_time = datetime.now().isoformat()

                    cursor.execute('''
                        INSERT INTO files (path, filename, size, data)
                        VALUES (?, ?, ?, ?)
                    ''', (formatted_path, filename, file_size, current_time))

                    logging.info(f"Categorized: {filename} -> {category} (via {mime_type})")

            except Exception as e:
                logging.info(f"Error processing {filename}: {e}")

    conn.commit()
    conn.close()
    logging.info("\nCold start complete.")

if __name__ == "__main__":
    main()
