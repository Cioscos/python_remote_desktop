# target.py (SENDER - PC Controllato) - H.264 Streaming + Adaptive Bitrate + Full Features
"""
Modulo per lo streaming desktop remoto con encoding H.264 e controllo adattivo della qualità.
Combina compressione hardware-accelerated con gestione dinamica della risoluzione e input.
"""

import socket
import threading
import struct
import cv2
import mss
import numpy as np
import pyautogui
import time
import hashlib
import ssl
import customtkinter as ctk
import win32gui
import win32con
import win32api
import logging
import av  # Richiede: pip install av

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0


# === GESTIONE RISOLUZIONE ===
class ResolutionManager:
    """
    Gestisce il cambio e ripristino della risoluzione dello schermo.
    Salva la configurazione originale per ripristinarla alla disconnessione.
    """

    def __init__(self):
        """Inizializza il manager senza modificare la risoluzione corrente."""
        self.original_devmode = None
        self.current_width = 0
        self.current_height = 0

    def save_current(self):
        """
        Salva la risoluzione attuale del display per il ripristino successivo.
        Deve essere chiamata prima di qualsiasi modifica.
        """
        self.original_devmode = win32api.EnumDisplaySettings(None, win32con.ENUM_CURRENT_SETTINGS)
        self.current_width = self.original_devmode.PelsWidth
        self.current_height = self.original_devmode.PelsHeight
        logger.info(f"Risoluzione originale salvata: {self.current_width}x{self.current_height}")

    def change_resolution(self, width, height):
        """
        Tenta di cambiare la risoluzione dello schermo.

        Args:
            width (int): Larghezza desiderata in pixel
            height (int): Altezza desiderata in pixel

        Returns:
            bool: True se il cambio è riuscito, False altrimenti
        """
        if not self.original_devmode:
            self.save_current()

        if width == self.current_width and height == self.current_height:
            return True

        devmode = win32api.EnumDisplaySettings(None, win32con.ENUM_CURRENT_SETTINGS)
        devmode.PelsWidth = width
        devmode.PelsHeight = height
        devmode.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT

        try:
            # Test della compatibilità prima di applicare
            res = win32api.ChangeDisplaySettings(devmode, win32con.CDS_TEST)
            if res != win32con.DISP_CHANGE_SUCCESSFUL:
                logger.warning(f"Risoluzione {width}x{height} non supportata.")
                return False

            # Applicazione effettiva
            win32api.ChangeDisplaySettings(devmode, 0)
            self.current_width = width
            self.current_height = height
            logger.info(f"Risoluzione cambiata a {width}x{height}")
            return True
        except Exception as e:
            logger.error(f"Errore cambio risoluzione: {e}")
            return False

    def restore(self):
        """Ripristina la risoluzione originale salvata."""
        if self.original_devmode:
            logger.info("Ripristino risoluzione originale...")
            win32api.ChangeDisplaySettings(self.original_devmode, 0)


# === GESTIONE CURSORE ===
SYSTEM_CURSORS = {
    win32gui.LoadCursor(0, win32con.IDC_ARROW): 0,
    win32gui.LoadCursor(0, win32con.IDC_IBEAM): 1,
    win32gui.LoadCursor(0, win32con.IDC_HAND): 2,
    win32gui.LoadCursor(0, win32con.IDC_WAIT): 3,
    win32gui.LoadCursor(0, win32con.IDC_CROSS): 4,
    win32gui.LoadCursor(0, win32con.IDC_SIZENS): 5,
    win32gui.LoadCursor(0, win32con.IDC_SIZEWE): 6
}


def get_current_cursor_id():
    """
    Ottiene l'ID del cursore attualmente visualizzato.

    Returns:
        int: ID del cursore (0-6), 0 se non riconosciuto
    """
    try:
        info = win32gui.GetCursorInfo()
        return SYSTEM_CURSORS.get(info[1], 0)
    except:
        return 0


