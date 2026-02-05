# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import cv2
import numpy as np
import sys


class RemoteDesktopController:
    def __init__(self, bind_ip='0.0.0.0', port=9999):
        self.bind_ip = bind_ip
        self.port = port
        self.sock = None
        self.conn = None
        self.addr = None
        self.window_name = "Reverse Remote Desktop"
        self.running = False

    def _recvall(self, n):
        """
        Riceve esattamente n byte.
        Gestisce il timeout per permettere l'uscita pulita.
        """
        data = b''
        while len(data) < n:
            if not self.running:
                return None

            try:
                # Se il timeout scatta, recv lancia socket.timeout
                chunk = self.conn.recv(n - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                # Timeout scaduto: torniamo al while per ricontrollare self.running
                continue
            except OSError:
                return None
        return data

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Timeout anche sull'accept per non bloccare l'avvio se vuoi chiudere subito
        self.sock.settimeout(1.0)

        print(f"[Controller] In ascolto su {self.bind_ip}:{self.port}...")

        try:
            self.sock.bind((self.bind_ip, self.port))
            self.sock.listen(1)

            # Loop di attesa connessione che rispetta KeyboardInterrupt
            while True:
                try:
                    self.conn, self.addr = self.sock.accept()
                    # IMPORTANTE: Impostiamo timeout sulla connessione attiva
                    self.conn.settimeout(0.5)
                    print(f"[Controller] Connesso con {self.addr}")

                    self.running = True
                    self._loop_stream()
                    break  # Usciamo dopo la sessione (o togli break per accettare nuove connessioni)

                except socket.timeout:
                    continue  # Riprova accept
                except KeyboardInterrupt:
                    raise  # Rilancia al blocco esterno

        except KeyboardInterrupt:
            print("\n[Controller] Stop manuale ricevuto.")
        finally:
            self.cleanup()

    def _loop_stream(self):
        cv2.namedWindow(self.window_name)
        # Dummy callback per evitare errori se non definita
        cv2.setMouseCallback(self.window_name, lambda *args: None)

        while self.running:
            # Controllo chiusura finestra GUI
            try:
                if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                    print("[Controller] Finestra chiusa.")
                    self.running = False
                    break
            except:
                pass

            # 1. Ricezione Header
            header = self._recvall(4)
            if not header:
                break  # Connessione chiusa o stop richiesto

            msg_size = struct.unpack(">L", header)[0]

            # 2. Ricezione Immagine
            frame_data = self._recvall(msg_size)
            if not frame_data:
                break

            # 3. Display
            np_data = np.frombuffer(frame_data, dtype=np.uint8)
            frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

            if frame is not None:
                cv2.imshow(self.window_name, frame)

            # 4. Input Tastiera (Q per uscire)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.running = False

    def cleanup(self):
        self.running = False
        if self.conn: self.conn.close()
        if self.sock: self.sock.close()
        cv2.destroyAllWindows()
        print("[Controller] Terminato.")


if __name__ == '__main__':
    ctrl = RemoteDesktopController()
    ctrl.start()
