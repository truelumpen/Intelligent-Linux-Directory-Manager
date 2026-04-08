#!/usr/bin/env python3
"""
Project: Intelligent Linux Directory Manager
Course: CMSC 495
Team Members: Elisei Khmelev, Han Kim, Kenneth Murray, Robert Wells, and Saad Ahmad

File: main.py

Description:
This script serves as the main entry point for the Intelligent Linux Directory Manager.
It initializes the application by creating a virtual environment, installing required
dependencies (including libmagic and Python packages), and running the cold start setup.
Additionally, it configures, enables, and starts a systemd service that runs the file
management daemon in the background for continuous monitoring and organization.
"""

# =============================
# Standard library imports
# =============================
import subprocess
import sys
import os
import shutil
import pwd
from pathlib import Path

# =============================
# Configuration constants
# =============================

# NOTE:
# The dictionary currently maps package names to import names. The values are
# informational and can be used for future import validation/reporting.
# [UPDATE: Hansol] Added 'joblib' and 'pandas' for AI model inference.
PACKAGES = {
    "scikit-learn": "sklearn",
    "watchdog": "watchdog",
    "python-magic": "python-magic",
    "joblib": "joblib",
    "pandas": "pandas",
    "send2trash": "send2trash",
    "inotify_simple": "inotify_simple"
}
SERVICE_NAME = "sorty-daemon"
SERVICE_FILE = f"/etc/systemd/system/{SERVICE_NAME}.service"
VENV_DIR = ".venv"

# =============================
# Setup helpers
# =============================

def get_real_user_info():
    """Resolve the real user account owning this script and its home directory."""
    try:
        script_stat = os.stat(__file__)
        user_info = pwd.getpwuid(script_stat.st_uid)
        return user_info.pw_name, user_info.pw_dir
    except Exception:
        return os.getlogin(), os.path.expanduser("~")

REAL_USER, USER_HOME = get_real_user_info()

def create_virtual_env(project_dir):
    """Create a virtual environment in the project directory."""
    venv_path = os.path.join(project_dir, VENV_DIR)
    print(f"Creating virtual env in {venv_path}...")
    try:
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=True, capture_output=True)
        print(f"✓ Virtual environment created")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed: {e.stderr.decode()}")
        sys.exit(1)
    return venv_path

def install_libmagic():
    """Install the libmagic system library using the detected package manager."""
    print("Checking for libmagic...")

    # Quick check: if the `file` command works, libmagic is available.
    if shutil.which("file") and subprocess.run(["file", "--version"], capture_output=True).returncode == 0:
        print("libmagic appears to be already installed (file command found).")
        return

    # Detect the host package manager and construct the install command.
    if shutil.which("apt-get"):
        cmd = ["apt-get", "install", "-y", "libmagic1"]
        print("Using apt-get to install libmagic...")
    elif shutil.which("yum"):
        cmd = ["yum", "install", "-y", "file-libs"]
        print("Using yum to install libmagic...")
    elif shutil.which("dnf"):
        cmd = ["dnf", "install", "-y", "file-libs"]
        print("Using dnf to install libmagic...")
    elif shutil.which("pacman"):
        cmd = ["pacman", "-S", "--noconfirm", "file"]
        print("Using pacman to install libmagic...")
    else:
        print("Warning: No supported package manager found. libmagic must be installed manually.")
        return

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print("libmagic installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to install libmagic: {e.stderr.decode()}")
        print("You may need to install it manually (e.g., 'apt-get install libmagic1').")

def check_and_install_dependencies(venv_path):
    """Install all Python dependencies into the virtual environment."""
    pip_path = os.path.join(venv_path, "bin", "pip")
    for package in PACKAGES:
        print(f"Installing {package}...")
        try:
            subprocess.run([pip_path, "install", package], check=True, capture_output=True)
            print(f"✓ {package} installed")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install {package}: {e.stderr.decode()}")
            sys.exit(1)

# =============================
# Service registration helpers
# =============================

def write_systemd_service(project_dir, venv_path):
    """Create the systemd service file for the daemon."""
    python_path = os.path.join(venv_path, "bin", "python")
    daemon_path = os.path.join(project_dir, "daemon.py")
    script_stat = os.stat(__file__)
    user_info = pwd.getpwuid(script_stat.st_uid)

    # [UPDATE: Hansol] Clarified service description to highlight AI capabilities.
    service_content = f"""[Unit]
Description=AI-Powered File Manager Daemon
After=network.target

[Service]
Type=simple
User={user_info.pw_name}
WorkingDirectory={project_dir}
ExecStart={python_path} {daemon_path}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    with open(SERVICE_FILE, "w") as f:
        f.write(service_content)
    print(f"✓ Created service file: {SERVICE_FILE}")

def enable_and_start_service():
    """Reload systemd and ensure the daemon is enabled and started."""
    try:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", SERVICE_NAME], check=True)
        subprocess.run(["systemctl", "start", SERVICE_NAME], check=True)
        print(f"✓ Daemon is now active.")
    except subprocess.CalledProcessError as e:
        print(f"✗ Service failed: {e}")
        sys.exit(1)

# =============================
# Main workflow
# =============================

def main():
    """Execute the full bootstrap flow for daemon installation/startup."""
    project_dir = os.path.dirname(os.path.abspath(__file__))

    # 1) Create isolated Python environment and install dependencies.
    venv_path = create_virtual_env(project_dir)
    install_libmagic()
    check_and_install_dependencies(venv_path)

    # 2) Run one-time cold start setup.
    print("Running cold start setup...")
    cold_start_script = os.path.join(project_dir, "cold_start.py")
    python_path = os.path.join(venv_path, "bin", "python")
    try:
        subprocess.run(["sudo", "-u", REAL_USER, python_path, cold_start_script], check=True, capture_output=True, text=True)
        print("Cold start completed.")
    except subprocess.CalledProcessError as e:
        print(f"Cold start failed: {e.stderr}")
        sys.exit(1)

    # 3) Ensure systemd is available before creating and managing the service.
    if (shutil.which("systemctl") is None):
        print("systemd not found")
        sys.exit(1)

    # 4) Register and start daemon service.
    write_systemd_service(project_dir, venv_path)
    enable_and_start_service()


if __name__ == "__main__":
    main()
