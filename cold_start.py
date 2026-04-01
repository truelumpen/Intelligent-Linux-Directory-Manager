"""
One-time cold start scanner.

This script scans the Downloads directory, classifies files by MIME/extension,
and seeds the tracking database with initial file metadata.
"""

# =============================
# Standard library and third-party imports
# =============================
import os
import sqlite3
import magic
import time
import logging
import pwd
from datetime import datetime

# =============================
# Classification configuration
# =============================

# 1) MIME prefix routing (broad media/font detection).
MIME_PREFIXES = {
    'video/': 'Video',
    'audio/': 'Audio',
    'image/': 'Image',
    'font/': 'Font',
}

# 2) Explicit MIME and extension routing.
# Both MIME types and extensions map to the same Target Folder.
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

# Keep logging timestamps aligned with local system time.
logging.Formatter.converter = time.localtime

def get_downloads_dir():
    """Return the Downloads directory for the user owning this script file."""
    script_uid = os.stat(__file__).st_uid
    home_dir = pwd.getpwuid(script_uid).pw_dir
    return os.path.join(home_dir, "Downloads")


# =============================
# Paths and logging setup
# =============================

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = f"{PROJECT_DIR}/download_daemon.log"
DB_PATH = os.path.join(PROJECT_DIR, "file_tracker.db")

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(message)s')


# =============================
# Cold start workflow
# =============================

def main():
    """Populate the tracking database using a one-time Downloads scan."""

    # Phase 1: Ensure the tracking table exists.
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

    # Phase 2: Scan files and derive a folder.
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

                # Step 2a: Route using MIME prefix
                for prefix, cat in MIME_PREFIXES.items():
                    if mime_type.startswith(prefix):
                        category = cat
                        break

                # Step 2b: Route using explicit MIME or extension mappings.
                if not category:
                    for cat_name, criteria in CATEGORY_MAPPING.items():
                        # Match known MIME signatures first.
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
                    # Use ISO format to avoid Python 3.12 datetime deprecation warnings.
                    current_time = datetime.now().isoformat()

                    cursor.execute('''
                        INSERT INTO files (path, filename, size, data)
                        VALUES (?, ?, ?, ?)
                    ''', (formatted_path, filename, file_size, current_time))

                    logging.info(f"Categorized: {filename} -> {category} (via {mime_type})")

            except Exception as e:
                logging.info(f"Error processing {filename}: {e}")

    # Finalize and close the database session.
    conn.commit()
    conn.close()
    logging.info("\nCold start complete.")

if __name__ == "__main__":
    main()
