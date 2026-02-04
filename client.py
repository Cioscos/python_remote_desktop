import socket
import struct
import cv2
import numpy as np

# Configurazione Client
SERVER_IP = '127.0.0.1'  # CAMBIARE CON L'IP DEL SERVER REALE
PORT = 9999

# Variabili globali per gestire la connessione nel callback del mouse
client_socket = None
window_width = 1
window_height = 1


def send_mouse_event(event_type, x, y):
    """
    Invia le coordinate al server.
    event_type: 0 = Move, 1 = Click
    x, y: coordinate assolute nella finestra client
    """
    if client_socket:
        try:
            # Coordinate Mapping: Normalizzazione (0.0 - 1.0)
            # Questo rende il client indipendente dalla risoluzione reale del server
            norm_x = x / window_width
            norm_y = y / window_height

            # Packing: Tipo (Byte), X (Float), Y (Float)
            payload = struct.pack(">Bff", event_type, norm_x, norm_y)
            client_socket.sendall(payload)
        except Exception:
            pass  # Ignora errori di invio mouse per non bloccare il video


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
    Funzione helper fondamentale per TCP.
    Assicura di ricevere esattamente 'n' byte, gestendo la frammentazione dei pacchetti.
    """
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data


def start_client():
    global client_socket, window_width, window_height

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect((SERVER_IP, PORT))
        print(f"[Client] Connesso a {SERVER_IP}")
    except ConnectionRefusedError:
        print("[Client] Impossibile connettersi al server.")
        return

    cv2.namedWindow("Remote Desktop")
    cv2.setMouseCallback("Remote Desktop", mouse_callback)

    try:
        while True:
            # 1. Ricezione Header (4 bytes per la dimensione del frame)
            header_data = recvall(client_socket, 4)
            if not header_data:
                break

            # Unpack della dimensione (Big Endian Long)
            msg_size = struct.unpack(">L", header_data)[0]

            # 2. Ricezione Payload (Dati Immagine JPEG)
            frame_data = recvall(client_socket, msg_size)
            if not frame_data:
                break

            # 3. Decodifica e Display
            # Converti i byte in array numpy
            np_data = np.frombuffer(frame_data, dtype=np.uint8)
            # Decodifica JPEG in immagine OpenCV
            frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

            if frame is not None:
                # Aggiorna le dimensioni correnti della finestra per il calcolo del mouse
                window_height, window_width = frame.shape[:2]

                cv2.imshow("Remote Desktop", frame)

            # Premi 'q' per uscire
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except Exception as e:
        print(f"[Client] Errore: {e}")
    finally:
        client_socket.close()
        cv2.destroyAllWindows()
        print("[Client] Sessione terminata.")


if __name__ == '__main__':
    start_client()
