# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import io
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk  # Richiede: pip install pillow

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

        # Inizializza GUI
        self.root = tk.Tk()
        self.root.title("Full Control Remote Desktop")
        self.root.geometry(f"{self.win_w}x{self.win_h}")

        # Label video
        self.lbl = tk.Label(self.root, bg="black")
        self.lbl.pack(fill=tk.BOTH, expand=True)

        # === BINDING INPUT ===
        # Mouse Movimento
        self.lbl.bind("<Motion>", self._send_mouse_move)

        # Mouse Click (Press e Release separati per Drag & Drop)
        self.lbl.bind("<ButtonPress-1>", lambda e: self._send_mouse_action(1, 1, e))  # Click SX Giù
        self.lbl.bind("<ButtonRelease-1>", lambda e: self._send_mouse_action(2, 1, e))  # Click SX Su
        self.lbl.bind("<ButtonPress-3>", lambda e: self._send_mouse_action(1, 3, e))  # Click DX Giù
        self.lbl.bind("<ButtonRelease-3>", lambda e: self._send_mouse_action(2, 3, e))  # Click DX Su

        # Rotellina
        self.root.bind("<MouseWheel>", self._send_scroll)  # Windows
        self.root.bind("<Button-4>", lambda e: self._send_scroll(e, 1))  # Linux Scroll UP
        self.root.bind("<Button-5>", lambda e: self._send_scroll(e, -1))  # Linux Scroll DOWN

        # Tastiera
        self.root.bind("<KeyPress>", lambda e: self._send_key(4, e))
        self.root.bind("<KeyRelease>", lambda e: self._send_key(5, e))

        # Eventi Finestra
        self.root.bind("<Configure>", self._on_resize)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Forza il focus per catturare subito la tastiera
        self.root.focus_set()

        # Mostra configurazione
        self._show_config_dialog()

    def _show_config_dialog(self):
        """Mostra popup per scegliere IP e Porta."""
        win = tk.Toplevel(self.root)
        win.title("Configurazione Server")
        win.geometry("300x180")

        # Input IP
        tk.Label(win, text="Indirizzo IP (0.0.0.0 per tutto):").pack(pady=(10, 5))
        e_ip = tk.Entry(win)
        e_ip.insert(0, "0.0.0.0")
        e_ip.pack(pady=5)

        # Input Porta
        tk.Label(win, text="Porta d'ascolto:").pack(pady=(5, 5))
        e_port = tk.Entry(win)
        e_port.insert(0, "9999")
        e_port.pack(pady=5)

        def start_server():
            ip_val = e_ip.get().strip()
            port_str = e_port.get().strip()

            if not ip_val:
                messagebox.showwarning("Attenzione", "Inserisci un IP valido.")
                return

            try:
                p = int(port_str)
                win.destroy()
                # Avvia il thread del server con IP e Porta scelti
                t = threading.Thread(target=self._server_loop, args=(ip_val, p), daemon=True)
                t.start()
            except ValueError:
                messagebox.showerror("Errore", "Porta non valida (deve essere un numero).")

        tk.Button(win, text="AVVIA SERVER", command=start_server, width=20, bg="#dddddd").pack(pady=15)

        # Se chiude il popup, chiude tutto
        win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _server_loop(self, ip, port):
        """Gestisce la connessione di rete in background."""
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
                        # 1. Legge dimensione immagine (4 byte)
                        header = self._recvall(4)
                        if not header: break
                        size = struct.unpack(">L", header)[0]

                        # 2. Legge i dati dell'immagine
                        data = self._recvall(size)
                        if not data: break

                        # 3. Decodifica e mostra
                        try:
                            img = Image.open(io.BytesIO(data))

                            # Ridimensiona solo se la finestra ha dimensioni valide
                            if self.win_w > 10 and self.win_h > 10:
                                img = img.resize((self.win_w, self.win_h), Image.Resampling.NEAREST)

                            tk_img = ImageTk.PhotoImage(img)
                            self.lbl.configure(image=tk_img)
                            self.lbl.image = tk_img  # Evita garbage collection
                        except Exception as e:
                            print(f"Errore render frame: {e}")

                    if self.conn: self.conn.close()
                    print("[Info] Client disconnesso. In attesa...")

                except OSError:
                    break  # Socket chiuso
        except Exception as e:
            messagebox.showerror("Errore Server", f"Impossibile avviare su {ip}:{port}\n\n{e}")
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

    # === LOGICA INVIO INPUT ===

    def _get_norm_coords(self, event):
        """Restituisce coordinate normalizzate 0.0-1.0"""
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
        # Type 1/2, Data = Bff (btn_code, x, y)
        try:
            self.conn.sendall(struct.pack(">BBff", action_type, btn_code, nx, ny))
        except:
            pass

    def _send_scroll(self, event, linux_delta=0):
        if not self.conn: return

        # Normalizzazione Scroll Windows vs Linux
        if linux_delta != 0:
            scroll_amount = linux_delta * 50
        else:
            # Windows solitamente è +-120
            scroll_amount = int(event.delta / 2)

        try:
            self.conn.sendall(struct.pack(">Bi", 3, scroll_amount))
        except:
            pass

    def _send_key(self, action_type, event):
        """ action_type: 4=KeyDown, 5=KeyUp """
        if not self.conn: return

        # Mappatura
        key = event.keysym
        if key in KEY_MAPPING:
            py_key = KEY_MAPPING[key]
        elif len(key) == 1:
            py_key = key.lower()
        else:
            return  # Tasto non gestito

        encoded = py_key.encode('utf-8')
        if len(encoded) > 255: return

        try:
            # Type(1B) + Len(1B) + String
            self.conn.sendall(struct.pack(">BB", action_type, len(encoded)) + encoded)
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
        """Avvia il loop principale della GUI."""
        self.root.mainloop()


if __name__ == "__main__":
    app = RemoteDesktopController()
    app.start()
