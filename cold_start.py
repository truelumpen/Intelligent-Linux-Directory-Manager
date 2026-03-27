#!/usr/bin/env python3
"""
One-time setup for the file sorting daemon.
- Creates category folders in the Downloads directory.
- Scans existing files in Downloads and records their metadata (name, size, MIME type).
"""

import os
import sys
import json
import time
import logging
import pwd
import grp
import datetime
from pathlib import Path
import magic

# Configuration
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
MARKER_FILE = os.path.join(PROJECT_DIR, ".cold_start_done")
EXISTING_FILES_JSON = os.path.join(PROJECT_DIR, "existing_files.json")
CATEGORIES = ["PDFs", "Docs", "Spreadsheets", "Presentations", "Archives", "Videos", "Others"]
TEMP_EXTENSIONS = {'.part', '.crdownload', '.tmp', '.download'}

# Reuse the same function as in daemon.py
def get_downloads_dir():
    """Determine the Downloads folder of the script owner."""
    script_uid = os.stat(__file__).st_uid
    home_dir = pwd.getpwuid(script_uid).pw_dir
    return os.path.join(home_dir, "Downloads")

def create_folders(base_dir):
    """Create category folders inside base_dir if they don't exist."""
    for cat in CATEGORIES:
        folder_path = os.path.join(base_dir, cat)
        os.makedirs(folder_path, exist_ok=True)
        print(f"Created folder: {folder_path}")

def gather_existing_files(downloads_dir):
    """Scan only top-level files in downloads_dir, collect metadata."""
    files_info = []
    try:
        with os.scandir(downloads_dir) as entries:
            for entry in entries:
                # Skip directories (including category folders)
                if not entry.is_file():
                    continue
                filepath = entry.path
                file = entry.name
                # Skip temporary files
                ext = os.path.splitext(file)[1].lower()
                if ext in TEMP_EXTENSIONS:
                    continue

                try:
                    stat = entry.stat()
                    size = stat.st_size
                    mime = magic.from_file(filepath, mime=True)

                    files_info.append({
                        "name": file,
                        "size": size,
                        "mime": mime
                    })
                except Exception as e:
                    print(f"Error processing {filepath}: {e}")
    except OSError as e:
        print(f"Error scanning directory {downloads_dir}: {e}")

    with open(EXISTING_FILES_JSON, 'w') as f:
        json.dump(files_info, f, indent=2)
    print(f"Saved metadata for {len(files_info)} files to {EXISTING_FILES_JSON}")

def main():
    # Check if already done
    if os.path.exists(MARKER_FILE):
        print("Cold start already performed. Exiting.")
        return

    downloads = get_downloads_dir()
    if not os.path.isdir(downloads):
        print(f"Downloads directory not found: {downloads}")
        sys.exit(1)

    print("Creating category folders...")
    create_folders(downloads)

    print("Gathering existing file metadata...")
    gather_existing_files(downloads)

    # Mark as done
    with open(MARKER_FILE, 'w') as f:
        f.write("Cold start completed on " + time.strftime("%Y-%m-%d %H:%M:%S"))
    print("Cold start completed.")

if __name__ == "__main__":
    main()
