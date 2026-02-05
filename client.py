# client.py (REVERSE CONNECTION - CONTROLLER)
import socket
import struct
import cv2
import numpy as np

# Configurazione Client (Controller)
# '0.0.0.0' significa "ascolta su tutte le mie schede di rete"
BIND_IP = '0.0.0.0'
PORT = 9999

# Variabili globali per gestire la connessione nel callback del mouse
connection_socket = None
window_width = 1
window_height = 1


def send_mouse_event(event_type, x, y):
    """
    Invia le coordinate al PC remoto.
    event_type: 0 = Move, 1 = Click
    """
    if connection_socket:
        try:
            # Coordinate Mapping: Normalizzazione (0.0 - 1.0)
            norm_x = x / window_width
            norm_y = y / window_height

            # Packing: Tipo (Byte), X (Float), Y (Float)
            payload = struct.pack(">Bff", event_type, norm_x, norm_y)
            connection_socket.sendall(payload)
        except Exception:
            pass  # Ignora errori mouse per fluidità video


def mouse_callback(event, x, y, flags, param):
    """
    Intercetta gli eventi mouse di OpenCV
    """
    if event == cv2.EVENT_MOUSEMOVE:
        send_mouse_event(0, x, y)
    elif event == cv2.EVENT_LBUTTONDOWN:
        send_mouse_event(1, x, y)


def recvall(sock, n):
    """
    Assicura di ricevere esattamente 'n' byte
    """
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data


def start_listener():
    global connection_socket, window_width, window_height

    # Creazione socket in ascolto (Server-side logic sul controller)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((BIND_IP, PORT))
        listener.listen(1)
        print(f"[Controller] In ascolto su {BIND_IP}:{PORT}...")
        print("[Controller] In attesa che il PC remoto si connetta...")

        # Accetta la connessione in entrata dal PC remoto
        connection_socket, addr = listener.accept()
        print(f"[Controller] Connessione ricevuta da {addr}")

    except Exception as e:
        print(f"[Controller] Errore bind/listen: {e}")
        return

    cv2.namedWindow("Reverse Remote Desktop")
    cv2.setMouseCallback("Reverse Remote Desktop", mouse_callback)

    try:
        while True:
            # 1. Ricezione Header (4 bytes size)
            header_data = recvall(connection_socket, 4)
            if not header_data:
                break

            msg_size = struct.unpack(">L", header_data)[0]

            # 2. Ricezione Payload (Immagine JPEG)
            frame_data = recvall(connection_socket, msg_size)
            if not frame_data:
                break

            # 3. Decodifica e Display
            np_data = np.frombuffer(frame_data, dtype=np.uint8)
            frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

            if frame is not None:
                window_height, window_width = frame.shape[:2]
                cv2.imshow("Reverse Remote Desktop", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except Exception as e:
        print(f"[Controller] Errore: {e}")
    finally:
        if connection_socket:
            connection_socket.close()
        listener.close()
        cv2.destroyAllWindows()
        print("[Controller] Sessione terminata.")


if __name__ == '__main__':
    start_listener()
