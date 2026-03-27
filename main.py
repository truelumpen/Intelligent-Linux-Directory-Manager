#!/usr/bin/env python3
"""
Main entry point for the daemon.
Installs dependencies and starts the daemon in the background.
"""
import subprocess
import sys
import os
import shutil
from pathlib import Path

# Map package names to their import names
# [UPDATE: Hansol] Added 'joblib' and 'pandas' for AI model inference.
PACKAGES = {
    "scikit-learn": "sklearn",
    "watchdog": "watchdog",
    "python-magic": "python-magic",
    "joblib": "joblib",
    "pandas": "pandas"
}
SERVICE_NAME = "sorty-daemon"
SERVICE_FILE = f"/etc/systemd/system/{SERVICE_NAME}.service"
VENV_DIR = ".venv"

def create_virtual_env(project_dir):
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
    """Install libmagic system library using available package manager."""
    print("Checking for libmagic...")

    # Quick check: see if 'file' command exists and works
    if shutil.which("file") and subprocess.run(["file", "--version"], capture_output=True).returncode == 0:
        print("libmagic appears to be already installed (file command found).")
        return

    # Determine package manager
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
    pip_path = os.path.join(venv_path, "bin", "pip")
    for package in PACKAGES:
        print(f"Installing {package}...")
        try:
            subprocess.run([pip_path, "install", package], check=True, capture_output=True)
            print(f"✓ {package} installed")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install {package}: {e.stderr.decode()}")
            sys.exit(1)

def write_systemd_service(project_dir, venv_path):
    python_path = os.path.join(venv_path, "bin", "python")
    daemon_path = os.path.join(project_dir, "daemon.py")

    # [UPDATE: Hansol] Clarified service description to highlight AI capabilities.
    service_content = f"""[Unit]
Description=AI-Powered File Manager Daemon
After=network.target

[Service]
Type=simple
User=root
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
    try:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", SERVICE_NAME], check=True)
        subprocess.run(["systemctl", "start", SERVICE_NAME], check=True)
        print(f"✓ Daemon is now active.")
    except subprocess.CalledProcessError as e:
        print(f"✗ Service failed: {e}")
        sys.exit(1)

def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    venv_path = create_virtual_env(project_dir)
    install_libmagic()
    check_and_install_dependencies(venv_path)

    # Run one-time cold start setup
    print("Running cold start setup...")
    cold_start_script = os.path.join(project_dir, "cold_start.py")
    python_path = os.path.join(venv_path, "bin", "python")
    try:
        subprocess.run([python_path, cold_start_script], check=True, capture_output=True, text=True)
        print("Cold start completed.")
    except subprocess.CalledProcessError as e:
        print(f"Cold start failed: {e.stderr}")
        sys.exit(1)

    if (shutil.which("systemctl") is None):
        print("systemd not found")
        sys.exit(1)

    write_systemd_service(project_dir, venv_path)
    enable_and_start_service()

if __name__ == "__main__":
    main()
