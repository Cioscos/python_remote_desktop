# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import cv2
import numpy as np


class RemoteDesktopController:
    def __init__(self, bind_ip='0.0.0.0', port=9999):
        self.bind_ip = bind_ip
        self.port = port
        self.sock = None
        self.conn = None
        self.addr = None
        self.window_name = "Reverse Remote Desktop"

        # Stato della finestra remota
        self.remote_width = 1
        self.remote_height = 1
        self.running = False

    def _recvall(self, n):
        """Helper per ricevere esattamente n byte."""
        data = b''
        while len(data) < n:
            try:
                packet = self.conn.recv(n - len(data))
                if not packet:
                    return None
                data += packet
            except OSError:
                return None
        return data

    def _send_mouse_event(self, event_type, x, y):
        """Invia evento mouse normalizzato al target."""
        if not self.conn:
            return

        try:
            # Normalizzazione 0.0 - 1.0
            norm_x = max(0.0, min(1.0, x / self.remote_width))
            norm_y = max(0.0, min(1.0, y / self.remote_height))

            # Payload: Type (1 byte), X (4 bytes float), Y (4 bytes float)
            payload = struct.pack(">Bff", event_type, norm_x, norm_y)
            self.conn.sendall(payload)
        except Exception:
            # Se la connessione cade durante il movimento mouse, ignoriamo l'errore momentaneo
            pass

    def _mouse_callback(self, event, x, y, flags, param):
        """Callback interno per OpenCV."""
        if event == cv2.EVENT_MOUSEMOVE:
            self._send_mouse_event(0, x, y)
        elif event == cv2.EVENT_LBUTTONDOWN:
            self._send_mouse_event(1, x, y)

    def start(self):
        """Avvia il listener e attende la connessione inversa."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.sock.bind((self.bind_ip, self.port))
            self.sock.listen(1)
            print(f"[Controller] In ascolto su {self.bind_ip}:{self.port}...")
            print("[Controller] In attesa del Target (Reverse Shell)...")

            self.conn, self.addr = self.sock.accept()
            print(f"[Controller] Connesso con {self.addr}")
            self.running = True
            self._loop_stream()

        except KeyboardInterrupt:
            print("\n[Controller] Interrotto dall'utente.")
        except Exception as e:
            print(f"[Controller] Errore critico: {e}")
        finally:
            self.cleanup()

    def _loop_stream(self):
        """Ciclo principale di ricezione video e gestione GUI."""
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        while self.running:
            # 1. Controllo se la finestra è stata chiusa con la "X"
            # WND_PROP_VISIBLE restituisce 0 se la finestra è chiusa
            try:
                if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                    print("[Controller] Finestra chiusa dall'utente.")
                    break
            except:
                pass  # Ignora errori se la finestra non è ancora pronta

            # 2. Ricezione Header
            header = self._recvall(4)
            if not header:
                print("[Controller] Il Target ha chiuso la connessione.")
                break

            msg_size = struct.unpack(">L", header)[0]

            # 3. Ricezione Body (Immagine)
            frame_data = self._recvall(msg_size)
            if not frame_data:
                break

            # 4. Decodifica
            np_data = np.frombuffer(frame_data, dtype=np.uint8)
            frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

            if frame is not None:
                # Aggiorniamo le dimensioni per il calcolo del mouse
                self.remote_height, self.remote_width = frame.shape[:2]
                cv2.imshow(self.window_name, frame)

            # 5. Controllo tasto 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[Controller] Chiusura richiesta tramite tasto 'Q'.")
                break

    def cleanup(self):
        """Chiude risorse e socket."""
        self.running = False
        if self.conn:
            self.conn.close()
        if self.sock:
            self.sock.close()
        cv2.destroyAllWindows()
        print("[Controller] Risorse rilasciate. Bye!")


if __name__ == '__main__':
    server = RemoteDesktopController(port=9999)
    server.start()
