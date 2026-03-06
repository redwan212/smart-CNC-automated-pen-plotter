import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import io
import contextlib

import ftest2  # must be in same folder or packaged in EXE
from PIL import Image, ImageTk


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Smart CNC Pen Plotter")
        self.minsize(1200, 720)
        self.state("zoomed")  # Windows maximize

        self.bg = "#0b1220"
        self.panel = "#0f1a2e"
        self.card = "#111c33"
        self.card2 = "#0f1930"
        self.text = "#e8edf6"
        self.muted = "#9aa7bd"
        self.border = "#223155"
        self.blue = "#2f7cff"
        self.green = "#18b26a"
        self.orange = "#ffb020"

        self.configure(bg=self.bg)

        self.selected_file = tk.StringVar(value="No file selected")
        self.mode = tk.IntVar(value=1)

        self._preview_imgtk = None  # keep reference

        self._build_ui()

    # ---------------- UI helpers ----------------
    def _btn(self, parent, text, command, bg, fg="#ffffff"):
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=("Segoe UI", 12, "bold"),
            bg=bg,
            fg=fg,
            activebackground=bg,
            activeforeground=fg,
            bd=0,
            padx=18,
            pady=12,
            cursor="hand2"
        )

    def _label(self, parent, text, size=12, bold=False, fg=None, bg=None):
        return tk.Label(
            parent,
            text=text,
            font=("Segoe UI", size, "bold" if bold else "normal"),
            fg=fg or self.text,
            bg=bg or self.bg
        )

    def _card(self, parent):
        frame = tk.Frame(parent, bg=self.card, bd=1, relief="solid", highlightthickness=0)
        frame.configure(highlightbackground=self.border, highlightcolor=self.border)
        return frame

    # ---------------- Main UI ----------------
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(self, bg=self.panel, bd=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_rowconfigure(6, weight=1)
        sidebar.configure(width=300)

        main = tk.Frame(self, bg=self.bg, bd=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=3)  # preview
        main.grid_columnconfigure(1, weight=5)  # log
        main.grid_rowconfigure(1, weight=1)

        # ---------------- Sidebar ----------------
        brand = tk.Frame(sidebar, bg=self.panel)
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        self._label(brand, "SMART CNC", size=20, bold=True, fg=self.text, bg=self.panel).pack(anchor="w")
        self._label(brand, "Automated pen plotter", size=11, fg=self.muted, bg=self.panel).pack(anchor="w", pady=(2, 0))

        file_card = tk.Frame(sidebar, bg=self.card2, bd=1, relief="solid")
        file_card.grid(row=1, column=0, sticky="ew", padx=18, pady=(10, 12))
        file_card.configure(highlightbackground=self.border, highlightcolor=self.border)

        self._label(file_card, "INPUT IMAGE", size=11, bold=True, fg=self.muted, bg=self.card2)\
            .pack(anchor="w", padx=14, pady=(12, 6))

        self.file_label = tk.Label(
            file_card,
            textvariable=self.selected_file,
            font=("Segoe UI", 11, "bold"),
            fg=self.text,
            bg="#0b152a",
            bd=0,
            padx=12,
            pady=10,
            anchor="w",
            wraplength=250,
            justify="left"
        )
        self.file_label.pack(fill="x", padx=14, pady=(0, 10))

        self._btn(file_card, "Browse Image", self.browse_file, self.blue).pack(fill="x", padx=14, pady=(0, 14))

        mode_card = tk.Frame(sidebar, bg=self.card2, bd=1, relief="solid")
        mode_card.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
        mode_card.configure(highlightbackground=self.border, highlightcolor=self.border)

        self._label(mode_card, "SELECT MODE", size=11, bold=True, fg=self.muted, bg=self.card2)\
            .pack(anchor="w", padx=14, pady=(12, 8))

        rb_style = dict(
            font=("Segoe UI", 12, "bold"),
            bg=self.card2,
            fg=self.text,
            activebackground=self.card2,
            activeforeground=self.text,
            selectcolor="#0b152a",
            cursor="hand2"
        )
        tk.Radiobutton(mode_card, text="Mode 1  •  Outline", variable=self.mode, value=1, **rb_style)\
            .pack(anchor="w", padx=14, pady=(0, 6))
        tk.Radiobutton(mode_card, text="Mode 2  •  Shading / Hatch", variable=self.mode, value=2, **rb_style)\
            .pack(anchor="w", padx=14, pady=(0, 12))

        action_card = tk.Frame(sidebar, bg=self.card2, bd=1, relief="solid")
        action_card.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 12))
        action_card.configure(highlightbackground=self.border, highlightcolor=self.border)

        self._label(action_card, "ACTIONS", size=11, bold=True, fg=self.muted, bg=self.card2)\
            .pack(anchor="w", padx=14, pady=(12, 8))

        self.run_btn = self._btn(action_card, "▶  RUN PROCESS", self.run_script_thread, self.green)
        self.run_btn.pack(fill="x", padx=14, pady=(0, 10))

        self.clear_btn = self._btn(action_card, "🧹  CLEAR LOG", self.clear_log, "#243456")
        self.clear_btn.pack(fill="x", padx=14, pady=(0, 14))

        # ---------------- Main: Topbar ----------------
        topbar = tk.Frame(main, bg=self.bg)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=22, pady=(18, 10))
        topbar.grid_columnconfigure(0, weight=1)

        self._label(topbar, "Dashboard", size=22, bold=True, fg=self.text, bg=self.bg).grid(row=0, column=0, sticky="w")

        status_wrap = tk.Frame(topbar, bg=self.bg)
        status_wrap.grid(row=0, column=1, sticky="e")
        self.status = tk.Label(
            status_wrap,
            text="Ready",
            font=("Segoe UI", 11, "bold"),
            fg=self.green,
            bg=self.bg,
            padx=10,
            pady=6
        )
        self.status.pack(anchor="e")

        # ---------------- Main: Preview Card (left) ----------------
        preview_card = self._card(main)
        preview_card.grid(row=1, column=0, sticky="nsew", padx=(22, 10), pady=(0, 22))
        preview_card.grid_rowconfigure(1, weight=1)
        preview_card.grid_columnconfigure(0, weight=1)

        preview_header = tk.Frame(preview_card, bg=self.card)
        preview_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 10))
        self._label(preview_header, "IMAGE PREVIEW", size=12, bold=True, fg=self.muted, bg=self.card).pack(anchor="w")

        self.preview_area = tk.Label(
            preview_card,
            bg="#0b152a",
            fg=self.muted,
            text="No image selected",
            font=("Segoe UI", 13, "bold"),
            bd=0,
            padx=10,
            pady=10
        )
        self.preview_area.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

        # ---------------- Main: Log Card (right) ----------------
        log_card = self._card(main)
        log_card.grid(row=1, column=1, sticky="nsew", padx=(10, 22), pady=(0, 22))
        log_card.grid_rowconfigure(1, weight=1)
        log_card.grid_columnconfigure(0, weight=1)

        header = tk.Frame(log_card, bg=self.card)
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 10))
        self._label(header, "OUTPUT LOG", size=12, bold=True, fg=self.muted, bg=self.card).pack(anchor="w")

        self.output_text = tk.Text(
            log_card,
            font=("Consolas", 12),
            bg="#0b152a",
            fg=self.text,
            insertbackground=self.text,
            bd=0,
            padx=14,
            pady=12,
            wrap="word"
        )
        self.output_text.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

        self.log("✅ Ready. Select an image, choose mode, then click RUN PROCESS.")

        self.preview_area.bind("<Configure>", lambda e: self._refresh_preview())

    # ---------------- Thread-safe logging ----------------
    def log(self, text: str):
        def _write():
            self.output_text.insert(tk.END, text + "\n")
            self.output_text.see(tk.END)
        self.after(0, _write)

    def set_status(self, text: str, color: str):
        def _set():
            self.status.config(text=text, fg=color)
        self.after(0, _set)

    def set_running(self, running: bool):
        def _set():
            if running:
                self.run_btn.config(state="disabled")
                self.status.config(text="Running...", fg=self.orange)
            else:
                self.run_btn.config(state="normal")
                self.status.config(text="Ready", fg=self.green)
        self.after(0, _set)

    # ---------------- Preview ----------------
    def _refresh_preview(self):
        path = self.selected_file.get()
        if not path or path == "No file selected" or not os.path.exists(path):
            return

        try:
            w = max(200, self.preview_area.winfo_width() - 20)
            h = max(200, self.preview_area.winfo_height() - 20)

            img = Image.open(path).convert("RGB")
            img.thumbnail((w, h))

            self._preview_imgtk = ImageTk.PhotoImage(img)
            self.preview_area.config(image=self._preview_imgtk, text="")
        except Exception:
            self.preview_area.config(image="", text="Preview failed")

    # ---------------- Actions ----------------
    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Select an Image",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp")]
        )
        if file_path:
            self.selected_file.set(file_path)
            self.log(f"Selected: {file_path}")
            self.preview_area.config(text="Loading preview...", image="")
            self.after(50, self._refresh_preview)

    def clear_log(self):
        self.output_text.delete("1.0", tk.END)
        self.set_status("Ready", self.green)

    def run_script_thread(self):
        if self.selected_file.get() == "No file selected":
            messagebox.showerror("Error", "Please select an image first!")
            return
        threading.Thread(target=self.run_process, daemon=True).start()

    # ---------------- NEW: Run by calling ftest2.main() directly ----------------
    def run_process(self):
        img_path = self.selected_file.get()
        mode_val = self.mode.get()

        if not os.path.exists(img_path):
            self.log("❌ Selected image path does not exist.")
            return

        self.set_running(True)
        self.log("=" * 70)
        self.log(f"Running: ftest2.main(['--mode', '{mode_val}', '{img_path}'])")
        self.log("=" * 70)

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                exit_code = ftest2.main(["--mode", str(mode_val), img_path])
        except Exception as e:
            self.set_status("Error ❌", "#ff4d4d")
            self.log(f"❌ Error: {e}")
            self.set_running(False)
            return

        out = buf.getvalue()
        for line in out.splitlines():
            self.log(line)

        if exit_code == 0:
            self.set_status("Done ✅", self.green)
            self.log("✅ DONE! LaserGRBL should open automatically.")
        else:
            self.set_status("Failed ❌", "#ff4d4d")
            self.log(f"❌ FAILED! Exit Code = {exit_code}")

        self.set_running(False)


if __name__ == "__main__":
    App().mainloop()