# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import io
import pygame
import sys
import tkinter as tk
from pygame.locals import *

# --- COSTANTI EVENTI ---
EVT_MOUSE_MOVE = 0
EVT_MOUSE_L_CLICK = 1
EVT_MOUSE_R_CLICK = 2
EVT_MOUSE_SCROLL = 3
EVT_KEY_DOWN = 4
EVT_KEY_UP = 5


def show_config_dialog():
    config_data = {"ip": "0.0.0.0", "port": 9999, "confirm": False}

    def on_confirm():
        config_data["ip"] = entry_ip.get()
        try:
            config_data["port"] = int(entry_port.get())
            config_data["confirm"] = True
            root.destroy()
        except ValueError:
            entry_port.config(bg="#ffcccc")

    root = tk.Tk()
    root.title("Configurazione Server")
    root.geometry("300x180")
    root.eval('tk::PlaceWindow . center')

    tk.Label(root, text="IP di Ascolto (default 0.0.0.0):").pack(pady=(10, 0))
    entry_ip = tk.Entry(root)
    entry_ip.insert(0, "0.0.0.0")
    entry_ip.pack(pady=5)

    tk.Label(root, text="Porta:").pack(pady=(5, 0))
    entry_port = tk.Entry(root)
    entry_port.insert(0, "9999")
    entry_port.pack(pady=5)

    btn = tk.Button(root, text="AVVIA SERVER", command=on_confirm, bg="#dddddd", height=2)
    btn.pack(pady=15, fill="x", padx=20)

    root.mainloop()
    if config_data["confirm"]:
        return config_data["ip"], config_data["port"]
    return None, None


class RemoteDesktopController:
    def __init__(self, bind_ip, port):
        self.bind_ip = bind_ip
        self.port = port
        self.sock = None
        self.conn = None
        self.addr = None
        self.running = False
        self.win_w = 800
        self.win_h = 600
        self.screen = None

    def _recvall(self, n):
        data = b''
        while len(data) < n:
            if not self.running: return None
            try:
                chunk = self.conn.recv(n - len(data))
                if not chunk: return None
                data += chunk
            except socket.timeout:
                continue
            except OSError:
                return None
        return data

    def _send_event(self, event_type, arg1, arg2):
        """
        Invia un evento generico.
        Struttura: >Bff (Byte, Float, Float)
        - Mouse Move:   type=0, x, y (normalizzati)
        - Clicks:       type=1/2, x, y (normalizzati)
        - Scroll:       type=3, 0, amount (+1/-1)
        - Key:          type=4/5, keycode, 0
        """
        if self.conn and self.running:
            try:
                # Normalizziamo le coordinate solo se sono coordinate (per coerenza logica)
                # Ma per semplicità inviamo sempre float e lasciamo il target interpretare
                payload = struct.pack(">Bff", event_type, float(arg1), float(arg2))
                self.conn.sendall(payload)
            except Exception:
                pass

    def start(self):
        pygame.init()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(1.0)

        try:
            self.sock.bind((self.bind_ip, self.port))
            self.sock.listen(1)
        except Exception as e:
            print(f"[Errore] Impossibile avviare: {e}")
            return

        print(f"[Controller] In ascolto su {self.bind_ip}:{self.port}...")

        try:
            while True:
                try:
                    self.conn, self.addr = self.sock.accept()
                    self.conn.settimeout(0.5)
                    print(f"[Controller] Connesso con {self.addr}!")
                    self.running = True
                    self._open_window_and_stream()
                    break
                except socket.timeout:
                    continue
                except KeyboardInterrupt:
                    break
        finally:
            self.cleanup()

    def _open_window_and_stream(self):
        self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)
        pygame.display.set_caption(f"Desktop Remoto - {self.addr[0]}")
        clock = pygame.time.Clock()

        # Disabilita la ripetizione tasti per evitare spam di pacchetti
        pygame.key.set_repeat()

        while self.running:
            for event in pygame.event.get():
                if event.type == QUIT:
                    self.running = False
                    return

                elif event.type == VIDEORESIZE:
                    self.win_w, self.win_h = event.w, event.h
                    self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)

                # --- MOUSE ---
                elif event.type == MOUSEMOTION:
                    # Normalizza X e Y tra 0.0 e 1.0
                    nx = event.pos[0] / self.win_w
                    ny = event.pos[1] / self.win_h
                    self._send_event(EVT_MOUSE_MOVE, nx, ny)

                elif event.type == MOUSEBUTTONDOWN:
                    nx = event.pos[0] / self.win_w
                    ny = event.pos[1] / self.win_h

                    if event.button == 1:  # Sinistro
                        self._send_event(EVT_MOUSE_L_CLICK, nx, ny)
                    elif event.button == 3:  # Destro
                        self._send_event(EVT_MOUSE_R_CLICK, nx, ny)
                    elif event.button == 4:  # Rotella Su
                        self._send_event(EVT_MOUSE_SCROLL, 0, 1)
                    elif event.button == 5:  # Rotella Giù
                        self._send_event(EVT_MOUSE_SCROLL, 0, -1)

                # --- TASTIERA ---
                elif event.type == KEYDOWN:
                    self._send_event(EVT_KEY_DOWN, event.key, 0)

                elif event.type == KEYUP:
                    self._send_event(EVT_KEY_UP, event.key, 0)

            # Ricezione Video
            header = self._recvall(4)
            if not header: break
            msg_size = struct.unpack(">L", header)[0]
            frame_data = self._recvall(msg_size)
            if not frame_data: break

            try:
                image_stream = io.BytesIO(frame_data)
                pyg_img = pygame.image.load(image_stream)
                pyg_img = pygame.transform.scale(pyg_img, (self.win_w, self.win_h))
                self.screen.blit(pyg_img, (0, 0))
                pygame.display.flip()
            except Exception:
                pass

            clock.tick(60)

    def cleanup(self):
        self.running = False
        if self.conn: self.conn.close()
        if self.sock: self.sock.close()
        pygame.quit()
        sys.exit(0)


if __name__ == '__main__':
    user_ip, user_port = show_config_dialog()
    if user_ip and user_port:
        ctrl = RemoteDesktopController(bind_ip=user_ip, port=user_port)
        ctrl.start()
