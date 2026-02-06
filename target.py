# target.py (SENDER - PC Controllato) - CustomTkinter dialog
import socket
import threading
import struct
import cv2
import mss
import numpy as np
import pyautogui
import time
import hashlib
import ssl
import customtkinter as ctk
import win32gui
import win32con
import win32api
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0


# === GESTIONE RISOLUZIONE ===
class ResolutionManager:
    def __init__(self):
        self.original_devmode = None
        self.current_width = 0
        self.current_height = 0

    def save_current(self):
        """Salva la risoluzione attuale per il ripristino."""
        self.original_devmode = win32api.EnumDisplaySettings(None, win32con.ENUM_CURRENT_SETTINGS)
        self.current_width = self.original_devmode.PelsWidth
        self.current_height = self.original_devmode.PelsHeight
        logger.info(f"Risoluzione originale salvata: {self.current_width}x{self.current_height}")

    def change_resolution(self, width, height):
        """Tenta di cambiare la risoluzione. Ritorna True se riesce."""
        if not self.original_devmode:
            self.save_current()
        if width == self.current_width and height == self.current_height:
            return True

        devmode = win32api.EnumDisplaySettings(None, win32con.ENUM_CURRENT_SETTINGS)
        devmode.PelsWidth = width
        devmode.PelsHeight = height
        devmode.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT

        try:
            res = win32api.ChangeDisplaySettings(devmode, win32con.CDS_TEST)
            if res != win32con.DISP_CHANGE_SUCCESSFUL:
                logger.warning("Risoluzione non supportata.")
                return False

            win32api.ChangeDisplaySettings(devmode, 0)
            self.current_width = width
            self.current_height = height
            logger.info(f"Risoluzione cambiata a {width}x{height}")
            return True
        except Exception as e:
            logger.error(f"Errore cambio risoluzione: {e}")
            return False

    def restore(self):
        """Ripristina la risoluzione originale."""
        if self.original_devmode:
            logger.info("Ripristino risoluzione originale...")
            win32api.ChangeDisplaySettings(self.original_devmode, 0)


# === GESTIONE CURSORE ===
SYSTEM_CURSORS = {
    win32gui.LoadCursor(0, win32con.IDC_ARROW): 0,
    win32gui.LoadCursor(0, win32con.IDC_IBEAM): 1,
    win32gui.LoadCursor(0, win32con.IDC_HAND): 2,
    win32gui.LoadCursor(0, win32con.IDC_WAIT): 3,
    win32gui.LoadCursor(0, win32con.IDC_CROSS): 4,
    win32gui.LoadCursor(0, win32con.IDC_SIZENS): 5,
    win32gui.LoadCursor(0, win32con.IDC_SIZEWE): 6
}


def get_current_cursor_id():
    try:
        info = win32gui.GetCursorInfo()
        return SYSTEM_CURSORS.get(info[1], 0)
    except:
        return 0


