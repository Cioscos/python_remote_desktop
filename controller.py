# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import io
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

# Mappatura: Usiamo nomi generici per i modificatori per massima compatibilità
KEY_MAPPING = {
    'Return': 'enter', 'BackSpace': 'backspace', 'Tab': 'tab', 'space': 'space',
    'Escape': 'esc', 'Delete': 'delete', 'Home': 'home', 'End': 'end',
    'Prior': 'pageup', 'Next': 'pagedown', 'Up': 'up', 'Down': 'down',
    'Left': 'left', 'Right': 'right',
    'F1': 'f1', 'F2': 'f2', 'F3': 'f3', 'F4': 'f4', 'F5': 'f5', 'F6': 'f6',
    'F7': 'f7', 'F8': 'f8', 'F9': 'f9', 'F10': 'f10', 'F11': 'f11', 'F12': 'f12',

    # Modificatori: Mappiamo entrambi i lati sul nome generico
    'Control_L': 'ctrl', 'Control_R': 'ctrl',
    'Alt_L': 'alt', 'Alt_R': 'alt',
    'Shift_L': 'shift', 'Shift_R': 'shift',
    'Win_L': 'win', 'Win_R': 'win',
    'Caps_Lock': 'capslock'
}


class RemoteDesktopController:
    def __init__(self):
        self.sock = None
        self.conn = None
        self.running = False
        self.win_w, self.win_h = 800, 600

        # Set per tracciare i tasti ATTUALMENTE giù
        self.pressed_keys = set()

        self.root = tk.Tk()
        self.root.title("Full Control Remote Desktop")
        self.root.geometry(f"{self.win_w}x{self.win_h}")

        self.lbl = tk.Label(self.root, bg="black")
        self.lbl.pack(fill=tk.BOTH, expand=True)

        # === BINDING INPUT ===
        # Mouse
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
        self.root.bind("<FocusOut>", self._on_focus_out)  # Sicurezza se si perde il focus
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.focus_set()
        self._show_config_dialog()

    def _show_config_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Configurazione")
        win.geometry("300x180")

        tk.Label(win, text="IP (0.0.0.0 per tutto):").pack(pady=(10, 5))
        e_ip = tk.Entry(win);
        e_ip.insert(0, "0.0.0.0");
        e_ip.pack()
        tk.Label(win, text="Porta:").pack(pady=(5, 5))
        e_port = tk.Entry(win);
        e_port.insert(0, "9999");
        e_port.pack()

        def start_server():
            ip_val = e_ip.get().strip()
            try:
                p = int(e_port.get().strip())
                if not ip_val: ip_val = "0.0.0.0"
                win.destroy()
                threading.Thread(target=self._server_loop, args=(ip_val, p), daemon=True).start()
            except ValueError:
                messagebox.showerror("Errore", "Porta non valida.")

        tk.Button(win, text="AVVIA", command=start_server, bg="#dddddd").pack(pady=15)
        win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _server_loop(self, ip, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.sock.bind((ip, port))
            self.sock.listen(1)
            print(f"[Info] Server avviato su {ip}:{port}...")
            self.running = True

            while self.running:
                try:
                    self.conn, addr = self.sock.accept()
                    print(f"[Info] Connesso da: {addr}")

                    while self.running:
                        header = self._recvall(4)
                        if not header: break
                        size = struct.unpack(">L", header)[0]
                        data = self._recvall(size)
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
                    self.pressed_keys.clear()  # Reset tasti alla disconnessione
                    print("[Info] Client disconnesso.")

                except OSError:
                    break
        except Exception as e:
            messagebox.showerror("Errore", f"Errore server: {e}")
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

    # === LOGICA INPUT ===

    def _get_norm_coords(self, event):
        if self.win_w <= 0 or self.win_h <= 0: return 0, 0
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
        """Gestisce pressione (4) e rilascio (5) tasti con filtro anti-ripetizione."""
        if not self.conn: return

        # Mapping
        key = event.keysym
        if key in KEY_MAPPING:
            py_key = KEY_MAPPING[key]
        elif len(key) == 1:
            py_key = key.lower()
        else:
            return

            # --- LOGICA ANTI-REPEAT ---
        if action_type == 4:  # KeyDown
            if py_key in self.pressed_keys:
                return  # Tasto già premuto, ignoriamo la ripetizione del sistema operativo
            self.pressed_keys.add(py_key)

        elif action_type == 5:  # KeyUp
            self.pressed_keys.discard(py_key)

        # Se passiamo il filtro, inviamo il pacchetto
        encoded = py_key.encode('utf-8')
        try:
            self.conn.sendall(struct.pack(">BB", action_type, len(encoded)) + encoded)
        except:
            pass

    def _on_focus_out(self, event):
        """Se perdi il focus (es. Alt-Tab), rilascia tutto."""
        if not self.conn or not self.pressed_keys: return

        keys_to_release = list(self.pressed_keys)
        self.pressed_keys.clear()

        for k in keys_to_release:
            encoded = k.encode('utf-8')
            try:
                self.conn.sendall(struct.pack(">BB", 5, len(encoded)) + encoded)
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
        import sys;
        sys.exit(0)

    def start(self):
        self.root.mainloop()


if __name__ == "__main__":
    RemoteDesktopController().start()
