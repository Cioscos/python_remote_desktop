# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import io
import pygame
import sys
import tkinter as tk  # Libreria per la finestra di configurazione
from pygame.locals import *


# --- FUNZIONE PER IL MENU DI CONFIGURAZIONE ---
def show_config_dialog():
    """
    Apre una piccola finestra per chiedere IP e Porta.
    Restituisce una tupla (ip, port) o None se l'utente chiude.
    """
    config_data = {"ip": "0.0.0.0", "port": 9999, "confirm": False}

    def on_confirm():
        config_data["ip"] = entry_ip.get()
        try:
            config_data["port"] = int(entry_port.get())
            config_data["confirm"] = True
            root.destroy()
        except ValueError:
            # Se la porta non è un numero, colora di rosso (feedback visivo base)
            entry_port.config(bg="#ffcccc")

    # Setup finestra Tkinter
    root = tk.Tk()
    root.title("Configurazione Server")
    root.geometry("300x180")
    root.eval('tk::PlaceWindow . center')  # Centra la finestra

    # Label e Input IP
    tk.Label(root, text="IP di Ascolto (default 0.0.0.0):").pack(pady=(10, 0))
    entry_ip = tk.Entry(root)
    entry_ip.insert(0, "0.0.0.0")  # Valore default
    entry_ip.pack(pady=5)

    # Label e Input Porta
    tk.Label(root, text="Porta:").pack(pady=(5, 0))
    entry_port = tk.Entry(root)
    entry_port.insert(0, "9999")  # Valore default
    entry_port.pack(pady=5)

    # Bottone Avvia
    btn = tk.Button(root, text="AVVIA SERVER", command=on_confirm, bg="#dddddd", height=2)
    btn.pack(pady=15, fill="x", padx=20)

    root.mainloop()

    if config_data["confirm"]:
        return config_data["ip"], config_data["port"]
    return None, None


# --- CLASSE PRINCIPALE CONTROLLER ---
class RemoteDesktopController:
    def __init__(self, bind_ip, port):
        self.bind_ip = bind_ip
        self.port = port
        self.sock = None
        self.conn = None
        self.addr = None
        self.running = False

        # Dimensioni iniziali finestra
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

    def _send_mouse_event(self, event_type, x, y):
        if self.conn and self.running and self.win_w > 0 and self.win_h > 0:
            norm_x = max(0.0, min(1.0, x / self.win_w))
            norm_y = max(0.0, min(1.0, y / self.win_h))
            try:
                payload = struct.pack(">Bff", event_type, norm_x, norm_y)
                self.conn.sendall(payload)
            except Exception:
                pass

    def start(self):
        # Inizializza PyGame (ma senza finestra per ora)
        pygame.init()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(1.0)

        try:
            self.sock.bind((self.bind_ip, self.port))
            self.sock.listen(1)
        except Exception as e:
            print(f"[Errore] Impossibile avviare su {self.bind_ip}:{self.port}")
            print(f"Dettaglio: {e}")
            return

        print(f"[Controller] In ascolto su {self.bind_ip}:{self.port}...")
        print("[Info] In attesa del Sender per aprire la finestra video...")

        try:
            while True:
                try:
                    self.conn, self.addr = self.sock.accept()
                    self.conn.settimeout(0.5)
                    print(f"[Controller] Connesso con {self.addr}! Apro video...")

                    self.running = True
                    self._open_window_and_stream()
                    break

                except socket.timeout:
                    continue
                except KeyboardInterrupt:
                    print("\n[Controller] Stop da tastiera.")
                    break
        finally:
            self.cleanup()

    def _open_window_and_stream(self):
        self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)
        pygame.display.set_caption(f"Desktop Remoto - {self.addr[0]}:{self.addr[1]}")
        clock = pygame.time.Clock()

        while self.running:
            for event in pygame.event.get():
                if event.type == QUIT:
                    print("[Controller] Chiusura richiesta utente.")
                    self.running = False
                    return

                elif event.type == VIDEORESIZE:
                    self.win_w, self.win_h = event.w, event.h
                    self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)

                elif event.type == MOUSEMOTION:
                    self._send_mouse_event(0, event.pos[0], event.pos[1])

                elif event.type == MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self._send_mouse_event(1, event.pos[0], event.pos[1])

            # Ricezione dati
            header = self._recvall(4)
            if not header:
                print("[Controller] Sender disconnesso.")
                break
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
    # 1. Mostra il menu di configurazione
    user_ip, user_port = show_config_dialog()

    # 2. Se l'utente ha premuto "Avvia", lancia il controller
    if user_ip and user_port:
        ctrl = RemoteDesktopController(bind_ip=user_ip, port=user_port)
        ctrl.start()
    else:
        print("Avvio annullato dall'utente.")
