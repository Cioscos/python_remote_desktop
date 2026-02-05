# controller.py (LISTENER - Visualizzatore)
import socket
import struct
import io
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk  # Richiede: pip install pillow


class RemoteDesktopController:
    def __init__(self):
        self.sock = None
        self.conn = None
        self.running = False
        self.server_thread = None

        # Variabili per gestire l'immagine e le dimensioni
        self.current_image = None
        self.win_w = 800
        self.win_h = 600

        # Inizializza la GUI principale
        self.root = tk.Tk()
        self.root.title("Reverse Remote Desktop (Tkinter)")
        self.root.geometry(f"{self.win_w}x{self.win_h}")

        # Label che conterrà il video
        self.video_label = tk.Label(self.root, bg="black")
        self.video_label.pack(fill=tk.BOTH, expand=True)

        # Binding Eventi (Mouse e Ridimensionamento)
        self.video_label.bind("<Motion>", self._on_mouse_move)
        self.video_label.bind("<Button-1>", self._on_mouse_click)
        self.root.bind("<Configure>", self._on_resize)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Mostra subito il dialog di configurazione
        self._show_config_dialog()

    def _show_config_dialog(self):
        """Finestra popup modale per inserire IP e Porta prima dell'avvio."""
        config_win = tk.Toplevel(self.root)
        config_win.title("Configurazione")
        config_win.geometry("300x150")
        config_win.grab_set()  # Blocca la finestra principale finché questa è aperta

        tk.Label(config_win, text="IP Ascolto (default 0.0.0.0):").pack(pady=5)
        entry_ip = tk.Entry(config_win)
        entry_ip.insert(0, "0.0.0.0")
        entry_ip.pack()

        tk.Label(config_win, text="Porta:").pack(pady=5)
        entry_port = tk.Entry(config_win)
        entry_port.insert(0, "9999")
        entry_port.pack()

        def on_confirm():
            ip = entry_ip.get()
            try:
                port = int(entry_port.get())
                config_win.destroy()
                # Avvia il server in un thread separato
                self._start_server_thread(ip, port)
            except ValueError:
                entry_port.config(bg="#ffcccc")

        tk.Button(config_win, text="AVVIA", command=on_confirm).pack(pady=15)

        # Se chiude la finestra con la X senza avviare, chiude tutto
        config_win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _start_server_thread(self, ip, port):
        """Avvia il thread di rete per non bloccare la GUI."""
        self.running = True
        self.server_thread = threading.Thread(target=self._server_loop, args=(ip, port), daemon=True)
        self.server_thread.start()

    def _server_loop(self, ip, port):
        """Logica di rete eseguita in background."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.sock.bind((ip, port))
            self.sock.listen(1)
            print(f"[Thread] In ascolto su {ip}:{port}")
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile avviare il server:\n{e}")
            self._on_close()
            return

        while self.running:
            try:
                # Accetta connessione
                self.conn, addr = self.sock.accept()
                print(f"[Thread] Connesso: {addr}")

                # Loop ricezione stream
                while self.running:
                    # 1. Header
                    header = self._recvall(4)
                    if not header: break
                    msg_size = struct.unpack(">L", header)[0]

                    # 2. Dati Immagine
                    frame_data = self._recvall(msg_size)
                    if not frame_data: break

                    # 3. Elaborazione Immagine (Decodifica + Resize)
                    try:
                        image_stream = io.BytesIO(frame_data)
                        pil_image = Image.open(image_stream)

                        # Ridimensiona l'immagine PIL in base alla finestra Tkinter attuale
                        # Nota: win_w e win_h vengono aggiornati dall'evento <Configure>
                        if self.win_w > 0 and self.win_h > 0:
                            pil_image = pil_image.resize((self.win_w, self.win_h), Image.Resampling.NEAREST)

                        # Converti per Tkinter
                        tk_image = ImageTk.PhotoImage(pil_image)

                        # AGGIORNAMENTO GUI: Deve essere thread-safe.
                        # Aggiorniamo la label direttamente (Tkinter in Python spesso lo tollera)
                        # o meglio, usiamo after_idle se ci fossero problemi, ma qui semplifichiamo.
                        self.video_label.configure(image=tk_image)
                        self.video_label.image = tk_image  # Mantiene riferimento per evitare garbage collection

                    except Exception as e:
                        print(f"Errore frame: {e}")

                if self.conn: self.conn.close()
                print("[Thread] Client disconnesso, torno in ascolto...")

            except OSError:
                break  # Socket chiuso durante la chiusura dell'app

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

    # --- EVENTI GUI ---

    def _on_resize(self, event):
        """Cattura il ridimensionamento della finestra."""
        # Filtriamo eventi spuri (a volte <Configure> scatta per i widget interni)
        if event.widget == self.root:
            self.win_w = event.width
            self.win_h = event.height

    def _on_mouse_move(self, event):
        """Invia movimento mouse."""
        self._send_input(0, event.x, event.y)

    def _on_mouse_click(self, event):
        """Invia click sinistro."""
        self._send_input(1, event.x, event.y)

    def _send_input(self, type, x, y):
        """Calcola coordinate normalizzate e invia."""
        if self.conn and self.win_w > 0 and self.win_h > 0:
            norm_x = max(0.0, min(1.0, x / self.win_w))
            norm_y = max(0.0, min(1.0, y / self.win_h))
            try:
                self.conn.sendall(struct.pack(">Bff", type, norm_x, norm_y))
            except:
                pass

    def _on_close(self):
        """Pulizia alla chiusura."""
        self.running = False
        if self.conn: self.conn.close()
        if self.sock: self.sock.close()
        self.root.destroy()
        import sys
        sys.exit(0)

    def start(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = RemoteDesktopController()
    app.start()
