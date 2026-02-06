# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import io
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

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

        # Dimensione Iniziale Finestra
        self.win_w, self.win_h = 1280, 720

        self.pressed_keys = set()
        self.key_map = {}

        self.root = tk.Tk()
        self.root.title("Full Control Remote Desktop - High Quality")
        self.root.geometry(f"{self.win_w}x{self.win_h}")

        self.lbl = tk.Label(self.root, bg="black", cursor="arrow")
        self.lbl.pack(fill=tk.BOTH, expand=True)

        # Binding Mouse
        self.lbl.bind("<Motion>", self._send_mouse_move)
        self.lbl.bind("<ButtonPress-1>", lambda e: self._send_mouse_action(1, 1, e))
        self.lbl.bind("<ButtonRelease-1>", lambda e: self._send_mouse_action(2, 1, e))
        self.lbl.bind("<ButtonPress-3>", lambda e: self._send_mouse_action(1, 3, e))
        self.lbl.bind("<ButtonRelease-3>", lambda e: self._send_mouse_action(2, 3, e))
        self.lbl.bind("<ButtonPress-2>", lambda e: self._send_mouse_action(1, 2, e))
        self.lbl.bind("<ButtonRelease-2>", lambda e: self._send_mouse_action(2, 2, e))

        # Binding Scroll
        self.root.bind("<MouseWheel>", self._send_scroll)
        self.root.bind("<Button-4>", lambda e: self._send_scroll(e, 1))
        self.root.bind("<Button-5>", lambda e: self._send_scroll(e, -1))

        # Binding Tastiera
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
        win.title("Config")
        win.geometry("300x220")

        tk.Label(win, text="IP Ascolto:").pack(pady=2)
        e_ip = tk.Entry(win)
        e_ip.insert(0, "0.0.0.0")
        e_ip.pack()
        tk.Label(win, text="Porta:").pack(pady=2)
        e_port = tk.Entry(win)
        e_port.insert(0, "9999")
        e_port.pack()

        # Checkbox per il cambio risoluzione automatico
        self.var_resize = tk.BooleanVar(value=True)
        tk.Checkbutton(win, text="Adatta Risoluzione Target (RDP Style)", variable=self.var_resize).pack(pady=10)

        def start_server():
            ip = e_ip.get().strip() or "0.0.0.0"
            try:
                p = int(e_port.get().strip())
                should_resize = self.var_resize.get()
                win.destroy()
                threading.Thread(target=self._server_loop, args=(ip, p, should_resize), daemon=True).start()
            except ValueError:
                messagebox.showerror("Errore", "Porta non valida.")

        tk.Button(win, text="AVVIA", command=start_server).pack(pady=10)

    def _server_loop(self, ip, port, auto_resize):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.sock.bind((ip, port))
            self.sock.listen(1)
            print(f"[Info] Listening on {ip}:{port}")
            self.running = True

            while self.running:
                try:
                    self.conn, addr = self.sock.accept()
                    print(f"[Info] Connected: {addr}")
                    self.pressed_keys.clear()

                    # === FEATURE: Invia Risoluzione Target ===
                    if auto_resize:
                        # Aspettiamo un attimo per stabilità
                        threading.Timer(0.5, self._send_resolution_command).start()

                    while self.running:
                        header = self._recvall(5)
                        if not header: break
                        img_size, cursor_id = struct.unpack(">LB", header)

                        self._update_cursor(cursor_id)

                        data = self._recvall(img_size)
                        if not data: break

                        try:
                            # Caricamento immagine (ottimizzato)
                            img = Image.open(io.BytesIO(data))

                            # Ridimensionamento locale solo se necessario per fit nella finestra
                            # (Se il target ha cambiato risoluzione, l'immagine dovrebbe già matchare quasi 1:1)
                            if self.win_w > 10 and self.win_h > 10:
                                img = img.resize((self.win_w, self.win_h), Image.Resampling.BILINEAR)

                            tk_img = ImageTk.PhotoImage(img)
                            self.lbl.configure(image=tk_img)
                            self.lbl.image = tk_img
                        except:
                            pass

                    if self.conn: self.conn.close()
                    print("[Info] Disconnected")
                except OSError:
                    break
        except Exception as e:
            messagebox.showerror("Errore", f"Server: {e}")
            self._on_close()

    def _send_resolution_command(self):
        """Invia al target il comando per cambiare risoluzione."""
        if not self.conn: return
        try:
            # Inviamo la dimensione attuale della finestra del controller
            w, h = self.win_w, self.win_h
            print(f"[Info] Richiesta cambio risoluzione remota a: {w}x{h}")
            # Tipo 6 = Risoluzione, 2 unsigned int (W, H)
            self.conn.sendall(struct.pack(">BII", 6, w, h))
        except:
            pass

    # ... Metodi _recvall, _update_cursor, _get_norm_coords, _send_mouse, _send_key ...
    # ... Sono IDENTICI alla versione precedente, li includo per completezza ma non cambiano ...

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

        if action_type == 4:
            if keysym in FUNCTION_KEY_MAPPING:
                py_key = FUNCTION_KEY_MAPPING[keysym]
            elif keysym in SYMBOL_MAPPING:
                py_key = SYMBOL_MAPPING[keysym]
            elif len(keysym) == 1:
                py_key = keysym.lower()

            if not py_key: return

            is_modifier = py_key in ['ctrl', 'alt', 'shift', 'win', 'capslock']
            if is_modifier:
                if py_key in self.pressed_keys: return
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

            if not py_key: return
            self.pressed_keys.discard(py_key)

        encoded = py_key.encode('utf-8')
        try:
            self.conn.sendall(struct.pack(">BB", action_type, len(encoded)) + encoded)
        except:
            pass

    def _on_focus_out(self, event):
        if not self.conn: return
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
        import sys
        sys.exit(0)

    def start(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = RemoteDesktopController()
    app.start()
