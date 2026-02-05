# server.py (REVERSE CONNECTION - TARGET)
import socket
import threading
import struct
import cv2
import mss
import numpy as np
import pyautogui
import time

# Configurazione Target (Il PC da controllare)
# Inserisci qui l'IP del TUO computer (dove hai lanciato client.py)
CONTROLLER_IP = '192.168.1.XX'  # <--- MODIFICA QUESTO IP
PORT = 9999

pyautogui.FAILSAFE = False


def handle_input(conn, screen_width, screen_height):
    """
    Riceve i comandi mouse dal controller
    """
    PAYLOAD_SIZE = struct.calcsize(">Bff")

    try:
        while True:
            data = conn.recv(PAYLOAD_SIZE)
            if not data:
                break

            event_type, norm_x, norm_y = struct.unpack(">Bff", data)

            real_x = int(norm_x * screen_width)
            real_y = int(norm_y * screen_height)

            if event_type == 0:
                pyautogui.moveTo(real_x, real_y, _pause=False)
            elif event_type == 1:
                pyautogui.click(real_x, real_y)

    except Exception:
        pass  # Thread muore silenziosamente se cade la connessione


def start_reverse_connection():
    screen_width, screen_height = pyautogui.size()

    while True:  # Loop di riconnessione automatica
        print(f"[Target] Tentativo di connessione verso {CONTROLLER_IP}:{PORT}...")

        try:
            # Tenta di connettersi al controller (Reverse Connection)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((CONTROLLER_IP, PORT))
            print("[Target] Connesso al controller!")

            # Avvia gestione input mouse
            input_thread = threading.Thread(target=handle_input, args=(s, screen_width, screen_height))
            input_thread.daemon = True
            input_thread.start()

            # Ciclo invio schermo
            with mss.mss() as sct:
                monitor = sct.monitors[1]

                while True:
                    img = sct.grab(monitor)
                    frame = np.array(img)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
                    result, encoded_img = cv2.imencode('.jpg', frame, encode_param)

                    if not result:
                        continue

                    data = encoded_img.tobytes()
                    size = len(data)

                    # Invia dimensione + immagine
                    s.sendall(struct.pack(">L", size) + data)

        except (ConnectionRefusedError, TimeoutError) as e:
            print(f"[Target] Connessione fallita: {e}")
        except (ConnectionResetError, BrokenPipeError):
            print("[Target] Connessione persa.")
        except Exception as e:
            print(f"[Target] Errore imprevisto: {e}")
        finally:
            try:
                s.close()
            except:
                pass

            # Attendi prima di riprovare (utile se il controller non è ancora pronto)
            print("[Target] Riprovo tra 5 secondi...")
            time.sleep(5)


if __name__ == '__main__':
    start_reverse_connection()
