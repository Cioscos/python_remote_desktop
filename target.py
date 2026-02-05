# target.py (SENDER - PC Controllato)
import socket
import threading
import struct
import cv2
import mss
import numpy as np
import pyautogui
import time


class RemoteDesktopTarget:
    def __init__(self, controller_ip, port=9999):
        self.controller_ip = controller_ip
        self.port = port
        self.sock = None
        self.running = False

        # Configurazione PyAutoGUI
        pyautogui.FAILSAFE = False
        self.screen_w, self.screen_h = pyautogui.size()

    def _handle_mouse_input(self):
        """Thread separato per ricevere comandi mouse."""
        payload_size = struct.calcsize(">Bff")

        while self.running:
            try:
                data = self.sock.recv(payload_size)
                if not data:
                    break  # Connessione persa

                event_type, norm_x, norm_y = struct.unpack(">Bff", data)

                # Conversione coordinate
                real_x = int(norm_x * self.screen_w)
                real_y = int(norm_y * self.screen_h)

                if event_type == 0:  # Move
                    pyautogui.moveTo(real_x, real_y, _pause=False)
                elif event_type == 1:  # Click
                    pyautogui.click(real_x, real_y)

            except (ConnectionResetError, BrokenPipeError, OSError):
                break  # Usciamo dal loop, il main thread gestirà la riconnessione
            except Exception as e:
                # Errori di unpacking o pyautogui non devono bloccare tutto
                continue

    def start(self):
        """Loop infinito di tentativi di connessione (Reverse Shell logic)."""
        while True:
            print(f"[Target] Tentativo di connessione a {self.controller_ip}:{self.port}...")

            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.controller_ip, self.port))
                print("[Target] Connessione stabilita!")
                self.running = True

                # Avvia thread input mouse
                input_thread = threading.Thread(target=self._handle_mouse_input, daemon=True)
                input_thread.start()

                # Loop invio schermo
                self._stream_screen()

            except (ConnectionRefusedError, TimeoutError):
                print("[Target] Controller non trovato/non pronto.")
            except (ConnectionResetError, BrokenPipeError):
                print("[Target] Connessione interrotta dal Controller.")
            except Exception as e:
                print(f"[Target] Errore generico: {e}")
            finally:
                self.running = False
                if self.sock:
                    self.sock.close()

                print("[Target] Riprovo tra 3 secondi...")
                time.sleep(3)

    def _stream_screen(self):
        """Cattura schermo, comprime e invia."""
        with mss.mss() as sct:
            # Seleziona il monitor principale
            monitor = sct.monitors[1]

            # Parametri compressione JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]

            while self.running:
                try:
                    # 1. Cattura
                    img = sct.grab(monitor)
                    frame = np.array(img)

                    # Converti da BGRA a BGR (rimuovi alpha channel per risparmiare banda)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                    # 2. Compressione
                    result, encoded_img = cv2.imencode('.jpg', frame, encode_param)
                    if not result:
                        continue

                    data = encoded_img.tobytes()
                    size = len(data)

                    # 3. Invio (Size + Data)
                    # struct.pack forza Big Endian (>) Unsigned Long (L)
                    self.sock.sendall(struct.pack(">L", size) + data)

                    # Piccolo sleep per non saturare la CPU se necessario (opzionale)
                    # time.sleep(0.01)

                except (ConnectionResetError, BrokenPipeError, OSError):
                    print("[Target] Errore durante l'invio dati (Pipe rotta).")
                    break  # Interrompe il while, triggera il finally del metodo start()


if __name__ == '__main__':
    # Sostituisci con l'IP della macchina dove gira controller.py
    IP_CONTROLLER = '192.168.1.XX'
    client = RemoteDesktopTarget(IP_CONTROLLER, port=9999)
    client.start()
