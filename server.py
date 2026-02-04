import socket
import threading
import struct
import cv2
import mss
import numpy as np
import pyautogui

# Configurazione Server
HOST = '0.0.0.0'  # Ascolta su tutte le interfacce di rete
PORT = 9999

# Disabilita il failsafe di PyAutoGUI per permettere movimenti agli angoli
# ATTENZIONE: Usa con cautela durante i test
pyautogui.FAILSAFE = False


def handle_input(conn, screen_width, screen_height):
    """
    Thread dedicato alla ricezione dei comandi del mouse dal client.
    Riceve coordinate normalizzate (0.0-1.0) e le scala sulla risoluzione del server.
    """
    # Dimensione del pacchetto mouse: 1 byte (tipo) + 4 bytes (float x) + 4 bytes (float y) = 9 bytes
    PAYLOAD_SIZE = struct.calcsize(">Bff")

    try:
        while True:
            data = conn.recv(PAYLOAD_SIZE)
            if not data:
                break

            # Decodifica: Tipo evento, X normalizzato, Y normalizzato
            event_type, norm_x, norm_y = struct.unpack(">Bff", data)

            # Mappa le coordinate normalizzate (0-1) ai pixel reali dello schermo server
            real_x = int(norm_x * screen_width)
            real_y = int(norm_y * screen_height)

            # Esegui l'azione
            if event_type == 0:  # Movimento
                pyautogui.moveTo(real_x, real_y, _pause=False)
            elif event_type == 1:  # Click Sinistro
                pyautogui.click(real_x, real_y)

    except Exception as e:
        print(f"[Input Thread] Errore o disconnessione: {e}")


def start_server():
    # Ottieni la risoluzione dello schermo principale per il mapping
    screen_width, screen_height = pyautogui.size()
    print(f"[Server] Risoluzione Host: {screen_width}x{screen_height}")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(1)
    print(f"[Server] In ascolto su {HOST}:{PORT}...")

    conn, addr = s.accept()
    print(f"[Server] Connesso a {addr}")

    # Avvia il thread per gestire l'input del mouse parallelamente allo streaming video
    input_thread = threading.Thread(target=handle_input, args=(conn, screen_width, screen_height))
    input_thread.daemon = True  # Il thread muore se il programma principale termina
    input_thread.start()

    try:
        with mss.mss() as sct:
            # Definisci l'area di cattura (monitor 1)
            monitor = sct.monitors[1]

            while True:
                # 1. Screen Capture
                img = sct.grab(monitor)

                # Converti in formato numpy compatibile con OpenCV (BGRA -> BGR)
                frame = np.array(img)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                # 2. Compressione JPEG
                # quality=50 offre un buon compromesso tra velocità e qualità visiva
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
                result, encoded_img = cv2.imencode('.jpg', frame, encode_param)

                if not result:
                    continue

                data = encoded_img.tobytes()
                size = len(data)

                # 3. Networking: Invia Header (dimensione) + Payload (immagine)
                # ">L" = Big-Endian Unsigned Long (4 bytes)
                conn.sendall(struct.pack(">L", size) + data)

    except (ConnectionResetError, BrokenPipeError):
        print("[Server] Client disconnesso.")
    except Exception as e:
        print(f"[Server] Errore critico: {e}")
    finally:
        conn.close()
        s.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    start_server()
