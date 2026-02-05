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


class RemoteDesktopTarget:
    def __init__(self, controller_ip, port=9999):
        self.controller_ip = controller_ip
        self.port = port
        self.sock = None
        self.running = False
        pyautogui.FAILSAFE = False
        self.screen_w, self.screen_h = pyautogui.size()

    def _handle_mouse_input(self):
        """Thread mouse con gestione timeout per uscita pulita."""
        payload_size = struct.calcsize(">Bff")

        while self.running:
            try:
                # recv ora lancerà socket.timeout se non riceve nulla entro 0.5s
                data = self.sock.recv(payload_size)
                if not data:
                    break

                event_type, norm_x, norm_y = struct.unpack(">Bff", data)
                real_x = int(norm_x * self.screen_w)
                real_y = int(norm_y * self.screen_h)

                if event_type == 0:
                    pyautogui.moveTo(real_x, real_y, _pause=False)
                elif event_type == 1:
                    pyautogui.click(real_x, real_y)

            except socket.timeout:
                # Nessun dato ricevuto, torniamo su per controllare 'self.running'
                continue
            except Exception:
                break

    def start(self):
        print(f"[Target] Avvio client verso {self.controller_ip}:{self.port}")
        print("[Info] Premi Ctrl+C nella console per terminare.")

        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)  # Timeout per la connect
                self.sock.connect((self.controller_ip, self.port))

                # Una volta connesso, riduciamo il timeout per rendere reattivo recv
                self.sock.settimeout(0.5)

                print("[Target] Connesso al Controller!")
                self.running = True

                mouse_thread = threading.Thread(target=self._handle_mouse_input, daemon=True)
                mouse_thread.start()

                self._stream_screen()

            except socket.timeout:
                print(f"[Target] Timeout connessione verso {self.controller_ip}... Riprovo.")
            except (ConnectionRefusedError, OSError):
                print(f"[Target] Controller non trovato su {self.controller_ip}. Riprovo tra 2s...")
            except KeyboardInterrupt:
                print("\n[Target] Uscita richiesta dall'utente.")
                self.running = False
                break
            finally:
                if self.running:
                    self.running = False
                if self.sock:
                    self.sock.close()

            # Piccolo sleep prima di riconnettersi, interrompibile
            try:
                time.sleep(2)
            except KeyboardInterrupt:
                print("\n[Target] Stop durante l'attesa.")
                break

    def _stream_screen(self):
        with mss.mss() as sct:
            # Monitor 1 è solitamente "tutti i monitor" o il principale.
            # Se hai più monitor e vuoi solo il primo, usa sct.monitors[1]
            monitor = sct.monitors[1]
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]

            while self.running:
                try:
                    img = np.array(sct.grab(monitor))
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    _, encoded_img = cv2.imencode('.jpg', img, encode_param)
                    data = encoded_img.tobytes()

                    self.sock.sendall(struct.pack(">L", len(data)) + data)

                except (socket.timeout, BlockingIOError):
                    continue
                except (BrokenPipeError, ConnectionResetError, OSError):
                    print("[Target] Connessione persa.")
                    break
                except Exception as e:
                    print(f"[Target] Errore stream: {e}")
                    break


# --- FUNZIONE GUI CONFIGURAZIONE ---
def get_config_dialog():
    """Mostra una finestra Tkinter per chiedere IP e Porta."""
    config = {"ip": None, "port": None}

    root = tk.Tk()
    root.title("Configurazione Target")
    root.geometry("300x180")

    # Label e Entry IP
    tk.Label(root, text="IP del Controller:").pack(pady=(15, 5))
    entry_ip = tk.Entry(root)
    entry_ip.insert(0, "192.168.1.X")  # Placeholder comodo
    entry_ip.pack()

    # Label e Entry Porta
    tk.Label(root, text="Porta:").pack(pady=(5, 5))
    entry_port = tk.Entry(root)
    entry_port.insert(0, "9999")
    entry_port.pack()

    def on_connect():
        ip = entry_ip.get().strip()
        port_str = entry_port.get().strip()

        if not ip:
            messagebox.showwarning("Errore", "Inserisci un IP valido.")
            return

        try:
            port = int(port_str)
            config["ip"] = ip
            config["port"] = port
            root.destroy()  # Chiude la finestra e prosegue
        except ValueError:
            messagebox.showerror("Errore", "La porta deve essere un numero.")

    tk.Button(root, text="CONNETTI", command=on_connect, bg="#dddddd", height=2).pack(pady=20, fill="x", padx=20)

    # Gestione chiusura con "X"
    def on_close():
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

    return config["ip"], config["port"]


if __name__ == '__main__':
    # 1. Chiedi configurazione via GUI
    user_ip, user_port = get_config_dialog()

    # 2. Se l'utente ha confermato, avvia il client
    if user_ip and user_port:
        client = RemoteDesktopTarget(user_ip, port=user_port)
        client.start()
    else:
        print("[Target] Avvio annullato.")
