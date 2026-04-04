# =============================
# Standard library imports
# =============================

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
# File‑open monitoring using inotify_simple
# =============================

def schedule_watch_directory(path):
    """Thread‑safe request to watch a directory and its subdirectories."""
    watch_queue.put(path)

def start_open_monitor(initial_dirs, stop_event):
    """
    Watch given directories recursively for file open events.
    Dynamically adds new directories from watch_queue.
    """
    inotify = INotify()
    watch_descriptors = {}

    def add_watch_recursively(path):
        """Add watch for IN_OPEN on path and all subdirs, skip if already watched."""
        with watched_dirs_lock:
            if path in watched_dirs:
                return
            watched_dirs.add(path)
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

    logging.info(f"Open monitoring active on {watched_dirs}")

    while not stop_event.is_set():
        # Process any pending watch requests
        try:
            while True:
                new_dir = watch_queue.get_nowait()
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
