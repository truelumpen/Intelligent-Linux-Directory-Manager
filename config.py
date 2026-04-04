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
import subprocess
from inotify_simple import INotify, flags
from send2trash import send2trash
from datetime import datetime, timedelta
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path

# =============================
# Extension and MIME type rules
# =============================

# 1) MIME prefix routing (broad media/font detection).
MIME_PREFIXES = {
    'video/': 'Videos',
    'audio/': 'Music',
    'image/': 'Pictures',
    'font/': 'Font',
}

# 2) Explicit MIME and extension routing.
# Both MIME types and extensions map to the same Target Folder.
CATEGORY_MAPPING = {
    'Documents': {
        'mimes': ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument', 'application/vnd.oasis.opendocument'],
        'exts': ['.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt']
    },
    'Ebooks': {
        'mimes': ['application/epub+zip', 'application/x-mobipocket-ebook'],
        'exts': ['.epub', '.mobi', '.azw3']
    },
    'Code': {
        'mimes': ['text/html', 'application/json', 'application/javascript', 'application/xml', 'text/xml', 'text/csv', 'text/x-python', 'text/x-java'],
        'exts': ['.py', '.java', '.cpp', '.c', '.h', '.js', '.ts', '.html', '.css', '.json', '.xml', '.csv', '.sql', '.sh', '.php']
    }
}

# =============================
# Supporting functions to resolve paths
# =============================

def get_downloads_dir():
    """Return the Downloads directory for the user owning this script file."""
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

# =============================
# Paths and logging setup
# =============================

REAL_USER, USER_HOME = get_real_user_info()
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = get_downloads_dir()
LOG_FILE = f"{PROJECT_DIR}/download_daemon.log"
DB_PATH = os.path.join(PROJECT_DIR, "file_tracker.db")
MODEL_PATH = os.path.join(PROJECT_DIR, "file_classifier.pkl")
VECTORIZER_PATH = os.path.join(PROJECT_DIR, "vectorizer.pkl")
INACTIVE_DAYS = 1 / (24*60) # change to 3 in PROD
CLEANUP_INTERVAL = 60 # Change to 600 in PROD
TEMP_EXTENSIONS = {'.part', '.crdownload', '.tmp', '.download'}

watch_queue = queue.Queue()
watched_dirs_lock = threading.Lock()
watched_dirs = set()
