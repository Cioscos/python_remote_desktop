# target.py (SENDER - PC Controllato)
import socket
import threading
import struct
import cv2
import mss
import numpy as np
import pyautogui
import time
import tkinter as tk
import win32gui
import win32con
import win32api
import pywintypes

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
        print(f"[Display] Risoluzione originale salvata: {self.current_width}x{self.current_height}")

    def change_resolution(self, width, height):
        """Tenta di cambiare la risoluzione. Ritorna True se riesce."""
        if not self.original_devmode: self.save_current()
        if width == self.current_width and height == self.current_height: return True

        devmode = win32api.EnumDisplaySettings(None, win32con.ENUM_CURRENT_SETTINGS)
        devmode.PelsWidth = width
        devmode.PelsHeight = height
        devmode.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT

        try:
            res = win32api.ChangeDisplaySettings(devmode, win32con.CDS_TEST)
            if res != win32con.DISP_CHANGE_SUCCESSFUL:
                print("[Display] Risoluzione non supportata.")
                return False

            win32api.ChangeDisplaySettings(devmode, 0)
            self.current_width = width
            self.current_height = height
            print(f"[Display] Risoluzione cambiata a {width}x{height}")
            return True
        except Exception as e:
            print(f"[Display] Errore cambio risoluzione: {e}")
            return False

    def restore(self):
        """Ripristina la risoluzione originale."""
        if self.original_devmode:
            print("[Display] Ripristino risoluzione originale...")
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
    def __init__(self, controller_ip, port=9999):
        self.controller_ip = controller_ip
        self.port = port
        self.sock = None
        self.running = False
        self.res_manager = ResolutionManager()
        self.res_manager.save_current()  # Salva subito lo stato iniziale

    def _handle_input(self):
        while self.running:
            try:
                header = self._recvall(1)
                if not header: break
                event_type = struct.unpack(">B", header)[0]

                # Aggiorniamo le dimensioni schermo correnti per il mouse
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
                    if not l_byte: break
                    k_len = struct.unpack(">B", l_byte)[0]
                    key = self._recvall(k_len).decode('utf-8')
                    if event_type == 4:
                        pyautogui.keyDown(key)
                    else:
                        pyautogui.keyUp(key)

                # NUOVO TIPO: 6 -> Richiesta Cambio Risoluzione
                elif event_type == 6:
                    data = self._recvall(8)
                    w, h = struct.unpack(">II", data)
                    print(f"[Target] Richiesta cambio ris: {w}x{h}")
                    self.res_manager.change_resolution(w, h)

            except Exception:
                break

    def start(self):
        print(f"[Target] Connessione a {self.controller_ip}:{self.port}")
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.controller_ip, self.port))
                self.running = True
                print("[Target] Connesso!")

                threading.Thread(target=self._handle_input, daemon=True).start()
                self._stream_screen()

            except Exception:
                time.sleep(2)
            except KeyboardInterrupt:
                break
            finally:
                self.running = False
                if self.sock: self.sock.close()
                self.res_manager.restore()  # IMPORTANTE: Ripristina risoluzione

    def _recvall(self, n):
        data = b''
        while len(data) < n and self.running:
            try:
                chunk = self.sock.recv(n - len(data))
                if not chunk: return None
                data += chunk
            except:
                return None
        return data

    def _stream_screen(self):
        with mss.mss() as sct:
            # QUALITÀ AUMENTATA: 90 (Prima era 60 o default)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]

            while self.running:
                try:
                    # Monitor 1 (adattivo se cambia risoluzione)
                    monitor = sct.monitors[1]
                    img = np.array(sct.grab(monitor))
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    _, enc_img = cv2.imencode('.jpg', img, encode_param)
                    data = enc_img.tobytes()

                    cid = get_current_cursor_id()
                    packet = struct.pack(">LB", len(data), cid) + data
                    self.sock.sendall(packet)

                    # Rimuovi lo sleep o tienilo molto basso per massimizzare FPS
                    # time.sleep(0.01)
                except:
                    break


def get_config_dialog():
    config = {"ip": None, "port": None}
    root = tk.Tk()
    root.title("Target Config")
    tk.Label(root, text="Controller IP:").pack()
    e_ip = tk.Entry(root);
    e_ip.insert(0, "192.168.1.X");
    e_ip.pack()
    tk.Label(root, text="Port:").pack()
    e_port = tk.Entry(root);
    e_port.insert(0, "9999");
    e_port.pack()

    def on_c():
        config["ip"] = e_ip.get()
        config["port"] = int(e_port.get())
        root.destroy()

    tk.Button(root, text="CONNECT", command=on_c).pack()
    root.mainloop()
    return config["ip"], config["port"]


if __name__ == '__main__':
    ip, port = get_config_dialog()
    if ip and port:
        RemoteDesktopTarget(ip, port).start()
