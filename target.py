# target.py (SENDER - PC Controllato)
import socket
import threading
import struct
import cv2
import mss
import numpy as np
import pyautogui
import time

# --- MAPPING TASTI (Pygame int -> Pyautogui str) ---
# Pygame usa codici int (ASCII o custom), Pyautogui usa stringhe.
KEY_MAPPING = {
    8: 'backspace',
    9: 'tab',
    13: 'enter',
    27: 'esc',
    32: 'space',
    127: 'delete',
    1073742049: 'shift',  # Shift Sinistro (codici moderni SDL2)
    1073742053: 'shift',  # Shift Destro
    1073742048: 'ctrl',
    1073742052: 'ctrl',
    1073742050: 'alt',
    1073742054: 'alt',
    1073741906: 'up',
    1073741905: 'down',
    1073741904: 'left',
    1073741903: 'right',
    # Aggiungi altri tasti speciali se necessario (F1-F12, etc.)
}


def get_pyautogui_key(code):
    """Converte il codice intero di Pygame in stringa per Pyautogui."""
    # 1. Controlla mappatura speciale
    if code in KEY_MAPPING:
        return KEY_MAPPING[code]

    # 2. Prova ASCII (a-z, 0-9)
    # Pyautogui accetta 'a', 'b', ma Pygame invia il codice ASCII
    try:
        char = chr(code)
        if char.isalnum():  # Se è alfanumerico
            return char
    except ValueError:
        pass

    return None


class RemoteDesktopTarget:
    def __init__(self, controller_ip, port=9999):
        self.controller_ip = controller_ip
        self.port = port
        self.sock = None
        self.running = False
        pyautogui.FAILSAFE = False
        self.screen_w, self.screen_h = pyautogui.size()

    def _handle_input(self):
        """Thread ricezione input (Mouse + Tastiera)"""
        # Dimensione struct >Bff = 1 byte (type) + 4 (float) + 4 (float) = 9 bytes
        payload_size = struct.calcsize(">Bff")

        while self.running:
            try:
                data = self.sock.recv(payload_size)
                if not data: break

                # Unpack: event_type, val1, val2
                e_type, v1, v2 = struct.unpack(">Bff", data)

                # --- 0: MOUSE MOVE ---
                if e_type == 0:
                    real_x = int(v1 * self.screen_w)
                    real_y = int(v2 * self.screen_h)
                    pyautogui.moveTo(real_x, real_y, _pause=False)

                # --- 1: LEFT CLICK ---
                elif e_type == 1:
                    real_x = int(v1 * self.screen_w)
                    real_y = int(v2 * self.screen_h)
                    pyautogui.click(real_x, real_y, button='left')

                # --- 2: RIGHT CLICK ---
                elif e_type == 2:
                    real_x = int(v1 * self.screen_w)
                    real_y = int(v2 * self.screen_h)
                    pyautogui.click(real_x, real_y, button='right')

                # --- 3: SCROLL ---
                elif e_type == 3:
                    # v2 contiene la direzione (+1 o -1).
                    # Moltiplichiamo per fare uno scroll più deciso.
                    amount = int(v2 * 100)
                    pyautogui.scroll(amount)

                # --- 4: KEY DOWN ---
                elif e_type == 4:
                    key_code = int(v1)
                    key_str = get_pyautogui_key(key_code)
                    if key_str:
                        pyautogui.keyDown(key_str)

                # --- 5: KEY UP ---
                elif e_type == 5:
                    key_code = int(v1)
                    key_str = get_pyautogui_key(key_code)
                    if key_str:
                        pyautogui.keyUp(key_str)

            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Input] Errore: {e}")
                break

    def start(self):
        print(f"[Target] Avvio client verso {self.controller_ip}...")
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)
                self.sock.connect((self.controller_ip, self.port))
                self.sock.settimeout(0.5)

                print("[Target] Connesso!")
                self.running = True

                # Avvia thread input
                input_thread = threading.Thread(target=self._handle_input, daemon=True)
                input_thread.start()

                # Avvia stream schermo (blocca il main thread del loop)
                self._stream_screen()

            except socket.timeout:
                pass
            except OSError:
                pass
            except KeyboardInterrupt:
                print("\n[Target] Uscita.")
                self.running = False
                break
            finally:
                if self.running: self.running = False
                if self.sock: self.sock.close()

            time.sleep(2)

    def _stream_screen(self):
        with mss.mss() as sct:
            # Monitor 1 è solitamente "All monitors", Monitor 1 specifico è index 1?
            # mss index 0 = all, 1 = primo monitor. Usiamo 1.
            monitor = sct.monitors[1]
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]

            while self.running:
                try:
                    img = np.array(sct.grab(monitor))
                    # Rimuovi canale Alpha se presente per CV2
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    _, encoded_img = cv2.imencode('.jpg', img, encode_param)
                    data = encoded_img.tobytes()

                    self.sock.sendall(struct.pack(">L", len(data)) + data)

                except (socket.timeout, BlockingIOError):
                    continue
                except Exception:
                    break


if __name__ == '__main__':
    # Modifica qui l'IP del Controller
    TARGET_IP = '192.168.1.XX'
    client = RemoteDesktopTarget(TARGET_IP, port=9999)
    client.start()
