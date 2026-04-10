#!/usr/bin/env python3
"""
gui.py
------
Graphical interface for eml_to_pdf.
Bundled via PyInstaller into a single executable — no Python or pip required.
"""

import queue
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
from pathlib import Path

from eml_to_pdf import process_eml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
APP_TITLE   = "EML to PDF Converter"
APP_VERSION = "1.0"
WIN_W, WIN_H = 700, 540

BG          = "#f5f5f5"
ACCENT      = "#1a237e"
ACCENT_LITE = "#e8eaf6"
BTN_FG      = "#ffffff"
LOG_BG      = "#1e1e2e"
LOG_FG      = "#cdd6f4"
LOG_OK      = "#a6e3a1"
LOG_ERR     = "#f38ba8"
LOG_INFO    = "#89b4fa"
LOG_WARN    = "#fab387"


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.resizable(True, True)
        self.minsize(560, 460)
        self._center(WIN_W, WIN_H)
        self.configure(bg=BG)

        self._log_queue: queue.Queue = queue.Queue()
        self._running = False

        self._build_ui()
        self._poll_log()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=ACCENT, pady=16)
        header.pack(fill="x")
        tk.Label(
            header, text=APP_TITLE,
            font=("Segoe UI", 15, "bold"), bg=ACCENT, fg=BTN_FG,
        ).pack()
        tk.Label(
            header,
            text="Convert .eml files to PDF — preserving formatting and attachments",
            font=("Segoe UI", 9), bg=ACCENT, fg="#9fa8da",
        ).pack()
        tk.Label(
            header, text="powered by srperaro",
            font=("Segoe UI", 7), bg=ACCENT, fg="#534d8a",
        ).pack(pady=(4, 0))

        # Body
        body = tk.Frame(self, bg=BG, padx=24, pady=20)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(6, weight=1)

        self._input_var  = tk.StringVar()
        self._output_var = tk.StringVar(
            value=str(Path.home() / "Desktop" / "generated_pdfs")
        )

        self._folder_row(body, "Input folder  (.eml files):", self._input_var,
                         self._browse_input,  grid_row=0)
        self._folder_row(body, "Output folder  (PDFs will be saved here):", self._output_var,
                         self._browse_output, grid_row=2)

        # Convert button
        btn_wrap = tk.Frame(body, bg=BG)
        btn_wrap.grid(row=4, column=0, columnspan=3, pady=(20, 10), sticky="ew")
        btn_wrap.columnconfigure(0, weight=1)

        self._btn = tk.Button(
            btn_wrap, text="   Convert   ",
            font=("Segoe UI", 11, "bold"),
            bg=ACCENT, fg=BTN_FG,
            activebackground="#283593", activeforeground=BTN_FG,
            relief="flat", cursor="hand2", padx=28, pady=9,
            command=self._start_conversion,
        )
        self._btn.grid(row=0, column=0)

        # Progress bar
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor="#dce0ff", background=ACCENT, bordercolor=BG, lightcolor=ACCENT,
        )
        self._progress = ttk.Progressbar(
            body, mode="determinate", style="Accent.Horizontal.TProgressbar"
        )
        self._progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        # Log area
        tk.Label(body, text="Log", font=("Segoe UI", 8, "bold"),
                 bg=BG, fg="#888").grid(row=6, column=0, columnspan=3,
                                        sticky="w", pady=(0, 2))
        self._log = scrolledtext.ScrolledText(
            body, height=10,
            bg=LOG_BG, fg=LOG_FG,
            font=("Consolas", 9),
            relief="flat",
            state="disabled",
            insertbackground=LOG_FG,
        )
        self._log.grid(row=7, column=0, columnspan=3, sticky="nsew")
        self._log.tag_config("ok",   foreground=LOG_OK)
        self._log.tag_config("err",  foreground=LOG_ERR)
        self._log.tag_config("info", foreground=LOG_INFO)
        self._log.tag_config("warn", foreground=LOG_WARN)
        body.rowconfigure(7, weight=1)

        # Status bar
        self._status = tk.StringVar(value="Ready.")
        tk.Label(
            self, textvariable=self._status,
            anchor="w", font=("Segoe UI", 8),
            bg="#e0e0e0", fg="#555", relief="flat", padx=10,
        ).pack(fill="x", side="bottom")

    def _folder_row(self, parent, label, var, command, grid_row):
        tk.Label(
            parent, text=label, font=("Segoe UI", 9, "bold"),
            bg=BG, fg="#333",
        ).grid(row=grid_row, column=0, columnspan=3, sticky="w", pady=(10, 2))

        entry = tk.Entry(
            parent, textvariable=var,
            font=("Segoe UI", 9), relief="solid", bd=1, bg="white",
        )
        entry.grid(row=grid_row + 1, column=0, columnspan=2,
                   sticky="ew", ipady=5, padx=(0, 6))

        tk.Button(
            parent, text="Browse…",
            font=("Segoe UI", 9),
            bg=ACCENT_LITE, fg=ACCENT,
            relief="flat", cursor="hand2",
            command=command,
        ).grid(row=grid_row + 1, column=2, sticky="ew")

    # ------------------------------------------------------------ Browsing

    def _browse_input(self):
        path = filedialog.askdirectory(title="Select folder with .eml files")
        if path:
            self._input_var.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select output folder for PDFs")
        if path:
            self._output_var.set(path)

    # ---------------------------------------------------------- Conversion

    def _start_conversion(self):
        if self._running:
            return

        input_dir  = Path(self._input_var.get().strip())
        output_dir = Path(self._output_var.get().strip())

        if not self._input_var.get().strip() or not input_dir.is_dir():
            self._log_line("Please select a valid input folder.", tag="err")
            return

        files = sorted(input_dir.glob("*.eml"))
        if not files:
            self._log_line(f"No .eml files found in:  {input_dir}", tag="warn")
            return

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._log_line(f"Cannot create output folder: {e}", tag="err")
            return

        self._running = True
        self._btn.config(state="disabled", text="   Converting…   ")
        self._progress.configure(maximum=len(files), value=0)
        self._status.set(f"Starting — {len(files)} file(s) to process…")

        self._log_line(f"Input   : {input_dir}", tag="info")
        self._log_line(f"Output  : {output_dir}", tag="info")
        self._log_line(f"Files   : {len(files)}", tag="info")
        self._log_line("─" * 58)

        threading.Thread(
            target=self._run_conversion,
            args=(files, output_dir),
            daemon=True,
        ).start()

    def _run_conversion(self, files, output_dir):
        ok = errors = 0
        for eml in files:
            self._q(None, f"  ⏳  {eml.name}")
            try:
                pdf = process_eml(str(eml), str(output_dir))
                self._q("ok",  f"  ✔   {Path(pdf).name}")
                ok += 1
            except Exception as ex:
                self._q("err", f"  ✘   {eml.name}\n       {ex}")
                errors += 1
            self._q("__tick__", None)

        self._q("", "─" * 58)
        tag = "ok" if not errors else ("warn" if ok else "err")
        self._q(tag, f"  Done — {ok} converted, {errors} error(s).")
        self._q("__done__", None)

    # ---------------------------------------------------------- Log thread

    def _q(self, tag, msg):
        """Put a message on the queue from the worker thread."""
        self._log_queue.put((tag, msg))

    def _poll_log(self):
        try:
            while True:
                tag, msg = self._log_queue.get_nowait()
                if tag == "__tick__":
                    self._progress["value"] += 1
                    done  = int(self._progress["value"])
                    total = int(self._progress["maximum"])
                    self._status.set(f"Converting…  {done} / {total}")
                elif tag == "__done__":
                    self._running = False
                    self._btn.config(state="normal", text="   Convert   ")
                    self._status.set("Done.")
                else:
                    self._log_line(msg, tag=tag or None)
        except queue.Empty:
            pass
        self.after(80, self._poll_log)

    def _log_line(self, text, tag=None):
        self._log.config(state="normal")
        self._log.insert("end", text + "\n", tag or "")
        self._log.see("end")
        self._log.config(state="disabled")

    # --------------------------------------------------------------- Util

    def _center(self, w, h):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    App().mainloop()
