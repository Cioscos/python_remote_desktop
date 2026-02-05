# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import io
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

# Mappatura Tasti Standard
KEY_MAPPING = {
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
    'Caps_Lock': 'capslock'
}

# Mappatura Inversa per i simboli (Shift attivi)
# Se Tkinter rileva '@', noi inviamo '2' perché lo 'shift' viene inviato separatamente
SHIFT_MAPPING = {
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
    '_': '-', '+': '=', '{': '[', '}': ']', ':': ';', '"': "'", '<': ',', '>': '.', '?': '/', '|': '\\', '~': '`'
}

# Mappatura Cursori (ID ricevuto -> Nome cursore Tkinter)
CURSOR_MAPPING = {
    0: "arrow",  # Default
    1: "xterm",  # IBeam (Testo)
    2: "hand2",  # Hand (Link)
    3: "watch",  # Wait
    4: "cross",  # Crosshair
    5: "sb_v_double_arrow",  # Resize NS
    6: "sb_h_double_arrow"  # Resize WE
}


class RemoteDesktopController:
    def __init__(self):
        self.sock = None
        self.conn = None
        self.running = False
        self.win_w, self.win_h = 800, 600

        self.pressed_keys = set()
        self.key_map = {}  # Associa keysym -> tasto inviato

        self.root = tk.Tk()
        self.root.title("Full Control Remote Desktop - Enhanced")
        self.root.geometry(f"{self.win_w}x{self.win_h}")

        self.lbl = tk.Label(self.root, bg="black", cursor="arrow")
        self.lbl.pack(fill=tk.BOTH, expand=True)

        # === BINDING INPUT ===
        self.lbl.bind("<Motion>", self._send_mouse_move)
        self.lbl.bind("<ButtonPress-1>", lambda e: self._send_mouse_action(1, 1, e))
        self.lbl.bind("<ButtonRelease-1>", lambda e: self._send_mouse_action(2, 1, e))
        self.lbl.bind("<ButtonPress-3>", lambda e: self._send_mouse_action(1, 3, e))
        self.lbl.bind("<ButtonRelease-3>", lambda e: self._send_mouse_action(2, 3, e))

        # Scroll
        self.root.bind("<MouseWheel>", self._send_scroll)
        self.root.bind("<Button-4>", lambda e: self._send_scroll(e, 1))
        self.root.bind("<Button-5>", lambda e: self._send_scroll(e, -1))

        # Tastiera
        self.root.bind("<KeyPress>", lambda e: self._send_key(4, e))
        self.root.bind("<KeyRelease>", lambda e: self._send_key(5, e))

        # Eventi Finestra
        self.root.bind("<Configure>", self._on_resize)
        self.root.bind("<FocusOut>", self._on_focus_out)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.focus_set()
        self._show_config_dialog()

    def _show_config_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Configurazione Server")
        win.geometry("300x180")

        tk.Label(win, text="IP Ascolto:").pack(pady=5)
        e_ip = tk.Entry(win)
        e_ip.insert(0, "0.0.0.0")
        e_ip.pack()
        tk.Label(win, text="Porta:").pack(pady=5)
        e_port = tk.Entry(win)
        e_port.insert(0, "9999")
        e_port.pack()

        def start_server():
            ip = e_ip.get().strip() or "0.0.0.0"
            try:
                p = int(e_port.get().strip())
                win.destroy()
                threading.Thread(target=self._server_loop, args=(ip, p), daemon=True).start()
            except ValueError:
                messagebox.showerror("Errore", "Porta non valida.")

        tk.Button(win, text="AVVIA", command=start_server).pack(pady=15)

    def _server_loop(self, ip, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.sock.bind((ip, port))
            self.sock.listen(1)
            print(f"[Info] In attesa su {ip}:{port}...")
            self.running = True

            while self.running:
                try:
                    self.conn, addr = self.sock.accept()
                    print(f"[Info] Connesso da: {addr}")
                    self.pressed_keys.clear()

                    while self.running:
                        # Header: 4 byte (Size Img) + 1 byte (Cursor ID) = 5 bytes
                        header = self._recvall(5)
                        if not header: break

                        img_size, cursor_id = struct.unpack(">LB", header)

                        # Aggiorna cursore locale
                        self._update_cursor(cursor_id)

                        # Ricevi immagine
                        data = self._recvall(img_size)
                        if not data: break

                        try:
                            img = Image.open(io.BytesIO(data))
                            if self.win_w > 10 and self.win_h > 10:
                                img = img.resize((self.win_w, self.win_h), Image.Resampling.NEAREST)
                            tk_img = ImageTk.PhotoImage(img)
                            self.lbl.configure(image=tk_img)
                            self.lbl.image = tk_img
                        except Exception:
                            pass

                    if self.conn: self.conn.close()
                    print("[Info] Client disconnesso.")
                except OSError:
                    break
        except Exception as e:
            messagebox.showerror("Errore", f"Server error: {e}")
            self._on_close()

    def _recvall(self, n):
        data = b''
        while len(data) < n:
            try:
                chunk = self.conn.recv(n - len(data))
                if not chunk: return None
                data += chunk
            except:
                return None
        return data

    def _update_cursor(self, cursor_id):
        # Imposta il cursore di Tkinter in base all'ID ricevuto
        cursor_name = CURSOR_MAPPING.get(cursor_id, "arrow")
        if self.lbl.cget("cursor") != cursor_name:
            self.lbl.config(cursor=cursor_name)

    # === LOGICA INPUT ===
    def _get_norm_coords(self, event):
        if self.win_w <= 0 or self.win_h <= 0: return 0.0, 0.0
        return max(0.0, min(1.0, event.x / self.win_w)), max(0.0, min(1.0, event.y / self.win_h))

    def _send_mouse_move(self, event):
        if not self.conn: return
        nx, ny = self._get_norm_coords(event)
        try:
            self.conn.sendall(struct.pack(">Bff", 0, nx, ny))
        except:
            pass

    def _send_mouse_action(self, atype, btn, event):
        if not self.conn: return
        nx, ny = self._get_norm_coords(event)
        try:
            self.conn.sendall(struct.pack(">BBff", atype, btn, nx, ny))
        except:
            pass

    def _send_scroll(self, event, linux_delta=0):
        if not self.conn: return
        amt = linux_delta * 50 if linux_delta != 0 else int(event.delta / 2)
        try:
            self.conn.sendall(struct.pack(">Bi", 3, amt))
        except:
            pass

    def _send_key(self, action_type, event):
        if not self.conn: return

        keysym = event.keysym
        py_key = None

        if action_type == 4:  # KeyDown
            # 1. Mappatura Tasti Speciali (Enter, Shift, F1...)
            if keysym in KEY_MAPPING:
                py_key = KEY_MAPPING[keysym]

            # 2. Mappatura Caratteri Shiftati (! -> 1, @ -> 2)
            # Questo permette di inviare il tasto 'BASE' mentre lo Shift è premuto separatamente
            elif keysym in SHIFT_MAPPING:
                py_key = SHIFT_MAPPING[keysym]

            # 3. Lettere e Numeri Semplici
            elif len(keysym) == 1:
                py_key = keysym.lower()

            if not py_key: return

            self.key_map[keysym] = py_key  # Memorizza per il rilascio

            if py_key in self.pressed_keys: return  # Anti-repeat
            self.pressed_keys.add(py_key)

        elif action_type == 5:  # KeyUp
            py_key = self.key_map.pop(keysym, None)
            if not py_key: return
            self.pressed_keys.discard(py_key)

        # Invio
        encoded = py_key.encode('utf-8')
        try:
            self.conn.sendall(struct.pack(">BB", action_type, len(encoded)) + encoded)
        except:
            pass

    def _on_focus_out(self, event):
        if not self.conn or not self.pressed_keys: return
        keys = list(self.pressed_keys)
        self.pressed_keys.clear()
        for k in keys:
            enc = k.encode('utf-8')
            try:
                self.conn.sendall(struct.pack(">BB", 5, len(enc)) + enc)
            except:
                pass

    def _on_resize(self, event):
        if event.widget == self.root:
            self.win_w, self.win_h = event.width, event.height

    def _on_close(self):
        self.running = False
        if self.sock: self.sock.close()
        try:
            self.root.destroy()
        except:
            pass
        import sys
        sys.exit(0)

    def start(self):
        """Avvia il loop principale dell'interfaccia grafica."""
        self.root.mainloop()

if __name__ == "__main__":
    app = RemoteDesktopController()
    app.start()
