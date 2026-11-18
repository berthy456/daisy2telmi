"""Tkinter front end: pick a DAISY pack and an output folder, watch the conversion log.

Drop a pack on the window when tkinterdnd2 is installed; otherwise use the browse
buttons. The conversion runs on a worker thread so the window stays responsive.

The Options window holds the language and the speech settings; both are read from
and written to `settings.py`, so the command line sees the same choices.
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import settings, tts
from .cli import convert
from .i18n import LANGUAGES, text
from .telmi_builder import Announce

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # drag and drop is a bonus, browsing works without it
    DND_FILES = None
    TkinterDnD = None

log = logging.getLogger("daisy2telmi")

ANNOUNCE_MODES = ("prompt", "chapter", "off")
ANNOUNCE_KEYS = {"prompt": "announce_prompt", "chapter": "announce_chapter", "off": "announce_off"}


class _QueueHandler(logging.Handler):
    """Ship log records to the Tk thread; widgets are only touched from the main thread."""

    def __init__(self, sink: queue.Queue) -> None:
        super().__init__(logging.INFO)
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self.sink.put_nowait(self.format(record))


class App:
    def __init__(self, root: tk.Misc, options: dict | None = None) -> None:
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.options = dict(settings.DEFAULTS, **(options or settings.load()))
        self.pack_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.force_var = tk.BooleanVar(value=False)
        self.language_var = tk.StringVar(value=self.options["language"])
        self._labels: dict[str, tk.Widget] = {}
        self._build()
        root.after(100, self._drain)

    def t(self, key: str) -> str:
        return text(self.language_var.get(), key)

    def _label(self, parent: tk.Widget, key: str, **kwargs) -> ttk.Label:
        widget = ttk.Label(parent, text=self.t(key), **kwargs)
        self._labels[key] = widget
        return widget

    def _button(self, parent: tk.Widget, key: str, command, **kwargs) -> ttk.Button:
        widget = ttk.Button(parent, text=self.t(key), command=command, **kwargs)
        self._labels[key] = widget
        return widget

    def _build(self) -> None:
        grid = ttk.Frame(self.root, padding=12)
        grid.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(5, weight=1)

        self._label(grid, "pack_label").grid(row=0, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.pack_var).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        buttons = ttk.Frame(grid)
        buttons.grid(row=1, column=2, sticky="e", padx=(6, 0))
        self._button(buttons, "browse_zip", self._pick_pack_file).pack(side="left")
        self._button(buttons, "browse_folder", self._pick_pack_dir).pack(side="left", padx=(4, 0))

        self._label(grid, "output_label").grid(row=2, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.out_var).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._button(grid, "browse_output", self._pick_out_dir).grid(row=3, column=2, sticky="e", padx=(6, 0))

        controls = ttk.Frame(grid)
        controls.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.convert_button = self._button(controls, "convert", self._start)
        self.convert_button.pack(side="left")
        self._button(controls, "options", self._open_options).pack(side="left", padx=12)
        self.force_box = ttk.Checkbutton(
            controls, text=self.t("overwrite"), variable=self.force_var
        )
        self._labels["overwrite"] = self.force_box
        self.force_box.pack(side="left", padx=12)
        self.progress = ttk.Progressbar(controls, mode="indeterminate", length=140)
        self.progress.pack(side="right")

        self.log_view = tk.Text(grid, height=18, width=72, state="disabled", wrap="word")
        self.log_view.grid(row=5, column=0, columnspan=3, sticky="nsew")
        scroll = ttk.Scrollbar(grid, command=self.log_view.yview)
        scroll.grid(row=5, column=3, sticky="ns")
        self.log_view.configure(yscrollcommand=scroll.set)

        hint = self.t("drop_hint") if DND_FILES else self.t("drop_unavailable")
        self._append(hint)

        if DND_FILES:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

    def _relabel(self) -> None:
        self.root.title(self.t("app_title"))
        for key, widget in self._labels.items():
            widget.configure(text=self.t(key))
        if not DND_FILES:
            self._append(self.t("drop_unavailable"))

    def _open_options(self) -> None:
        Options(self)

    def announce(self) -> Announce:
        return Announce(
            mode=self.options["announce"],
            language=self.language_var.get(),
            autoplay=self.options["autoplay"],
            engine=self.options["tts"],
            voice=self.options["voice"],
            command=self.options["command"],
        )

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
        announce = self.announce()
        threading.Thread(
            target=self._run, args=(source, out_dir, self.force_var.get(), announce), daemon=True
        ).start()

    def _run(self, source: Path, out_dir: Path, force: bool, announce: Announce) -> None:
        self.events.put(("code", convert(source, out_dir, force, announce)))

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


class Options:
    """Language and speech settings, saved when the window closes.

    The boxes show translated names, so each one keeps its own list of keys in
    the same order as the values it displays and reads the choice back by index.
    """

    def __init__(self, app: App) -> None:
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.title(app.t("opt_title"))
        self.top.resizable(False, False)

        self.language_keys = list(LANGUAGES)
        self.announce_keys = list(ANNOUNCE_MODES)
        self.engine_keys = ["auto"] + [engine.name for engine in tts.engines()] + ["off"]

        grid = ttk.Frame(self.top, padding=12)
        grid.grid(sticky="nsew")
        grid.columnconfigure(1, weight=1)

        self.language_box = self._combo(self.language_keys, app.options["language"])
        self.announce_box = self._combo(self.announce_keys, app.options["announce"])
        self.engine_box = self._combo(self.engine_keys, app.options["tts"])
        self.voice_box = self._combo([None], app.options["voice"])
        self.autoplay_var = tk.BooleanVar(value=bool(app.options["autoplay"]))

        self._row(grid, "opt_language", 0, self.language_box)
        self._row(grid, "opt_announce", 1, self.announce_box)
        self._row(grid, "opt_autoplay", 2, ttk.Checkbutton(grid, variable=self.autoplay_var))
        self._row(grid, "opt_engine", 3, self.engine_box)
        self._row(grid, "opt_voice", 4, self.voice_box)
        ttk.Button(grid, text=app.t("opt_close"), command=self._close).grid(
            row=5, column=0, columnspan=2, sticky="e", pady=(12, 0)
        )

        self.engine_box.bind("<<ComboboxSelected>>", lambda _e: self._fill_voices())
        self.language_box.bind("<<ComboboxSelected>>", lambda _e: self._fill_voices())
        self._fill_voices()

    def _label_text(self, key: str | None) -> str:
        if key is None:
            return self.app.t("voice_default")
        if key == "auto":
            return self.app.t("engine_auto")
        if key == "off":
            return self.app.t("engine_off")
        if key in ANNOUNCE_KEYS:
            return self.app.t(ANNOUNCE_KEYS[key])
        if key in LANGUAGES:
            return f"{key} - {LANGUAGES[key].name}"
        return next((e.label for e in tts.engines() if e.name == key), key)

    def _combo(self, keys: list[str | None], current: str | None) -> ttk.Combobox:
        box = ttk.Combobox(self.top, values=[self._label_text(k) for k in keys], state="readonly", width=26)
        box.set(self._label_text(current if current in keys else keys[0]))
        return box

    def _chosen(self, box: ttk.Combobox, keys: list[str | None]) -> str | None:
        labels = [self._label_text(k) for k in keys]
        try:
            return keys[labels.index(box.get())]
        except ValueError:
            return keys[0]

    def _row(self, grid: ttk.Frame, key: str, row: int, widget: tk.Widget) -> None:
        ttk.Label(grid, text=self.app.t(key)).grid(row=row, column=0, sticky="w", pady=4)
        widget.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=4)

    def _fill_voices(self) -> None:
        code = self._chosen(self.language_box, self.language_keys)
        engine = self._chosen(self.engine_box, self.engine_keys)
        names: list[str | None] = [None]
        if engine not in (None, "auto", "off"):
            names += tts.voices(engine, LANGUAGES.get(code, LANGUAGES["en"]))
        self.voice_keys = names
        self.voice_box.configure(values=[self._label_text(k) for k in names])
        self.voice_box.set(self._label_text(None))

    def _close(self) -> None:
        self.app.options.update(
            {
                "language": self._chosen(self.language_box, self.language_keys),
                "announce": self._chosen(self.announce_box, self.announce_keys),
                "autoplay": self.autoplay_var.get(),
                "tts": self._chosen(self.engine_box, self.engine_keys),
                "voice": self._chosen(self.voice_box, self.voice_keys),
            }
        )
        self.app.language_var.set(self.app.options["language"])
        self.app._relabel()
        try:
            settings.save(self.app.options)
        except OSError as exc:
            self.app._append(f"ERROR: could not save options: {exc}")
        self.top.destroy()


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
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    app = App(root)
    root.title(app.t("app_title"))
    handler = attach_log_handler(app)
    try:
        root.mainloop()
    finally:
        log.removeHandler(handler)
    return 0
