"""Tkinter front end: pick a DAISY pack and an output folder, watch the conversion log.

Drop a pack on the window when tkinterdnd2 is installed; otherwise use the browse
buttons. The conversion runs on a worker thread so the window stays responsive.
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from .cli import convert

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # drag and drop is a bonus, browsing works without it
    DND_FILES = None
    TkinterDnD = None

log = logging.getLogger("daisy2telmi")


class _QueueHandler(logging.Handler):
    """Ship log records to the Tk thread; widgets are only touched from the main thread."""

    def __init__(self, sink: queue.Queue) -> None:
        super().__init__(logging.INFO)
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self.sink.put_nowait(self.format(record))


class App:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.pack_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.force_var = tk.BooleanVar(value=False)
        self._build()
        root.after(100, self._drain)

    def _build(self) -> None:
        grid = ttk.Frame(self.root, padding=12)
        grid.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(5, weight=1)

        ttk.Label(grid, text="DAISY pack").grid(row=0, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.pack_var).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        buttons = ttk.Frame(grid)
        buttons.grid(row=1, column=2, sticky="e", padx=(6, 0))
        ttk.Button(buttons, text="Zip…", command=self._pick_pack_file).pack(side="left")
        ttk.Button(buttons, text="Folder…", command=self._pick_pack_dir).pack(side="left", padx=(4, 0))

        ttk.Label(grid, text="Output folder").grid(row=2, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.out_var).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(grid, text="Choose…", command=self._pick_out_dir).grid(row=3, column=2, sticky="e", padx=(6, 0))

        controls = ttk.Frame(grid)
        controls.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.convert_button = ttk.Button(controls, text="Convert", command=self._start)
        self.convert_button.pack(side="left")
        ttk.Checkbutton(controls, text="overwrite an existing story folder", variable=self.force_var).pack(
            side="left", padx=12
        )
        self.progress = ttk.Progressbar(controls, mode="indeterminate", length=140)
        self.progress.pack(side="right")

        self.log_view = tk.Text(grid, height=18, width=72, state="disabled", wrap="word")
        self.log_view.grid(row=5, column=0, columnspan=3, sticky="nsew")
        scroll = ttk.Scrollbar(grid, command=self.log_view.yview)
        scroll.grid(row=5, column=3, sticky="ns")
        self.log_view.configure(yscrollcommand=scroll.set)

        hint = "Drop a DAISY pack anywhere in this window, or use the buttons above."
        self._append(hint if DND_FILES else "Install tkinterdnd2 to drop a pack on the window.")

        if DND_FILES:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

    def _pick_pack_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("DAISY packs", "*.zip"), ("all files", "*.*")])
        if path:
            self.pack_var.set(path)

    def _pick_pack_dir(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.pack_var.set(path)

    def _pick_out_dir(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.out_var.set(path)

    def _on_drop(self, event: tk.Event) -> None:
        dropped = self.root.tk.splitlist(event.data)
        if dropped:
            self.pack_var.set(dropped[0])

    def _append(self, line: str) -> None:
        self.log_view.configure(state="normal")
        self.log_view.insert("end", line + "\n")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def _start(self) -> None:
        source = Path(self.pack_var.get().strip()).expanduser()
        out_dir = Path(self.out_var.get().strip()).expanduser()
        if not str(source):
            self._append("ERROR: choose a DAISY pack first")
            return
        if not source.exists():
            self._append(f"ERROR: no such pack: {source}")
            return
        if not str(out_dir):
            self._append("ERROR: choose an output folder first")
            return
        out_dir.mkdir(parents=True, exist_ok=True)

        self.convert_button.state(["disabled"])
        self.progress.start(12)
        threading.Thread(target=self._run, args=(source, out_dir, self.force_var.get()), daemon=True).start()

    def _run(self, source: Path, out_dir: Path, force: bool) -> None:
        self.events.put(("code", convert(source, out_dir, force)))

    def _drain(self) -> None:
        while True:
            try:
                item = self.events.get_nowait()
            except queue.Empty:
                break
            if item[0] == "code":
                self.progress.stop()
                self.convert_button.state(["!disabled"])
                self._append("done" if item[1] == 0 else f"failed with exit code {item[1]}")
            else:
                self._append(item)

        self.root.after(100, self._drain)


def attach_log_handler(app: App) -> logging.Handler:
    """Route the converter's log records into the app's queue."""
    handler = _QueueHandler(app.events)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    log.addHandler(handler)
    # Without this the logger keeps the root's WARNING level and the window stays blank.
    log.setLevel(logging.INFO)
    return handler


def make_root() -> tk.Misc:
    """tkinterdnd2 only adds the drop methods to its own root class."""
    return TkinterDnD.Tk() if TkinterDnD else tk.Tk()


def run_gui() -> int:
    root = make_root()
    root.title("daisy2telmi")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    app = App(root)
    handler = attach_log_handler(app)
    try:
        root.mainloop()
    finally:
        log.removeHandler(handler)
    return 0
