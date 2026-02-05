# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import io
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

# Mappatura Tasti Funzione e Speciali
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
    'Caps_Lock': 'capslock',
    'Insert': 'insert', 'Print': 'printscreen', 'Scroll_Lock': 'scrolllock', 'Pause': 'pause'
}

# Mappatura Estesa per Simboli (Tkinter keysym -> Tasto Base)
# Mappa il nome del simbolo al tasto fisico che lo produce (Layout US standard come fallback comune)
SHIFT_MAPPING = {
    # Nomi Tkinter -> Tasto Base
    'exclam': '1', 'at': '2', 'numbersign': '3', 'dollar': '4', 'percent': '5',
    'asciicircum': '6', 'ampersand': '7', 'asterisk': '8', 'parenleft': '9', 'parenright': '0',
    'underscore': '-', 'plus': '=',
    'braceleft': '[', 'braceright': ']',
    'colon': ';', 'quotedbl': "'",
    'less': ',', 'greater': '.', 'question': '/',
    'bar': '\\', 'asciitilde': '`',

    # Caratteri diretti (nel caso Tkinter restituisca il char)
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
    '_': '-', '+': '=', '{': '[', '}': ']', ':': ';', '"': "'", '<': ',', '>': '.', '?': '/', '|': '\\', '~': '`'
}

# Mappatura Cursori
CURSOR_MAPPING = {
    0: "arrow", 1: "xterm", 2: "hand2", 3: "watch",
    4: "cross", 5: "sb_v_double_arrow", 6: "sb_h_double_arrow"
}


class RemoteDesktopController:
    def __init__(self):
        self.sock = None
        self.conn = None
        self.running = False
        self.win_w, self.win_h = 800, 600

        self.pressed_keys = set()
        self.key_map = {}

        self.root = tk.Tk()
        self.root.title("Full Control Remote Desktop")
        self.root.geometry(f"{self.win_w}x{self.win_h}")

        self.lbl = tk.Label(self.root, bg="black", cursor="arrow")
        self.lbl.pack(fill=tk.BOTH, expand=True)

        # Mouse
        self.lbl.bind("<Motion>", self._send_mouse_move)
        self.lbl.bind("<ButtonPress-1>", lambda e: self._send_mouse_action(1, 1, e))
        self.lbl.bind("<ButtonRelease-1>", lambda e: self._send_mouse_action(2, 1, e))
        self.lbl.bind("<ButtonPress-3>", lambda e: self._send_mouse_action(1, 3, e))
        self.lbl.bind("<ButtonRelease-3>", lambda e: self._send_mouse_action(2, 3, e))
        self.lbl.bind("<ButtonPress-2>", lambda e: self._send_mouse_action(1, 2, e))  # Rotellina click
        self.lbl.bind("<ButtonRelease-2>", lambda e: self._send_mouse_action(2, 2, e))

        # Scroll
        self.root.bind("<MouseWheel>", self._send_scroll)
        self.root.bind("<Button-4>", lambda e: self._send_scroll(e, 1))
        self.root.bind("<Button-5>", lambda e: self._send_scroll(e, -1))

        # Tastiera
        self.root.bind("<KeyPress>", lambda e: self._send_key(4, e))
        self.root.bind("<KeyRelease>", lambda e: self._send_key(5, e))

        # Finestra
        self.root.bind("<Configure>", self._on_resize)
        self.root.bind("<FocusOut>", self._on_focus_out)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.focus_set()
        self._show_config_dialog()

    def _show_config_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Configurazione")
        win.geometry("300x180")

        tk.Label(win, text="IP Ascolto:").pack(pady=5)
        e_ip = tk.Entry(win);
        e_ip.insert(0, "0.0.0.0");
        e_ip.pack()
        tk.Label(win, text="Porta:").pack(pady=5)
        e_port = tk.Entry(win);
        e_port.insert(0, "9999");
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
            print(f"[Info] Server avviato su {ip}:{port}")
            self.running = True

            while self.running:
                try:
                    self.conn, addr = self.sock.accept()
                    print(f"[Info] Connesso: {addr}")
                    self.pressed_keys.clear()

                    while self.running:
                        header = self._recvall(5)
                        if not header: break
                        img_size, cursor_id = struct.unpack(">LB", header)

                        self._update_cursor(cursor_id)

                        data = self._recvall(img_size)
                        if not data: break

                        try:
                            img = Image.open(io.BytesIO(data))
                            if self.win_w > 10 and self.win_h > 10:
                                img = img.resize((self.win_w, self.win_h), Image.Resampling.NEAREST)
                            tk_img = ImageTk.PhotoImage(img)
                            self.lbl.configure(image=tk_img)
                            self.lbl.image = tk_img
                        except:
                            pass

                    if self.conn: self.conn.close()
                    print("[Info] Client disconnesso")
                except OSError:
                    break
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
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
        cursor_name = CURSOR_MAPPING.get(cursor_id, "arrow")
        if self.lbl.cget("cursor") != cursor_name:
            self.lbl.config(cursor=cursor_name)

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
            # Priorità 1: Mappatura tasti speciali e modificatori
            if keysym in KEY_MAPPING:
                py_key = KEY_MAPPING[keysym]
            # Priorità 2: Mappatura simboli shiftati (exclam -> 1)
            elif keysym in SHIFT_MAPPING:
                py_key = SHIFT_MAPPING[keysym]
            # Priorità 3: Tasti normali (lettere, numeri)
            elif len(keysym) == 1:
                py_key = keysym.lower()

            if not py_key: return

            # MODIFICA IMPORTANTE: Gestione Anti-Repeat Selettiva
            # Blocchiamo la ripetizione SOLO per i modificatori.
            # Permettiamo Backspace, Enter e Lettere di ripetersi.
            is_modifier = py_key in ['ctrl', 'alt', 'shift', 'win', 'capslock']

            if is_modifier:
                if py_key in self.pressed_keys: return
                self.pressed_keys.add(py_key)
            else:
                # Per i tasti non modificatori, non li aggiungiamo a pressed_keys
                # per bloccarne l'invio, ma solo per tracciarne il rilascio se necessario.
                # Tuttavia, per semplicità, permettiamo l'invio continuo del pacchetto KeyDown.
                self.key_map[keysym] = py_key  # Memorizza quale tasto rilasciare dopo

        elif action_type == 5:  # KeyUp
            # Troviamo cosa inviare in base al keysym originale
            # (Nota: per i simboli shiftati, rilasciamo il numero, es: 1)
            if keysym in KEY_MAPPING:
                py_key = KEY_MAPPING[keysym]
            elif keysym in SHIFT_MAPPING:
                py_key = SHIFT_MAPPING[keysym]
            elif len(keysym) == 1:
                py_key = keysym.lower()
            else:
                # Fallback se non trovato direttamente
                py_key = self.key_map.pop(keysym, None)

            if not py_key: return

            # Rimuovi dal set dei premuti (utile per i modificatori)
            self.pressed_keys.discard(py_key)

        # Invia pacchetto
        encoded = py_key.encode('utf-8')
        try:
            self.conn.sendall(struct.pack(">BB", action_type, len(encoded)) + encoded)
        except:
            pass

    def _on_focus_out(self, event):
        if not self.conn: return
        # Rilascia tutti i modificatori conosciuti per sicurezza
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

    def _on_close(self):
        self.running = False
        if self.sock: self.sock.close()
        try:
            self.root.destroy()
        except:
            pass
        import sys;
        sys.exit(0)

    def start(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = RemoteDesktopController()
    app.start()
