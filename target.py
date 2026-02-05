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
from tkinter import messagebox

# Configurazioni PyAutoGUI per velocità
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0  # Rimuove il ritardo di default tra le azioni


class RemoteDesktopTarget:
    def __init__(self, controller_ip, port=9999):
        self.controller_ip = controller_ip
        self.port = port
        self.sock = None
        self.running = False
        self.screen_w, self.screen_h = pyautogui.size()

    def _handle_input(self):
        """Thread ricezione comandi (Mouse e Tastiera)."""
        while self.running:
            try:
                # 1. Leggi il tipo di evento (1 byte)
                # Tipi: 0=Move, 1=Down, 2=Up, 3=Scroll, 4=KeyDown, 5=KeyUp
                header = self._recvall(1)
                if not header: break
                event_type = struct.unpack(">B", header)[0]

                if event_type == 0:  # MOUSE MOVE
                    data = self._recvall(8)  # 2 float (4+4 byte)
                    norm_x, norm_y = struct.unpack(">ff", data)
                    x, y = int(norm_x * self.screen_w), int(norm_y * self.screen_h)
                    pyautogui.moveTo(x, y, _pause=False)

                elif event_type in [1, 2]:  # MOUSE BUTTON DOWN/UP
                    data = self._recvall(9)  # button_code (1B) + 2 float (8B)
                    btn_code, norm_x, norm_y = struct.unpack(">Bff", data)
                    x, y = int(norm_x * self.screen_w), int(norm_y * self.screen_h)

                    # Mappa codici: 1=left, 2=middle, 3=right
                    btn_map = {1: 'left', 2: 'middle', 3: 'right'}
                    button = btn_map.get(btn_code, 'left')

                    if event_type == 1:
                        pyautogui.mouseDown(x, y, button=button)
                    else:
                        pyautogui.mouseUp(x, y, button=button)

                elif event_type == 3:  # SCROLL
                    data = self._recvall(4)  # int (4B)
                    amount = struct.unpack(">i", data)[0]
                    pyautogui.scroll(amount)

                elif event_type in [4, 5]:  # KEYBOARD
                    # Legge lunghezza nome tasto (1B)
                    len_byte = self._recvall(1)
                    if not len_byte: break
                    key_len = struct.unpack(">B", len_byte)[0]

                    # Legge il nome del tasto
                    key_name = self._recvall(key_len).decode('utf-8')

                    if event_type == 4:
                        pyautogui.keyDown(key_name)
                    else:
                        pyautogui.keyUp(key_name)

            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Target] Errore input: {e}")
                break

    def start(self):
        print(f"[Target] Avvio client verso {self.controller_ip}:{self.port}")

        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)
                self.sock.connect((self.controller_ip, self.port))
                self.sock.settimeout(0.5)  # Timeout breve per recv

                print("[Target] Connesso al Controller!")
                self.running = True

                input_thread = threading.Thread(target=self._handle_input, daemon=True)
                input_thread.start()

                self._stream_screen()

            except socket.timeout:
                print(f"[Target] Timeout connessione... Riprovo.")
            except (ConnectionRefusedError, OSError):
                print(f"[Target] Controller non trovato. Riprovo tra 2s...")
                time.sleep(2)
            except KeyboardInterrupt:
                self.running = False
                break
            finally:
                self.running = False
                if self.sock: self.sock.close()

    def _recvall(self, n: int):
        data = b''
        while len(data) < n and self.running:
            try:
                chunk = self.sock.recv(n - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                continue
            except OSError:
                return None
        return data if len(data) == n else None

    def _stream_screen(self):
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            # Qualità JPEG ridotta per fluidità (puoi alzarla a 70-80)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]

            while self.running:
                try:
                    img = np.array(sct.grab(monitor))
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    _, encoded_img = cv2.imencode('.jpg', img, encode_param)
                    data = encoded_img.tobytes()

                    # Invia lunghezza + dati
                    self.sock.sendall(struct.pack(">L", len(data)) + data)
                except Exception:
                    break


# --- GUI CONFIGURAZIONE (Invariata) ---
def get_config_dialog():
    config = {"ip": None, "port": None}
    root = tk.Tk()
    root.title("Config Target")
    root.geometry("300x180")

    tk.Label(root, text="IP Controller:").pack(pady=5)
    e_ip = tk.Entry(root);
    e_ip.insert(0, "192.168.1.X");
    e_ip.pack()
    tk.Label(root, text="Porta:").pack(pady=5)
    e_port = tk.Entry(root);
    e_port.insert(0, "9999");
    e_port.pack()

    def on_c():
        try:
            config["port"] = int(e_port.get())
            config["ip"] = e_ip.get()
            root.destroy()
        except:
            pass

    tk.Button(root, text="CONNETTI", command=on_c).pack(pady=15)
    root.mainloop()
    return config["ip"], config["port"]


if __name__ == '__main__':
    ip, port = get_config_dialog()
    if ip and port:
        RemoteDesktopTarget(ip, port).start()
