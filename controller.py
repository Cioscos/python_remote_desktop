# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import io
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

# Mappatura tasti speciali Tkinter -> PyAutoGUI
KEY_MAPPING = {
    'Return': 'enter', 'BackSpace': 'backspace', 'Tab': 'tab', 'space': 'space',
    'Escape': 'esc', 'Delete': 'delete', 'Home': 'home', 'End': 'end',
    'Prior': 'pageup', 'Next': 'pagedown', 'Up': 'up', 'Down': 'down',
    'Left': 'left', 'Right': 'right', 'F1': 'f1', 'F2': 'f2', 'F3': 'f3',
    'F4': 'f4', 'F5': 'f5', 'F6': 'f6', 'F7': 'f7', 'F8': 'f8', 'F9': 'f9',
    'F10': 'f10', 'F11': 'f11', 'F12': 'f12',
    'Control_L': 'ctrlleft', 'Control_R': 'ctrlright',
    'Alt_L': 'altleft', 'Alt_R': 'altright',
    'Shift_L': 'shiftleft', 'Shift_R': 'shiftright',
    'Win_L': 'winleft', 'Win_R': 'winright',
    'Caps_Lock': 'capslock'
}


class RemoteDesktopController:
    def __init__(self):
        self.sock = None
        self.conn = None
        self.running = False
        self.win_w, self.win_h = 800, 600

        self.root = tk.Tk()
        self.root.title("Full Control Remote Desktop")
        self.root.geometry(f"{self.win_w}x{self.win_h}")

        self.lbl = tk.Label(self.root, bg="black")
        self.lbl.pack(fill=tk.BOTH, expand=True)

        # === BINDING INPUT ===
        # Mouse Movimento
        self.lbl.bind("<Motion>", self._send_mouse_move)

        # Mouse Click (Press e Release separati per Drag & Drop)
        # Button-1: Sinistro, Button-2: Centrale, Button-3: Destro
        self.lbl.bind("<ButtonPress-1>", lambda e: self._send_mouse_action(1, 1, e))
        self.lbl.bind("<ButtonRelease-1>", lambda e: self._send_mouse_action(2, 1, e))
        self.lbl.bind("<ButtonPress-3>", lambda e: self._send_mouse_action(1, 3, e))
        self.lbl.bind("<ButtonRelease-3>", lambda e: self._send_mouse_action(2, 3, e))
        # Rotellina (Windows usa <MouseWheel>, Linux usa Button-4/5)
        self.root.bind("<MouseWheel>", self._send_scroll)
        self.root.bind("<Button-4>", lambda e: self._send_scroll(e, 1))  # Linux su
        self.root.bind("<Button-5>", lambda e: self._send_scroll(e, -1))  # Linux giù

        # Tastiera
        # Importante: Il focus deve essere sulla finestra per catturare i tasti
        self.root.bind("<KeyPress>", lambda e: self._send_key(4, e))
        self.root.bind("<KeyRelease>", lambda e: self._send_key(5, e))

        self.root.bind("<Configure>", self._on_resize)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Focus force per catturare subito la tastiera
        self.root.focus_set()

        self._show_config_dialog()

    def _show_config_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Avvio Server")
        tk.Label(win, text="Porta:").pack()
        e_port = tk.Entry(win);
        e_port.insert(0, "9999");
        e_port.pack()

        def start():
            try:
                p = int(e_port.get())
                win.destroy()
                threading.Thread(target=self._server_loop, args=("0.0.0.0", p), daemon=True).start()
            except:
                pass

        tk.Button(win, text="START", command=start).pack(pady=10)
        win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _server_loop(self, ip, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((ip, port))
        self.sock.listen(1)
        self.running = True
        print(f"In ascolto su {port}...")

        while self.running:
            try:
                self.conn, _ = self.sock.accept()
                print("Client connesso.")

                while self.running:
                    # Legge dimensione immagine
                    header = self._recvall(4)
                    if not header: break
                    size = struct.unpack(">L", header)[0]

                    # Legge immagine
                    data = self._recvall(size)
                    if not data: break

                    # Mostra immagine
                    try:
                        img = Image.open(io.BytesIO(data))
                        if self.win_w > 0 and self.win_h > 0:
                            img = img.resize((self.win_w, self.win_h), Image.Resampling.NEAREST)
                        tk_img = ImageTk.PhotoImage(img)
                        self.lbl.configure(image=tk_img)
                        self.lbl.image = tk_img
                    except:
                        pass

                if self.conn: self.conn.close()
            except OSError:
                break

    def _recvall(self, n):
        data = b''
        while len(data) < n:
            chunk = self.conn.recv(n - len(data))
            if not chunk: return None
            data += chunk
        return data

    # === LOGICA INVIO INPUT ===

    def _get_norm_coords(self, event):
        if self.win_w <= 0 or self.win_h <= 0: return 0, 0
        nx = max(0.0, min(1.0, event.x / self.win_w))
        ny = max(0.0, min(1.0, event.y / self.win_h))
        return nx, ny

    def _send_mouse_move(self, event):
        if not self.conn: return
        nx, ny = self._get_norm_coords(event)
        # Type 0 = Move, Data = ff (x, y)
        try:
            self.conn.sendall(struct.pack(">Bff", 0, nx, ny))
        except:
            pass

    def _send_mouse_action(self, action_type, btn_code, event):
        """ action_type: 1=Down, 2=Up """
        if not self.conn: return
        nx, ny = self._get_norm_coords(event)
        # Type 1/2, Data = Bff (btn, x, y)
        try:
            self.conn.sendall(struct.pack(">BBff", action_type, btn_code, nx, ny))
        except:
            pass

    def _send_scroll(self, event, linux_delta=0):
        if not self.conn: return
        # Windows: event.delta è +-120. PyAutoGUI vuole +-10 ca. per riga.
        # Linux: usa button 4/5, passiamo delta manuale
        if linux_delta != 0:
            scroll_amount = linux_delta * 50
        else:
            scroll_amount = int(event.delta / 2)  # Scaliamo un po'

        try:
            self.conn.sendall(struct.pack(">Bi", 3, scroll_amount))
        except:
            pass

    def _send_key(self, action_type, event):
        """ action_type: 4=KeyDown, 5=KeyUp """
        if not self.conn: return

        # Mappatura tasti
        key = event.keysym
        if key in KEY_MAPPING:
            py_key = KEY_MAPPING[key]
        elif len(key) == 1:
            py_key = key.lower()
        else:
            # Tasti ignoti o non mappati
            return

        encoded = py_key.encode('utf-8')
        if len(encoded) > 255: return  # Troppo lungo (non dovrebbe succedere)

        try:
            # Pacchetto: Type(1B) + Len(1B) + String
            self.conn.sendall(struct.pack(">BB", action_type, len(encoded)) + encoded)
        except:
            pass

    def _on_resize(self, event):
        if event.widget == self.root:
            self.win_w, self.win_h = event.width, event.height

    def _on_close(self):
        self.running = False
        if self.sock: self.sock.close()
        self.root.destroy()
        import sys;
        sys.exit(0)


if __name__ == "__main__":
    RemoteDesktopController()
