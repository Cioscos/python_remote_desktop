# controller.py (LISTENER - Visualizzatore) - CustomTkinter
import socket
import struct
import io
import threading
import hashlib
import ssl
import time
import customtkinter as ctk
from tkinter import messagebox
from PIL import Image
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FUNCTION_KEY_MAPPING = {
    'Return': 'enter', 'BackSpace': 'backspace', 'Tab': 'tab', 'space': 'space',
    'Escape': 'esc', 'Delete': 'delete', 'Home': 'home', 'End': 'end',
    'Prior': 'pageup', 'Next': 'pagedown', 'Up': 'up', 'Down': 'down',
    'Left': 'left', 'Right': 'right',
    'F1': 'f1', 'F2': 'f2', 'F3': 'f3', 'F4': 'f4', 'F5': 'f5', 'F6': 'f6',
    'F7': 'f7', 'F8': 'f8', 'F9': 'f9', 'F10': 'f10', 'F11': 'f11', 'F12': 'f12',
    'Control_L': 'ctrl', 'Control_R': 'ctrl',
    'Alt_L': 'alt', 'Alt_R': 'alt',
    'Shift_L': 'shift', 'Shift_R': 'shift',
    'Win_L': 'win', 'Win_R': 'win',
    'Caps_Lock': 'capslock',
    'Insert': 'insert', 'Print': 'printscreen', 'Scroll_Lock': 'scrolllock', 'Pause': 'pause',
    'Num_Lock': 'numlock'
}

SYMBOL_MAPPING = {
    'minus': '-', 'underscore': '-', 'equal': '=', 'plus': '=',
    'bracketleft': '[', 'braceleft': '[', 'bracketright': ']', 'braceright': ']',
    'semicolon': ';', 'colon': ';', 'apostrophe': "'", 'quotedbl': "'",
    'grave': '`', 'asciitilde': '`', 'backslash': '\\', 'bar': '\\',
    'comma': ',', 'less': ',', 'period': '.', 'greater': '.', 'slash': '/', 'question': '/',
    'exclam': '1', 'at': '2', 'numbersign': '3', 'dollar': '4', 'percent': '5',
    'asciicircum': '6', 'ampersand': '7', 'asterisk': '8', 'parenleft': '9', 'parenright': '0'
}

CURSOR_MAPPING = {
    0: "arrow", 1: "xterm", 2: "hand2", 3: "watch",
    4: "cross", 5: "sb_v_double_arrow", 6: "sb_h_double_arrow"
}


