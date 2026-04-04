"""
Project: Intelligent Linux Directory Manager
Course: CMSC 495
Team Members: Elisei Khmelev, Han Kim, Kenneth Murray, Robert Wells, and Saad Ahmad

File: cold_start.py

Description:
This script performs the initial “cold start” process by scanning the user's
Downloads directory and organizing existing files into categorized folders.
It determines file categories using MIME types, file extensions, and a fallback
machine learning model when needed. The script also logs activity and stores
file metadata in a SQLite database for tracking and future reference.
"""

# =============================
# Imports from local config
# =============================

from config import *

# =============================
# Logging configuration ?? Can it be in config?
# =============================

# Keep logging timestamps aligned with local system time.
logging.Formatter.converter = time.localtime

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
        created_at TIMESTAMP,
        last_accessed TIMESTAMP
    )
    ''')
    conn.commit()

    fmagic = magic.Magic(mime=True)

    # Phase 2: Scan files and derive a folder.
    with os.scandir(DOWNLOADS_DIR) as entries:
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

                file_size = entry.stat().st_size
                # Use ISO format to avoid Python 3.12 datetime deprecation warnings.
                now = datetime.now().isoformat()

                # PHASE 3: Database Insertion
                if not category:

                    # Use AI prediction as a last resort
                    model = joblib.load(MODEL_PATH)
                    vectorizer = joblib.load(VECTORIZER_PATH)

                    vec = vectorizer.transform([filename])
                    category = model.predict(vec)[0]

                # Create a directory for the category if doesn't exist
                target_dir = os.path.join(USER_HOME, category)
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)

                cursor.execute(''' INSERT INTO files (path, filename, size, created_at, last_accessed) VALUES (?, ?, ?, ?, ?) ''', (target_dir, filename, file_size, now, now))

                # Move the file into the right category folder
                dest_path = os.path.join(target_dir, filename)
                shutil.move(str(filepath), dest_path)

                logging.info(f"Categorized: {filename} -> {category}")

            except Exception as e:
                logging.info(f"Error processing {filename}: {e}")

    # Finalize and close the database session.
    conn.commit()
    conn.close()
    logging.info("\nCold start complete.")

if __name__ == "__main__":
    main()
