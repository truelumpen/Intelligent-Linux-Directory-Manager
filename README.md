Intelligent Linux Directory Manager

*----------
FOR UBUNTU USERS
if you do not have python3-venv installed, you can do it with:
`sudo apt install python3-venv`

QuickStart
`sudo python main.py`

The daemon does the job with no external interraction needed. You can modify the settings in config.py
The output logs in .log file, created automatically.


This repo is a Python project intended to run on Linux. It watches your `~/Downloads` folder and logs new downloads, and it has a one-time “cold start” that creates category folders + captures metadata for existing files.

The primary entry point is [main.py](main.py), which:
- Creates a Python virtual environment under `.venv/`
- Installs Python dependencies (scikit-learn, watchdog, python-magic, joblib, pandas)
- Ensures `libmagic` is available (needed by `python-magic`)
- Runs the cold start script
- Installs + enables a `systemd` service to run the daemon in the background

## How to run (recommended: real Linux with systemd)

Prereqs:
- Linux with `systemd` (Ubuntu/Debian/Arch)
- Python 3 (with `venv` support)
- `sudo` access (because it writes a system service into `/etc/systemd/system/`)

From the project directory:

1) Run the installer/launcher:

`sudo python3 main.py`

2) Check status/logs:

`systemctl status sorty-daemon`

Log files are created in the project folder:
- `download_daemon.log`
- `downloads.txt`

Cold start artifacts are also written in the project folder:
- `.cold_start_done`
- `existing_files.json`

## How to run without systemd (dev mode)

If you don’t have systemd (or don’t want to install a service), you can run the scripts directly:

1) Create and activate a venv:

`python3 -m venv .venv`
`source .venv/bin/activate`

2) Install deps:

`pip install scikit-learn watchdog python-magic joblib pandas`

3) Run cold start once:

`python3 cold_start.py`

4) Start the watcher (foreground):

`python3 daemon.py`

Stop with Ctrl+C.

## Running on Windows

This project uses Linux-specific features (`systemd`, the `pwd` module, and `libmagic`), so it won’t run natively on Windows.

Options:
- Use WSL2 (Ubuntu) and run in “dev mode” above. (Systemd in WSL may require extra setup depending on your Windows/WSL version.)
- Use a Linux VM or a real Linux machine.
