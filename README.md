# Educational Keylogger for Linux

This project implements a keylogger for educational purposes, designed to run in a controlled environment (e.g., a virtual machine). It captures keystrokes using the Linux input subsystem, logs them locally, and periodically exfiltrates them to a remote HTTP server. The code is intended to demonstrate how malware of this type works and to help cybersecurity students understand attack techniques and corresponding defense strategies.

***⚠️ WARNING:*** This software is for educational use only. Do not run it on any system you do not own or without explicit permission. Misuse of this code may violate laws and regulations.

## Features

- **Keystroke capture** using `evdev`.
- **Local logging** with timestamp formatting.
- **Log rotation** to prevent excessive file growth.
- **Remote exfiltration** via HTTP POST requests.
- **Daemon mode** (run in background).
- **Persistence** through crontab (auto-start on reboot).
- **Termination key** (default ESC) to stop the keylogger gracefully.
- **Automatic virtual environment setup** with required dependencies.

## Requirements

- **Linux** (tested on Ubuntu Desktop 24.04.4)
- **Python 3.6+**
- Root privileges (or membership in the `input` group) to access `/dev/input/event*`.

The script automatically creates a virtual environment and installs the required Python packages (`evdev`, `requests`) if they are missing.

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/educational-keylogger.git
   cd educational-keylogger