class RemoteDesktopTarget:
    """
    Classe principale per lo streaming desktop con encoding H.264 e controllo remoto.
    Gestisce cattura schermo, compressione video, invio rete e ricezione comandi input.
    """

    def __init__(self, controller_ip, port=9999, password=None, use_ssl=False, target_fps=30):
        """
        Inizializza il target del desktop remoto.

        Args:
            controller_ip (str): Indirizzo IP del controller
            port (int): Porta di connessione (default: 9999)
            password (str): Password per autenticazione (None per disabilitare)
            use_ssl (bool): Abilita crittografia SSL/TLS
            target_fps (int): Frame rate target per lo streaming
        """
        self.controller_ip = controller_ip
        self.port = port
        self.password = password
        self.use_ssl = use_ssl
        self.sock = None
        self.running = False
        self.res_manager = ResolutionManager()
        self.res_manager.save_current()

        # Frame rate limiter
        self.target_fps = target_fps
        self.frame_time = 1.0 / target_fps

        # Clipboard tracking
        self.last_clipboard = ""

        # Adaptive Quality Settings per H.264
        self.base_bitrate = 2000000  # 2 Mbps di partenza
        self.min_bitrate = 200000  # 200 Kbps minimo
        self.max_bitrate = 8000000  # 8 Mbps massimo
        self.current_bitrate = self.base_bitrate
        self.congestion_window = 0

    def _authenticate_with_server(self, sock):
        """
        Esegue autenticazione challenge-response con il server.

        Args:
            sock (socket): Socket di connessione

        Returns:
            bool: True se autenticato, False altrimenti
        """
        if not self.password:
            return True

        try:
            # Ricevi challenge dal server
            challenge = sock.recv(64).decode()
            # Calcola risposta hash
            response = hashlib.sha256((challenge + self.password).encode()).hexdigest()
            sock.sendall(response.encode())

            # Attendi conferma
            result = sock.recv(4).decode()
            if result == "OK":
                logger.info("Autenticazione riuscita")
                return True
            else:
                logger.error("Autenticazione fallita")
                return False
        except Exception as e:
            logger.error(f"Errore autenticazione: {e}")
            return False

    def _handle_input(self):
        """
        Thread per la gestione degli eventi di input ricevuti dal controller.
        Processa mouse, tastiera, risoluzione e clipboard in modo asincrono.
        """
        while self.running:
            try:
                # Leggi tipo evento
                header = self._recvall(1)
                if not header:
                    break
                event_type = struct.unpack(">B", header)[0]

                screen_w, screen_h = pyautogui.size()

                if event_type == 0:  # MOVE
                    data = self._recvall(8)
                    nx, ny = struct.unpack(">ff", data)
                    pyautogui.moveTo(int(nx * screen_w), int(ny * screen_h), _pause=False)

                elif event_type in [1, 2]:  # MOUSE DOWN/UP
                    data = self._recvall(9)
                    btn, nx, ny = struct.unpack(">Bff", data)
                    x, y = int(nx * screen_w), int(ny * screen_h)
                    btn_s = {1: 'left', 2: 'middle', 3: 'right'}.get(btn, 'left')
                    if event_type == 1:
                        pyautogui.mouseDown(x, y, button=btn_s)
                    else:
                        pyautogui.mouseUp(x, y, button=btn_s)

                elif event_type == 3:  # SCROLL
                    data = self._recvall(4)
                    pyautogui.scroll(struct.unpack(">i", data)[0])

                elif event_type in [4, 5]:  # KEY DOWN/UP
                    l_byte = self._recvall(1)
                    if not l_byte:
                        break
                    k_len = struct.unpack(">B", l_byte)[0]
                    key = self._recvall(k_len).decode('utf-8')
                    if event_type == 4:
                        pyautogui.keyDown(key)
                    else:
                        pyautogui.keyUp(key)

                elif event_type == 6:  # RISOLUZIONE
                    data = self._recvall(8)
                    w, h = struct.unpack(">II", data)
                    logger.info(f"Richiesta cambio risoluzione: {w}x{h}")
                    success = self.res_manager.change_resolution(w, h)
                    if success:
                        # Riavvia encoder con nuova risoluzione
                        logger.info("Risoluzione cambiata, restart stream necessario")

                elif event_type == 7:  # CLIPBOARD
                    data = self._recvall(4)
                    text_len = struct.unpack(">I", data)[0]
                    text = self._recvall(text_len).decode('utf-8')
                    try:
                        import pyperclip
                        pyperclip.copy(text)
                        self.last_clipboard = text
                        logger.info("Clipboard sincronizzato dal controller")
                    except ImportError:
                        logger.warning("pyperclip non installato, clipboard non disponibile")

            except Exception as e:
                logger.error(f"Input handler error: {e}")
                break

    def start(self):
        """
        Avvia la connessione al controller e inizia lo streaming.
        Gestisce riconnessione automatica in caso di errore.
        """
        logger.info(f"Connessione a {self.controller_ip}:{self.port}")
        retry_delay = 2

        while True:
            try:
                # Creazione socket con ottimizzazioni
                raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # TCP_NODELAY per ridurre latenza
                raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                # Buffer più grande per H.264
                #raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)  # 1MB

                raw_sock.connect((self.controller_ip, self.port))

                # Wrap SSL se richiesto
                if self.use_ssl:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    self.sock = context.wrap_socket(raw_sock)
                    logger.info("SSL connection established")
                else:
                    self.sock = raw_sock

                # Autenticazione
                if not self._authenticate_with_server(self.sock):
                    self.sock.close()
                    time.sleep(retry_delay)
                    continue

                self.running = True
                logger.info("Connesso! Avvio H.264 streaming...")

                # Avvia thread input
                threading.Thread(target=self._handle_input, daemon=True).start()

                # Stream principale
                self._stream_h264()

            except ConnectionRefusedError:
                logger.warning(f"Connessione rifiutata, riprovo tra {retry_delay}s...")
                time.sleep(retry_delay)
            except Exception as e:
                logger.error(f"Errore: {e}")
                time.sleep(retry_delay)
            except KeyboardInterrupt:
                logger.info("Interruzione utente")
                break
            finally:
                self.running = False
                if self.sock:
                    self.sock.close()
                self.res_manager.restore()

    def _recvall(self, n):
        """
        Riceve esattamente n bytes dal socket.

        Args:
            n (int): Numero di bytes da ricevere

        Returns:
            bytes: Dati ricevuti o None se connessione chiusa
        """
        data = b''
        while len(data) < n and self.running:
            try:
                chunk = self.sock.recv(n - len(data))
                if not chunk:
                    return None
                data += chunk
            except:
                return None
        return data

    def _stream_h264(self):
        """
        Loop principale di streaming con encoding H.264 e adaptive bitrate.
        Utilizza PyAV per compressione hardware-accelerated quando disponibile.
        """
        # Setup H.264 Encoder
        # 'libx264' per CPU, 'h264_nvenc' per GPU NVIDIA, 'h264_qsv' per Intel QuickSync
        codec_name = 'libx264'

        try:
            # Container fittizio per gestire il codec
            container = av.open('pipe:', format='h264', mode='w')
            stream = container.add_stream(codec_name, rate=self.target_fps)
            stream.width = self.res_manager.current_width
            stream.height = self.res_manager.current_height
            stream.pix_fmt = 'yuv420p'
            stream.bit_rate = self.current_bitrate

            # Opzioni CRITICHE per bassa latenza
            stream.options = {
                'preset': 'ultrafast',  # Velocità encoding massima
                'tune': 'zerolatency',  # Minimizza buffering
                'profile': 'baseline',  # Compatibilità massima
                'crf': '23'  # Qualità costante (0-51, lower=better)
            }

            logger.info(f"H.264 encoder inizializzato: {codec_name} @ {self.current_bitrate / 1000} kbps")
        except Exception as e:
            logger.error(f"Errore init codec H.264: {e}")
            logger.info("Fallback a JPEG compression")
            self._stream_jpeg_fallback()
            return

        with mss.mss() as sct:
            last_frame_time = time.time()

            while self.running:
                try:
                    # Frame rate limiter
                    elapsed = time.time() - last_frame_time
                    if elapsed < self.frame_time:
                        time.sleep(self.frame_time - elapsed)
                    last_frame_time = time.time()

                    # 1. Cattura Schermo
                    monitor = sct.monitors[1]
                    img = np.array(sct.grab(monitor))
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    # Gestione cambio risoluzione dinamico
                    h, w = img.shape[:2]
                    if w != stream.width or h != stream.height:
                        logger.warning(f"Risoluzione cambiata durante streaming: {w}x{h}")
                        # Ricrea stream (costoso ma necessario)
                        container.close()
                        container = av.open('pipe:', format='h264', mode='w')
                        stream = container.add_stream(codec_name, rate=self.target_fps)
                        stream.width = w
                        stream.height = h
                        stream.pix_fmt = 'yuv420p'
                        stream.bit_rate = self.current_bitrate
                        stream.options = {
                            'preset': 'ultrafast',
                            'tune': 'zerolatency',
                            'profile': 'baseline'
                        }

                    # 2. Conversione a VideoFrame PyAV
                    frame = av.VideoFrame.from_ndarray(img, format='bgr24')

                    # 3. Encoding H.264 (genera automaticamente I-frames e P-frames)
                    packets = stream.encode(frame)

                    # 4. Invio Pacchetti + Adaptive Quality
                    cid = get_current_cursor_id()

                    for packet in packets:
                        data = bytes(packet)

                        timestamp = time.time()

                        # Header: Length (4B) | Cursor (1B) | Timestamp (8B)
                        header = struct.pack(">LBd", len(data), cid, timestamp)

                        # Misura latenza invio per adaptive bitrate
                        send_start = time.time()
                        self.sock.sendall(header + data)
                        send_time = time.time() - send_start

                        # === LOGICA ADAPTIVE QUALITY ===
                        if send_time > 0.05:  # Più di 50ms = congestione
                            self.congestion_window += 1
                        else:
                            self.congestion_window = max(0, self.congestion_window - 1)

                        # Riduci bitrate se congestione persistente
                        if self.congestion_window > 5:
                            old_bitrate = self.current_bitrate
                            self.current_bitrate = max(self.min_bitrate, int(self.current_bitrate * 0.8))
                            stream.bit_rate = self.current_bitrate
                            self.congestion_window = 0
                            logger.info(f"Riduzione Bitrate: {old_bitrate / 1000} → {self.current_bitrate / 1000} kbps")

                        # Aumenta bitrate lentamente se rete libera
                        elif self.congestion_window == 0 and self.current_bitrate < self.max_bitrate:
                            self.current_bitrate = min(self.max_bitrate, int(self.current_bitrate * 1.01))
                            stream.bit_rate = self.current_bitrate

                except Exception as e:
                    logger.error(f"Stream error: {e}")
                    break

        # Cleanup
        try:
            container.close()
        except:
            pass

    def _stream_jpeg_fallback(self):
        """
        Modalità fallback con compressione JPEG se H.264 non disponibile.
        Meno efficiente ma garantisce compatibilità universale.
        """
        logger.info("Streaming in modalità JPEG fallback")
        encode_quality = 90

        with mss.mss() as sct:
            last_frame_time = time.time()

            while self.running:
                try:
                    # Frame rate limiter
                    elapsed = time.time() - last_frame_time
                    if elapsed < self.frame_time:
                        time.sleep(self.frame_time - elapsed)
                    last_frame_time = time.time()

                    monitor = sct.monitors[1]
                    img = np.array(sct.grab(monitor))
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    # Compressione JPEG
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), encode_quality]
                    _, enc_img = cv2.imencode('.jpg', img, encode_param)
                    data = enc_img.tobytes()

                    cid = get_current_cursor_id()
                    packet = struct.pack(">LB", len(data), cid) + data
                    self.sock.sendall(packet)

                except Exception as e:
                    logger.error(f"JPEG stream error: {e}")
                    break