class RemoteDesktopTarget:
    def __init__(self, controller_ip, port=9999, password=None, use_ssl=False, target_fps=30):
        self.controller_ip = controller_ip
        self.port = port
        self.password = password
        self.use_ssl = use_ssl
        self.sock = None
        self.running = False
        self.res_manager = ResolutionManager()
        self.res_manager.save_current()

        # Frame rate limiter
        self.target_fps = target_fps
        self.frame_time = 1.0 / target_fps

        # Clipboard
        self.last_clipboard = ""

        # Quality adaptive
        self.encode_quality = 90

    def _authenticate_with_server(self, sock):
        """Autentica con il server usando challenge-response"""
        if not self.password:
            return True

        try:
            challenge = sock.recv(64).decode()
            response = hashlib.sha256((challenge + self.password).encode()).hexdigest()
            sock.sendall(response.encode())

            result = sock.recv(4).decode()
            if result == "OK":
                logger.info("Autenticazione riuscita")
                return True
            else:
                logger.error("Autenticazione fallita")
                return False
        except Exception as e:
            logger.error(f"Errore autenticazione: {e}")
            return False

    def _handle_input(self):
        while self.running:
            try:
                header = self._recvall(1)
                if not header:
                    break
                event_type = struct.unpack(">B", header)[0]

                screen_w, screen_h = pyautogui.size()

                if event_type == 0:  # MOVE
                    data = self._recvall(8)
                    nx, ny = struct.unpack(">ff", data)
                    pyautogui.moveTo(int(nx * screen_w), int(ny * screen_h), _pause=False)

                elif event_type in [1, 2]:  # CLICK
                    data = self._recvall(9)
                    btn, nx, ny = struct.unpack(">Bff", data)
                    x, y = int(nx * screen_w), int(ny * screen_h)
                    btn_s = {1: 'left', 2: 'middle', 3: 'right'}.get(btn, 'left')
                    if event_type == 1:
                        pyautogui.mouseDown(x, y, button=btn_s)
                    else:
                        pyautogui.mouseUp(x, y, button=btn_s)

                elif event_type == 3:  # SCROLL
                    data = self._recvall(4)
                    pyautogui.scroll(struct.unpack(">i", data)[0])

                elif event_type in [4, 5]:  # KEYBOARD
                    l_byte = self._recvall(1)
                    if not l_byte:
                        break
                    k_len = struct.unpack(">B", l_byte)[0]
                    key = self._recvall(k_len).decode('utf-8')
                    if event_type == 4:
                        pyautogui.keyDown(key)
                    else:
                        pyautogui.keyUp(key)

                elif event_type == 6:  # RISOLUZIONE
                    data = self._recvall(8)
                    w, h = struct.unpack(">II", data)
                    logger.info(f"Richiesta cambio ris: {w}x{h}")
                    self.res_manager.change_resolution(w, h)

                elif event_type == 7:  # CLIPBOARD
                    data = self._recvall(4)
                    text_len = struct.unpack(">I", data)[0]
                    text = self._recvall(text_len).decode('utf-8')
                    try:
                        import pyperclip
                        pyperclip.copy(text)
                        self.last_clipboard = text
                        logger.info("Clipboard sincronizzato")
                    except ImportError:
                        pass

            except Exception as e:
                logger.error(f"Input handler error: {e}")
                break

    def start(self):
        logger.info(f"Connessione a {self.controller_ip}:{self.port}")
        retry_delay = 2

        while True:
            try:
                raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # TCP_NODELAY per ridurre latenza
                raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                # Buffer più grandi
                raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 512000)

                raw_sock.connect((self.controller_ip, self.port))

                # Wrap con SSL se abilitato
                if self.use_ssl:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    self.sock = context.wrap_socket(raw_sock)
                    logger.info("SSL connection established")
                else:
                    self.sock = raw_sock

                # Autenticazione
                if not self._authenticate_with_server(self.sock):
                    self.sock.close()
                    time.sleep(retry_delay)
                    continue

                self.running = True
                logger.info("Connesso!")

                threading.Thread(target=self._handle_input, daemon=True).start()
                self._stream_screen()

            except ConnectionRefusedError:
                logger.warning(f"Connessione rifiutata, riprovo tra {retry_delay}s...")
                time.sleep(retry_delay)
            except Exception as e:
                logger.error(f"Errore: {e}")
                time.sleep(retry_delay)
            except KeyboardInterrupt:
                break
            finally:
                self.running = False
                if self.sock:
                    self.sock.close()
                self.res_manager.restore()

    def _recvall(self, n):
        data = b''
        while len(data) < n and self.running:
            try:
                chunk = self.sock.recv(n - len(data))
                if not chunk:
                    return None
                data += chunk
            except:
                return None
        return data

    def _stream_screen(self):
        with mss.mss() as sct:
            last_frame_time = time.time()

            while self.running:
                try:
                    # Frame rate limiter
                    elapsed = time.time() - last_frame_time
                    if elapsed < self.frame_time:
                        time.sleep(self.frame_time - elapsed)
                    last_frame_time = time.time()

                    monitor = sct.monitors[1]
                    img = np.array(sct.grab(monitor))
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    # Compressione con qualità configurabile
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.encode_quality]
                    _, enc_img = cv2.imencode('.jpg', img, encode_param)
                    data = enc_img.tobytes()

                    cid = get_current_cursor_id()
                    packet = struct.pack(">LB", len(data), cid) + data
                    self.sock.sendall(packet)
                except Exception as e:
                    logger.error(f"Stream error: {e}")
                    break


def get_config_dialog():
    config = {"ip": None, "port": None, "password": None, "ssl": False, "fps": 30}

    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Target Config")
    root.geometry("380x360")

    ctk.CTkLabel(root, text="Controller IP:").pack(pady=(14, 2))
    e_ip = ctk.CTkEntry(root)
    e_ip.insert(0, "192.168.1.X")
    e_ip.pack(padx=12, fill="x")

    ctk.CTkLabel(root, text="Port:").pack(pady=(10, 2))
    e_port = ctk.CTkEntry(root)
    e_port.insert(0, "9999")
    e_port.pack(padx=12, fill="x")

    ctk.CTkLabel(root, text="Password (lascia vuoto se non richiesta):").pack(pady=(10, 2))
    e_pass = ctk.CTkEntry(root, show="*")
    e_pass.pack(padx=12, fill="x")

    ctk.CTkLabel(root, text="Target FPS:").pack(pady=(10, 2))
    e_fps = ctk.CTkEntry(root)
    e_fps.insert(0, "30")
    e_fps.pack(padx=12, fill="x")

    var_ssl = ctk.BooleanVar(value=False)
    ctk.CTkCheckBox(root, text="Usa SSL/TLS", variable=var_ssl).pack(pady=8, padx=12, anchor="w")

    def on_c():
        config["ip"] = e_ip.get().strip()
        config["port"] = int(e_port.get().strip())
        config["password"] = e_pass.get().strip() or None
        config["ssl"] = bool(var_ssl.get())
        config["fps"] = int(e_fps.get().strip())
        root.destroy()

    ctk.CTkButton(root, text="CONNECT", command=on_c).pack(pady=14)
    root.mainloop()
    return config


if __name__ == '__main__':
    cfg = get_config_dialog()
    if cfg["ip"] and cfg["port"]:
        RemoteDesktopTarget(
            cfg["ip"],
            cfg["port"],
            cfg["password"],
            cfg["ssl"],
            cfg["fps"]
        ).start()
