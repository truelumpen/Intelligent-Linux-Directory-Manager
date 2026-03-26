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
PACKAGES = {
    "scikit-learn": "sklearn",
    "watchdog": "watchdog",
    "python-magic": "python-magic"
}
SERVICE_NAME = "sorty-daemon"
SERVICE_FILE = f"/etc/systemd/system/{SERVICE_NAME}.service"
VENV_DIR = ".venv"

# creating venv for the external libraries
def create_virtual_env(project_dir):
    # create a venv
    venv_path = os.path.join(project_dir, VENV_DIR)
    print(f"Creating virtual env for the dependencies in {venv_path}...")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", venv_path],
            check=True,
            capture_output=True
        )
        print(f"✓ Virtual environment created")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to create virtual environment: {e.stderr.decode()}")
        sys.exit(1)

    return venv_path


def install_package(package):
    """Install a Python package using pip."""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✓ Installed {package}")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install {package}: {e}")
        sys.exit(1)


def check_and_install_dependencies(venv_path):

    # Install dependencies in .venv
    pip_path = os.path.join(venv_path, "bin", "pip")

    # Install required packages
    for package in PACKAGES:
        print(f"Installing {package}...")
        try:
            subprocess.run(
                [pip_path, "install", package],
                check=True,
                capture_output=True
            )
            print(f"✓ {package} installed")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install {package}: {e.stderr.decode()}")
            sys.exit(1)


def write_systemd_service(project_dir, venv_path):
    """Create the systemd service file pointing to the virtual environment."""
    python_path = os.path.join(venv_path, "bin", "python")
    daemon_path = os.path.join(project_dir, "daemon.py")

    service_content = f"""[Unit]
    Description=My Python Daemon
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
    print(f"✓ Created systemd service file: {SERVICE_FILE}")


def enable_and_start_service():
    """Enable and start the systemd service."""
    try:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", SERVICE_NAME], check=True)
        subprocess.run(["systemctl", "start", SERVICE_NAME], check=True)
        print(f"✓ Enabled and started systemd service: {SERVICE_NAME}")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to enable/start service: {e}")
        sys.exit(1)


def main():

    project_dir = os.path.dirname(os.path.abspath(__file__))

    print("Setting up Python virtual environment...")
    venv_path = create_virtual_env(project_dir)

    print("Checking dependencies...")
    check_and_install_dependencies(venv_path)

    # Check if systemd is present
    if (shutil.which("systemctl") is None):
        print("systemd not found")
        sys.exit(1)

    print("Setting up the daemon...")
    # write systemd service
    write_systemd_service(project_dir, venv_path)

    # start the daemon
    enable_and_start_service()


    # print("\nStarting daemon...")
    # start_daemon()
    # print("\nDaemon is running in the background.")


if __name__ == "__main__":
    main()
