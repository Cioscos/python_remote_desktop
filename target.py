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

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# === GESTIONE CURSORE WINDOWS ===
# Pre-carichiamo gli handle standard per confrontarli nel loop
SYSTEM_CURSORS = {
    win32gui.LoadCursor(0, win32con.IDC_ARROW): 0,
    win32gui.LoadCursor(0, win32con.IDC_IBEAM): 1,
    win32gui.LoadCursor(0, win32con.IDC_HAND): 2,
    win32gui.LoadCursor(0, win32con.IDC_WAIT): 3,
    win32gui.LoadCursor(0, win32con.IDC_CROSS): 4,
    win32gui.LoadCursor(0, win32con.IDC_SIZENS): 5,
    win32gui.LoadCursor(0, win32con.IDC_SIZEWE): 6,
    # Aggiungi altri se necessario
}


def get_current_cursor_id():
    """Restituisce l'ID del cursore attuale (0-6) o 0 se sconosciuto."""
    try:
        # GetCursorInfo restituisce (flags, hCursor, (x,y))
        info = win32gui.GetCursorInfo()
        h_cursor = info[1]
        return SYSTEM_CURSORS.get(h_cursor, 0)
    except:
        return 0


class RemoteDesktopTarget:
    def __init__(self, controller_ip, port=9999):
        self.controller_ip = controller_ip
        self.port = port
        self.sock = None
        self.running = False
        self.screen_w, self.screen_h = pyautogui.size()

    def _handle_input(self):
        """Thread ricezione comandi."""
        while self.running:
            try:
                # 1. Leggi tipo evento (1 byte)
                header = self._recvall(1)
                if not header: break
                event_type = struct.unpack(">B", header)[0]

                if event_type == 0:  # MOUSE MOVE
                    data = self._recvall(8)
                    norm_x, norm_y = struct.unpack(">ff", data)
                    x, y = int(norm_x * self.screen_w), int(norm_y * self.screen_h)
                    pyautogui.moveTo(x, y, _pause=False)

                elif event_type in [1, 2]:  # MOUSE CLICK
                    data = self._recvall(9)
                    btn_code, norm_x, norm_y = struct.unpack(">Bff", data)
                    x, y = int(norm_x * self.screen_w), int(norm_y * self.screen_h)
                    btn_map = {1: 'left', 2: 'middle', 3: 'right'}
                    button = btn_map.get(btn_code, 'left')

                    if event_type == 1:
                        pyautogui.mouseDown(x, y, button=button)
                    else:
                        pyautogui.mouseUp(x, y, button=button)

                elif event_type == 3:  # SCROLL
                    data = self._recvall(4)
                    amount = struct.unpack(">i", data)[0]
                    pyautogui.scroll(amount)

                elif event_type in [4, 5]:  # KEYBOARD
                    len_byte = self._recvall(1)
                    if not len_byte: break
                    key_len = struct.unpack(">B", len_byte)[0]
                    key_name = self._recvall(key_len).decode('utf-8')

                    # Controllo validità tasto
                    if key_name in pyautogui.KEY_NAMES or len(key_name) == 1:
                        if event_type == 4:
                            pyautogui.keyDown(key_name)
                        else:
                            pyautogui.keyUp(key_name)
                    else:
                        print(f"[Target] Tasto ignoto ricevuto: {key_name}")

            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Target] Input Error: {e}")
                break

    def start(self):
        print(f"[Target] Connecting to {self.controller_ip}:{self.port}")

        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)
                self.sock.connect((self.controller_ip, self.port))
                self.sock.settimeout(0.5)

                print("[Target] CONNECTED!")
                self.running = True

                threading.Thread(target=self._handle_input, daemon=True).start()
                self._stream_screen()

            except (socket.timeout, ConnectionRefusedError, OSError):
                print(f"[Target] Retrying connection in 2s...")
                time.sleep(2)
            except KeyboardInterrupt:
                break
            finally:
                self.running = False
                if self.sock: self.sock.close()

    def _recvall(self, n):
        data = b''
        while len(data) < n and self.running:
            try:
                chunk = self.sock.recv(n - len(data))
                if not chunk: return None
                data += chunk
            except socket.timeout:
                continue
            except OSError:
                return None
        return data if len(data) == n else None

    def _stream_screen(self):
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            # Compressione JPEG per velocità (quality=50) o PNG (livello 3)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 60]

            while self.running:
                try:
                    # Cattura schermo
                    img = np.array(sct.grab(monitor))
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    # Codifica
                    _, encoded_img = cv2.imencode('.jpg', img, encode_param)
                    data = encoded_img.tobytes()

                    # Ottieni ID cursore
                    cursor_id = get_current_cursor_id()

                    # PACKET: [Size 4B] + [CursorID 1B] + [Data]
                    packet = struct.pack(">LB", len(data), cursor_id) + data
                    self.sock.sendall(packet)

                    # Limit FPS (opzionale)
                    time.sleep(0.03)
                except Exception as e:
                    print(f"[Stream] Error: {e}")
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

    tk.Button(root, text="CONNECT", command=on_c).pack(pady=10)
    root.mainloop()
    return config["ip"], config["port"]


if __name__ == '__main__':
    ip, port = get_config_dialog()
    if ip and port:
        RemoteDesktopTarget(ip, port).start()