def get_config_dialog():
    """
    Mostra dialog CustomTkinter per configurazione connessione.

    Returns:
        dict: Configurazione con chiavi ip, port, password, ssl, fps
    """
    config = {"ip": None, "port": None, "password": None, "ssl": False, "fps": 30}

    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Remote Desktop Target - Config")
    root.geometry("380x380")

    # IP Controller
    ctk.CTkLabel(root, text="Controller IP:", font=("Arial", 12, "bold")).pack(pady=(14, 2))
    e_ip = ctk.CTkEntry(root, width=300)
    e_ip.insert(0, "192.168.1.X")
    e_ip.pack(padx=12, fill="x")

    # Porta
    ctk.CTkLabel(root, text="Port:", font=("Arial", 12, "bold")).pack(pady=(10, 2))
    e_port = ctk.CTkEntry(root, width=300)
    e_port.insert(0, "9999")
    e_port.pack(padx=12, fill="x")

    # Password
    ctk.CTkLabel(root, text="Password (opzionale):", font=("Arial", 12, "bold")).pack(pady=(10, 2))
    e_pass = ctk.CTkEntry(root, show="*", width=300)
    e_pass.pack(padx=12, fill="x")

    # FPS Target
    ctk.CTkLabel(root, text="Target FPS:", font=("Arial", 12, "bold")).pack(pady=(10, 2))
    e_fps = ctk.CTkEntry(root, width=300)
    e_fps.insert(0, "30")
    e_fps.pack(padx=12, fill="x")

    # SSL Toggle
    var_ssl = ctk.BooleanVar(value=False)
    ctk.CTkCheckBox(root, text="Usa SSL/TLS", variable=var_ssl).pack(pady=8, padx=12, anchor="w")

    def on_connect():
        """Callback per il pulsante di connessione."""
        config["ip"] = e_ip.get().strip()
        config["port"] = int(e_port.get().strip())
        config["password"] = e_pass.get().strip() or None
        config["ssl"] = bool(var_ssl.get())
        config["fps"] = int(e_fps.get().strip())
        root.destroy()

    ctk.CTkButton(root, text="CONNECT", command=on_connect, height=40).pack(pady=14)

    root.mainloop()
    return config


if __name__ == '__main__':
    cfg = get_config_dialog()
    if cfg["ip"] and cfg["port"]:
        target = RemoteDesktopTarget(
            controller_ip=cfg["ip"],
            port=cfg["port"],
            password=cfg["password"],
            use_ssl=cfg["ssl"],
            target_fps=cfg["fps"]
        )
        target.start()