class RemoteDesktopController:
    def __init__(self):
        self.sock = None
        self.conn = None
        self.running = False
        self.password = None
        self.use_ssl = False

        # debounce variables
        self.resize_timer = None
        self.auto_resize_enabled = False

        # Statistics
        self.frame_count = 0
        self.last_fps_update = time.time()
        self.current_fps = 0
        self.last_frame_time = time.time()
        self.current_latency = 0

        # Clipboard
        self.last_clipboard = ""
        self.clipboard_thread = None

        # Dimensione Iniziale Finestra
        self.win_w, self.win_h = 1280, 720

        self.pressed_keys = set()
        self.key_map = {}

        # CustomTkinter setup
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Full Control Remote Desktop - High Quality")
        self.root.geometry(f"{self.win_w}x{self.win_h}")

        self.is_fullscreen = False

        # Label video
        self.lbl = ctk.CTkLabel(self.root, text="", fg_color="black", cursor="arrow")
        self.lbl.pack(fill="both", expand=True)

        # Status indicator
        self.status_label = ctk.CTkLabel(
            self.root,
            text="● Disconnesso",
            text_color="red",
            font=("Arial", 12, "bold")
        )
        self.status_label.place(x=10, y=10)

        # Statistics label
        self.stats_label = ctk.CTkLabel(
            self.root,
            text="FPS: 0 | Latency: 0ms",
            font=("Arial", 10)
        )
        self.stats_label.place(relx=1.0, x=-10, y=10, anchor="ne")

        self.btn_fullscreen = ctk.CTkButton(
            self.root,
            text="Attiva Fullscreen",
            command=self._toggle_fullscreen,
            fg_color="red",
            bg_color="transparent",
            height=30,
            width=150
        )
        self.btn_fullscreen.bind("<Enter>", lambda e: self.btn_fullscreen.place(relx=0.5, y=10, anchor="n"))

        self.lbl.bind("<Motion>", self._on_mouse_move_wrapper)
        self.lbl.bind("<ButtonPress-1>", lambda e: self._send_mouse_action(1, 1, e))
        self.lbl.bind("<ButtonRelease-1>", lambda e: self._send_mouse_action(2, 1, e))
        self.lbl.bind("<ButtonPress-3>", lambda e: self._send_mouse_action(1, 3, e))
        self.lbl.bind("<ButtonRelease-3>", lambda e: self._send_mouse_action(2, 3, e))
        self.lbl.bind("<ButtonPress-2>", lambda e: self._send_mouse_action(1, 2, e))
        self.lbl.bind("<ButtonRelease-2>", lambda e: self._send_mouse_action(2, 2, e))

        self.root.bind("<MouseWheel>", self._send_scroll)
        self.root.bind("<Button-4>", lambda e: self._send_scroll(e, 1))
        self.root.bind("<Button-5>", lambda e: self._send_scroll(e, -1))

        self.root.bind("<KeyPress>", lambda e: self._send_key(4, e))
        self.root.bind("<KeyRelease>", lambda e: self._send_key(5, e))

        self.root.bind("<Configure>", self._on_resize)
        self.root.bind("<FocusOut>", self._on_focus_out)
        self.root.bind("<Escape>", self._exit_fullscreen)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.focus_set()
        self._show_config_dialog()

    def _show_config_dialog(self):
        win = ctk.CTkToplevel(self.root)
        win.title("Config")
        win.geometry("380x380")
        win.transient(self.root)
        win.grab_set()

        ctk.CTkLabel(win, text="IP Ascolto:").pack(pady=(12, 2))
        e_ip = ctk.CTkEntry(win)
        e_ip.insert(0, "0.0.0.0")
        e_ip.pack(padx=12, fill="x")

        ctk.CTkLabel(win, text="Porta:").pack(pady=(10, 2))
        e_port = ctk.CTkEntry(win)
        e_port.insert(0, "9999")
        e_port.pack(padx=12, fill="x")

        ctk.CTkLabel(win, text="Password (lascia vuoto per nessuna auth):").pack(pady=(10, 2))
        e_pass = ctk.CTkEntry(win, show="*")
        e_pass.pack(padx=12, fill="x")

        # Checkbox SSL
        self.var_ssl = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            win,
            text="Usa SSL/TLS (richiede cert.pem e key.pem)",
            variable=self.var_ssl
        ).pack(pady=8, padx=12, anchor="w")

        # Checkbox auto-resize
        self.var_resize = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            win,
            text="Adatta Risoluzione Target (RDP Style)",
            variable=self.var_resize
        ).pack(pady=4, padx=12, anchor="w")

        # Checkbox clipboard sync
        self.var_clipboard = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            win,
            text="Sincronizza Clipboard",
            variable=self.var_clipboard
        ).pack(pady=4, padx=12, anchor="w")

        def start_server():
            ip = e_ip.get().strip() or "0.0.0.0"
            password = e_pass.get().strip()
            try:
                p = int(e_port.get().strip())
                should_resize = bool(self.var_resize.get())
                use_ssl = bool(self.var_ssl.get())
                use_clipboard = bool(self.var_clipboard.get())

                self.password = password if password else None
                self.use_ssl = use_ssl

                win.destroy()
                threading.Thread(target=self._server_loop, args=(ip, p, should_resize, use_clipboard),
                                 daemon=True).start()
            except ValueError:
                messagebox.showerror("Errore", "Porta non valida.")

        ctk.CTkButton(win, text="AVVIA", command=start_server).pack(pady=14)

    def _authenticate_client(self, conn):
        """Autentica il client con challenge-response"""
        if not self.password:
            return True

        try:
            import secrets
            challenge = secrets.token_hex(32)
            conn.sendall(challenge.encode())

            response = conn.recv(64)
            expected = hashlib.sha256((challenge + self.password).encode()).hexdigest()

            if response.decode() == expected:
                conn.sendall(b"OK")
                logger.info("Autenticazione riuscita")
                return True
            else:
                conn.sendall(b"FAIL")
                logger.warning("Autenticazione fallita")
                return False
        except Exception as e:
            logger.error(f"Errore autenticazione: {e}")
            return False

    def _server_loop(self, ip, port, auto_resize, use_clipboard):
        self.auto_resize_enabled = auto_resize

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # TCP_NODELAY per ridurre latenza
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # Buffer più grandi
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 512000)

        try:
            self.sock.bind((ip, port))
            self.sock.listen(1)
            logger.info(f"Listening on {ip}:{port}")
            self.running = True

            while self.running:
                try:
                    raw_conn, addr = self.sock.accept()
                    logger.info(f"Connection from {addr}")

                    # Wrap con SSL se abilitato
                    if self.use_ssl:
                        try:
                            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                            context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
                            self.conn = context.wrap_socket(raw_conn, server_side=True)
                            logger.info("SSL connection established")
                        except FileNotFoundError:
                            messagebox.showerror("Errore", "File cert.pem o key.pem non trovati!")
                            raw_conn.close()
                            continue
                        except Exception as e:
                            logger.error(f"SSL error: {e}")
                            raw_conn.close()
                            continue
                    else:
                        self.conn = raw_conn

                    # Autenticazione
                    if not self._authenticate_client(self.conn):
                        self.conn.close()
                        continue

                    self.pressed_keys.clear()
                    self._update_status("Connesso", "green")

                    if self.auto_resize_enabled:
                        threading.Timer(0.5, self._send_resolution_command).start()

                    # Avvia clipboard sync se abilitato
                    if use_clipboard:
                        self.clipboard_thread = threading.Thread(target=self._clipboard_monitor, daemon=True)
                        self.clipboard_thread.start()

                    # Reset statistiche
                    self.frame_count = 0
                    self.last_fps_update = time.time()

                    while self.running:
                        frame_start = time.time()

                        header = self._recvall(5)
                        if not header:
                            break
                        img_size, cursor_id = struct.unpack(">LB", header)

                        self._update_cursor(cursor_id)

                        data = self._recvall(img_size)
                        if not data:
                            break

                        try:
                            img = Image.open(io.BytesIO(data)).convert("RGB")
                            if self.win_w > 10 and self.win_h > 10:
                                img = img.resize((self.win_w, self.win_h), Image.Resampling.BILINEAR)
                            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(self.win_w, self.win_h))
                            self.lbl.configure(image=ctk_img, text="")
                            self.lbl.image = ctk_img

                            # Aggiorna statistiche
                            self.frame_count += 1
                            self.current_latency = int((time.time() - frame_start) * 1000)
                            self._update_stats()
                        except:
                            pass

                    if self.conn:
                        self.conn.close()
                    logger.info("Disconnected")
                    self._update_status("Disconnesso", "red")
                except OSError:
                    break
                except Exception as e:
                    logger.error(f"Connection error: {e}")
                    time.sleep(1)  # Evita loop infinito
        except Exception as e:
            messagebox.showerror("Errore", f"Server: {e}")
            self._on_close()

    def _clipboard_monitor(self):
        """Monitora clipboard e sincronizza"""
        try:
            import pyperclip
            logger.info("Clipboard sync attivo")

            while self.running and self.conn:
                try:
                    current = pyperclip.paste()
                    if current and current != self.last_clipboard:
                        self._send_clipboard(current)
                        self.last_clipboard = current
                    time.sleep(0.5)
                except:
                    pass
        except ImportError:
            logger.warning("pyperclip non installato, clipboard sync disabilitato")

    def _send_clipboard(self, text):
        """Invia contenuto clipboard al target"""
        if not self.conn or not text:
            return
        try:
            encoded = text.encode('utf-8')
            # Tipo 7 = Clipboard
            self.conn.sendall(struct.pack(">BI", 7, len(encoded)) + encoded)
        except:
            pass

    def _update_status(self, text, color):
        """Aggiorna indicatore di stato"""
        try:
            self.status_label.configure(text=f"● {text}", text_color=color)
        except:
            pass

    def _update_stats(self):
        """Aggiorna statistiche FPS e latenza"""
        now = time.time()
        elapsed = now - self.last_fps_update

        if elapsed >= 1.0:
            self.current_fps = int(self.frame_count / elapsed)
            self.frame_count = 0
            self.last_fps_update = now

            try:
                self.stats_label.configure(
                    text=f"FPS: {self.current_fps} | Latency: {self.current_latency}ms"
                )
            except:
                pass

    def _send_resolution_command(self):
        """Invia al target il comando per cambiare risoluzione."""
        if not self.conn:
            return
        try:
            w, h = self.win_w, self.win_h
            logger.info(f"Richiesta cambio risoluzione remota a: {w}x{h}")
            self.conn.sendall(struct.pack(">BII", 6, w, h))
        except:
            pass

    def _recvall(self, n):
        data = b''
        while len(data) < n:
            try:
                chunk = self.conn.recv(n - len(data))
                if not chunk:
                    return None
                data += chunk
            except:
                return None
        return data

    def _update_cursor(self, cursor_id):
        cursor_name = CURSOR_MAPPING.get(cursor_id, "arrow")
        if self.lbl.cget("cursor") != cursor_name:
            self.lbl.configure(cursor=cursor_name)

    def _get_norm_coords(self, event):
        if self.win_w <= 0 or self.win_h <= 0:
            return 0.0, 0.0
        return (
            max(0.0, min(1.0, event.x / self.win_w)),
            max(0.0, min(1.0, event.y / self.win_h))
        )

    def _send_mouse_move(self, event):
        if not self.conn:
            return
        nx, ny = self._get_norm_coords(event)
        try:
            self.conn.sendall(struct.pack(">Bff", 0, nx, ny))
        except:
            pass

    def _send_mouse_action(self, atype, btn, event):
        if not self.conn:
            return
        nx, ny = self._get_norm_coords(event)
        try:
            self.conn.sendall(struct.pack(">BBff", atype, btn, nx, ny))
        except:
            pass

    def _send_scroll(self, event, linux_delta=0):
        if not self.conn:
            return
        amt = linux_delta * 50 if linux_delta != 0 else int(getattr(event, "delta", 0) / 2)
        try:
            self.conn.sendall(struct.pack(">Bi", 3, amt))
        except:
            pass

    def _send_key(self, action_type, event):
        if not self.conn:
            return
        keysym = event.keysym
        py_key = None

        if action_type == 4:
            if keysym in FUNCTION_KEY_MAPPING:
                py_key = FUNCTION_KEY_MAPPING[keysym]
            elif keysym in SYMBOL_MAPPING:
                py_key = SYMBOL_MAPPING[keysym]
            elif len(keysym) == 1:
                py_key = keysym.lower()

            if not py_key:
                return

            is_modifier = py_key in ['ctrl', 'alt', 'shift', 'win', 'capslock']
            if is_modifier:
                if py_key in self.pressed_keys:
                    return
                self.pressed_keys.add(py_key)
            else:
                self.key_map[keysym] = py_key

        elif action_type == 5:
            if keysym in FUNCTION_KEY_MAPPING:
                py_key = FUNCTION_KEY_MAPPING[keysym]
            elif keysym in SYMBOL_MAPPING:
                py_key = SYMBOL_MAPPING[keysym]
            elif len(keysym) == 1:
                py_key = keysym.lower()
            else:
                py_key = self.key_map.pop(keysym, None)

            if not py_key:
                return
            self.pressed_keys.discard(py_key)

        encoded = py_key.encode('utf-8')
        try:
            self.conn.sendall(struct.pack(">BB", action_type, len(encoded)) + encoded)
        except:
            pass

    def _on_focus_out(self, event):
        if not self.conn:
            return
        modifiers = ['ctrl', 'alt', 'shift', 'win']
        for k in modifiers:
            if k in self.pressed_keys:
                enc = k.encode('utf-8')
                try:
                    self.conn.sendall(struct.pack(">BB", 5, len(enc)) + enc)
                except:
                    pass
        self.pressed_keys.clear()

    def _on_resize(self, event):
        if event.widget == self.root:
            self.win_w, self.win_h = event.width, event.height

            if self.running and self.conn and self.auto_resize_enabled:
                if self.resize_timer is not None:
                    self.resize_timer.cancel()

                self.resize_timer = threading.Timer(1.0, self._send_resolution_command)
                self.resize_timer.start()

    def _on_close(self):
        self.running = False
        if self.sock:
            self.sock.close()
        try:
            self.root.destroy()
        except:
            pass
        import sys
        sys.exit(0)

    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)

        if self.is_fullscreen:
            self.btn_fullscreen.configure(text="Esci da Fullscreen")
        else:
            self.btn_fullscreen.configure(text="Attiva Fullscreen")

        self.root.focus_set()

    def _exit_fullscreen(self, event=None):
        """Metodo di sicurezza: ESC esce dal fullscreen se attivo"""
        if self.is_fullscreen:
            self._toggle_fullscreen()

    def _on_mouse_move_wrapper(self, event):
        """Wrapper che gestisce sia l'invio dati remoto che la UI locale"""
        if event.y < 50:
            self.btn_fullscreen.place(relx=0.5, y=10, anchor="n")
            self.btn_fullscreen.lift()
        else:
            self.btn_fullscreen.place_forget()

        self._send_mouse_move(event)

    def start(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = RemoteDesktopController()
    app.start()
