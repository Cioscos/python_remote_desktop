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
        print(f"[Target] Avvio client verso {self.controller_ip} (Ctrl+C per chiudere)")

        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)  # Timeout per la connect
                self.sock.connect((self.controller_ip, self.port))

                # Una volta connesso, riduciamo il timeout per rendere reattivo recv
                self.sock.settimeout(0.5)

                print("[Target] Connesso!")
                self.running = True

                mouse_thread = threading.Thread(target=self._handle_mouse_input, daemon=True)
                mouse_thread.start()

                self._stream_screen()

            except socket.timeout:
                pass  # Timeout connessione, riprova
            except (ConnectionRefusedError, OSError):
                # Non stampare spam se il server è giù, aspetta e basta
                pass
            except KeyboardInterrupt:
                print("\n[Target] Uscita richiesta dall'utente.")
                self.running = False
                break
            finally:
                if self.running:  # Se siamo usciti per errore di rete, resettiamo
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
            monitor = sct.monitors[1]
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]

            while self.running:
                try:
                    img = np.array(sct.grab(monitor))
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    _, encoded_img = cv2.imencode('.jpg', img, encode_param)
                    data = encoded_img.tobytes()

                    # sendall può bloccare se il buffer è pieno, ma è raro con timeout
                    self.sock.sendall(struct.pack(">L", len(data)) + data)

                except (socket.timeout, BlockingIOError):
                    continue
                except (BrokenPipeError, ConnectionResetError, OSError):
                    print("[Target] Connessione persa.")
                    break
                except Exception as e:
                    print(f"[Target] Errore stream: {e}")
                    break


if __name__ == '__main__':
    # Modifica IP
    client = RemoteDesktopTarget('192.168.1.XX', port=9999)
    client.start()
