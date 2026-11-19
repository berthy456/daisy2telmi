"""Tkinter front end: pick a DAISY pack and an output folder, watch the conversion log.

Drop a pack on the window when tkinterdnd2 is installed; otherwise use the browse
buttons. The conversion runs on a worker thread so the window stays responsive.

The Options window holds the language and the speech settings; both are read from
and written to `settings.py`, so the command line sees the same choices.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import audio, chapters, images, settings, tts
from .cli import FORMATS, convert
from .detector import DaisyPackError, open_pack
from .extractor import CUT_LEVELS, extract
from .i18n import LANGUAGES, text
from .telmi_builder import Announce, slugify

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
        self.cover_var = tk.StringVar()
        self.crop_var = tk.StringVar(value=self.options["cover_crop"])
        self.format_var = tk.StringVar(value=self.options["format"])
        self._previews: tuple[str, dict[str, bytes]] | None = None
        self._crop_images: dict[str, tk.PhotoImage] = {}
        self.force_var = tk.BooleanVar(value=False)
        self.language_var = tk.StringVar(value=self.options["language"])
        self.cut = self.options["cut"]
        self.dropped: set[int] = set()
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
        grid.rowconfigure(8, weight=1)

        self._label(grid, "pack_label").grid(row=0, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.pack_var).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        buttons = ttk.Frame(grid)
        buttons.grid(row=1, column=2, sticky="e", padx=(6, 0))
        self._button(buttons, "browse_zip", self._pick_pack_file).pack(side="left")
        self._button(buttons, "browse_folder", self._pick_pack_dir).pack(side="left", padx=(4, 0))

        self._label(grid, "output_label").grid(row=2, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.out_var).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._button(grid, "browse_output", self._pick_out_dir).grid(row=3, column=2, sticky="e", padx=(6, 0))

        self._label(grid, "cover_label").grid(row=4, column=0, sticky="w", pady=(0, 2))
        ttk.Entry(grid, textvariable=self.cover_var).grid(row=4, column=1, sticky="ew", padx=(6, 0))
        self._button(grid, "browse_cover", self._pick_cover).grid(row=4, column=2, sticky="e", padx=(6, 0))

        crop_row = ttk.Frame(grid)
        crop_row.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._label(crop_row, "cover_crop_label").pack(side="left", padx=(0, 10))
        self.crop_boxes: dict[str, ttk.Radiobutton] = {}
        for mode in images.CROP_MODES:
            box = ttk.Radiobutton(
                crop_row,
                text=self.t(f"crop_{mode}"),
                variable=self.crop_var,
                value=mode,
                compound="top",
                command=self._pick_crop,
            )
            self._labels[f"crop_{mode}"] = box
            box.pack(side="left", padx=(0, 10))
            self.crop_boxes[mode] = box
        self.cover_var.trace_add("write", lambda *_: self._show_crop())

        format_row = ttk.Frame(grid)
        format_row.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._label(format_row, "format_label").pack(side="left", padx=(0, 10))
        for player in FORMATS:
            box = ttk.Radiobutton(
                format_row,
                text=self.t(f"fmt_{player}"),
                variable=self.format_var,
                value=player,
                command=self._pick_format,
            )
            self._labels[f"fmt_{player}"] = box
            box.pack(side="left", padx=(0, 12))

        controls = ttk.Frame(grid)
        controls.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 8))
        self.convert_button = self._button(controls, "convert", self._start)
        self.convert_button.pack(side="left")
        self._button(controls, "options", self._open_options).pack(side="left", padx=12)
        self._button(controls, "chapters", self._open_chapters).pack(side="left")
        self.force_box = ttk.Checkbutton(
            controls, text=self.t("overwrite"), variable=self.force_var
        )
        self._labels["overwrite"] = self.force_box
        self.force_box.pack(side="left", padx=12)
        self.progress = ttk.Progressbar(controls, mode="indeterminate", length=140)
        self.progress.pack(side="right")

        self.log_view = tk.Text(grid, height=18, width=72, state="disabled", wrap="word")
        self.log_view.grid(row=8, column=0, columnspan=3, sticky="nsew")
        scroll = ttk.Scrollbar(grid, command=self.log_view.yview)
        scroll.grid(row=8, column=3, sticky="ns")
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

    def _open_chapters(self) -> None:
        source = self._typed_path(self.pack_var)
        if source is None or not source.exists():
            self._append("ERROR: choose a DAISY pack first")
            return
        ChapterList(self, source)

    def announce(self) -> Announce:
        return Announce(
            mode=self.options["announce"],
            language=self.language_var.get(),
            autoplay=self.options["autoplay"],
            engine=self.options["tts"],
            voice=self.options["voice"],
            command=self.options["command"],
            python=self.options["python"],
            clip=self.options["clip"],
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

    def _pick_cover(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("all files", "*.*")]
        )
        if path:
            self.cover_var.set(path)

    def _pick_crop(self) -> None:
        self.options["cover_crop"] = self.crop_var.get()
        settings.save(self.options)

    def _pick_format(self) -> None:
        self.options["format"] = self.format_var.get()
        settings.save(self.options)

    def _show_crop(self) -> None:
        """Draw each crop band on its own button: which band a tall cover loses
        is not something a word can tell you."""
        source = self._typed_path(self.cover_var)
        if source is None or not source.is_file():
            for box in self.crop_boxes.values():
                box.configure(image="")
            self._crop_images.clear()
            return
        if self._previews is None or self._previews[0] != str(source):
            try:
                self._previews = (str(source), images.crop_previews(source))
            except images.ImageError as exc:
                self._append(f"ERROR: {exc}")
                return
        for mode, png in self._previews[1].items():
            self._crop_images[mode] = tk.PhotoImage(data=png)
            self.crop_boxes[mode].configure(image=self._crop_images[mode])

    def _on_drop(self, event: tk.Event) -> None:
        dropped = self.root.tk.splitlist(event.data)
        if dropped:
            self.pack_var.set(dropped[0])

    def _append(self, line: str) -> None:
        self.log_view.configure(state="normal")
        self.log_view.insert("end", line + "\n")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def _typed_path(self, var: tk.StringVar) -> Path | None:
        """The folder or file the box holds, or None when it is empty.

        An empty box must not become Path('.'), which exists and would be read as
        the working directory.
        """
        typed = var.get().strip()
        return Path(typed).expanduser() if typed else None

    def _start(self) -> None:
        source = self._typed_path(self.pack_var)
        out_dir = self._typed_path(self.out_var)
        if source is None:
            self._append("ERROR: choose a DAISY pack first")
            return
        if not source.exists():
            self._append(f"ERROR: no such pack: {source}")
            return
        if out_dir is None:
            self._append("ERROR: choose an output folder first")
            return
        cover = self._typed_path(self.cover_var)
        if cover is not None and not cover.exists():
            self._append(f"ERROR: no such image: {cover}")
            return
        out_dir.mkdir(parents=True, exist_ok=True)

        self.convert_button.state(["disabled"])
        self.progress.start(12)
        announce = self.announce()
        dropped = sorted(self.dropped)
        threading.Thread(
            target=self._run,
            args=(
                source,
                out_dir,
                self.force_var.get(),
                announce,
                cover,
                ",".join(str(number) for number in dropped) if dropped else None,
                self.cut,
                self.format_var.get(),
                self.crop_var.get(),
            ),
            daemon=True,
        ).start()

    def _run(
        self,
        source: Path,
        out_dir: Path,
        force: bool,
        announce: Announce,
        cover: Path | None,
        drop: str | None,
        cut: str,
        fmt: str,
        crop: str,
    ) -> None:
        self.events.put(("code", convert(source, out_dir, force, announce, cover, drop, cut, fmt, crop)))

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


class ChapterList:
    """The pack's chapters: listen to one, uncheck the ones to leave out.

    The pack stays open while the window is up, so listening costs no extra work.
    Durations and previews run on worker threads and post their results to a queue
    the Tk thread drains: widgets may only be touched from the thread that made
    them.
    """

    def __init__(self, app: App, source: Path) -> None:
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.title(app.t("chapters"))
        self.events: queue.Queue = queue.Queue()
        self.packs = contextlib.ExitStack()
        try:
            self.pack = self.packs.enter_context(open_pack(source))
        except (DaisyPackError, OSError) as exc:
            self.top.destroy()
            app._append(f"ERROR: {exc}")
            return

        self.cut = app.cut
        self.reported = False
        grid = ttk.Frame(self.top, padding=12)
        grid.grid(sticky="nsew")
        grid.columnconfigure(0, weight=1)

        # The levels stay shut until the pack has been read: which of them the
        # pack can actually cut at is only known once its own outline is in hand.
        chooser = ttk.Frame(grid)
        chooser.grid(row=0, column=0, sticky="w")
        ttk.Label(chooser, text=app.t("cut_level")).pack(side="left")
        self.cut_var = tk.StringVar(value=self.cut)
        self.cut_boxes: dict[str, ttk.Radiobutton] = {}
        for level in CUT_LEVELS:
            box = ttk.Radiobutton(
                chooser,
                text=app.t(f"cut_{level}"),
                variable=self.cut_var,
                value=level,
                command=lambda chosen=level: self._choose(chosen),
            )
            box.state(["disabled"])
            box.pack(side="left", padx=(8, 0))
            self.cut_boxes[level] = box
        self.counts = ttk.Label(grid, text=app.t("cut_hint"))
        self.counts.grid(row=1, column=0, sticky="w", pady=(2, 6))
        ttk.Label(grid, text=app.t("chapters_hint")).grid(row=2, column=0, sticky="w", pady=(0, 6))

        self.rows = ttk.Frame(grid)
        self.rows.grid(row=3, column=0, sticky="nsew")
        self._build()
        self.top.protocol("WM_DELETE_WINDOW", self._close)

        threading.Thread(target=self._measure, daemon=True).start()
        self.top.after(100, self._drain)

    def _build(self) -> None:
        """(Re)draw the part list for the level now chosen."""
        for child in self.rows.winfo_children():
            child.destroy()
        self.book = extract(self.pack, self.cut)
        self.info = chapters.describe(self.book, with_durations=False)
        self.cache = (
            Path(tempfile.gettempdir()) / "daisy2telmi-preview" / (slugify(self.book.title) or "pack")
        )
        self.keep: list[tk.BooleanVar] = []
        self.sizes: list[ttk.Label] = []
        self.play_buttons: list[ttk.Button] = []

        self.rows.columnconfigure(2, weight=1)
        for offset, info in enumerate(self.info):
            box = tk.BooleanVar(value=info.number not in self.app.dropped)
            self.keep.append(box)
            ttk.Checkbutton(self.rows, variable=box).grid(row=offset, column=0, sticky="w")
            ttk.Label(self.rows, text=str(info.number)).grid(row=offset, column=1, sticky="w", padx=(4, 8))
            ttk.Label(self.rows, text=info.title).grid(row=offset, column=2, sticky="w")
            size = ttk.Label(self.rows, text="")
            size.grid(row=offset, column=3, sticky="e", padx=(12, 0))
            self.sizes.append(size)
            button = ttk.Button(
                self.rows,
                text=self.app.t("chapters_play"),
                width=8,
                command=lambda index=offset: self._play(index),
            )
            button.grid(row=offset, column=4, sticky="e", padx=(12, 0))
            self.play_buttons.append(button)

        ttk.Button(
            self.rows, text=self.app.t("opt_close"), command=self._close
        ).grid(row=len(self.info), column=0, columnspan=5, sticky="e", pady=(10, 0))

    def _offer_levels(self, rows: list[chapters.LevelInfo]) -> None:
        """Open the levels the pack's own outline can cut at, and grey out the rest.

        A level that gives no more parts than the one above it only repeats that
        level, so the pack has nothing to cut at there. The audio is never asked.
        """
        available: list[str] = []
        parts = 0
        for row in rows:
            if row.parts > parts:
                available.append(row.level)
                parts = row.parts
        for level, box in self.cut_boxes.items():
            box.state(["!disabled"] if level in available else ["disabled"])
        if self.cut not in available:
            self._choose(available[min(CUT_LEVELS.index(self.cut), len(available) - 1)])

    def _choose(self, level: str) -> None:
        """A different level is a different book: the old part numbers mean nothing."""
        if level == self.cut:
            return
        self.cut = level
        self.cut_var.set(level)
        self.app.cut = level
        self.app.dropped = set()
        self._build()
        threading.Thread(target=self._measure, daemon=True).start()

    def _measure(self) -> None:
        cut = self.cut
        self.events.put(("sizes", (cut, chapters.describe(extract(self.pack, cut)))))
        if not self.reported:
            self.reported = True
            books = {level: extract(self.pack, level) for level in CUT_LEVELS}
            self.events.put(("counts", chapters.describe_levels(books)))

    def _play(self, index: int) -> None:
        for button in self.play_buttons:
            button.state(["disabled"])
        threading.Thread(
            target=self._render, args=(self.info[index], self.book.chapters[index]), daemon=True
        ).start()

    def _render(self, info: chapters.ChapterInfo, chapter) -> None:
        try:
            self.events.put(("play", chapters.render_preview(info, chapter, self.cache)))
        except (chapters.ChapterError, audio.AudioError) as exc:
            self.events.put(("error", str(exc)))

    def _enable(self) -> None:
        for button in self.play_buttons:
            button.state(["!disabled"])

    def _drain(self) -> None:
        if not self.top.winfo_exists():
            return
        while True:
            try:
                item = self.events.get_nowait()
            except queue.Empty:
                break
            kind, payload = item[0], item[1]
            if kind == "sizes":
                cut, rows = payload
                if cut != self.cut:
                    continue  # a rebuild already replaced the rows these were measured for
                for label, info in zip(self.sizes, rows):
                    label.configure(text=chapters.format_seconds(info.seconds))
            elif kind == "counts":
                self.counts.configure(
                    text="   ".join(
                        f"{self.app.t(f'cut_{row.level}')} {row.parts}"
                        f" ({chapters.format_seconds(row.each)})"
                        for row in payload
                    )
                )
                self._offer_levels(payload)
            elif kind == "play":
                try:
                    chapters.open_preview(payload)
                except chapters.ChapterError as exc:
                    self.app._append(f"ERROR: {exc}")
                self._enable()
            else:
                self.app._append(f"ERROR: {payload}")
                self._enable()
        self.top.after(100, self._drain)

    def _close(self) -> None:
        self.app.dropped = {
            info.number for info, box in zip(self.info, self.keep) if not box.get()
        }
        self.app.options["cut"] = self.cut
        settings.save(self.app.options)
        self.packs.close()
        self.top.destroy()


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
        self.device_keys = list(tts.DEVICES)

        grid = ttk.Frame(self.top, padding=12)
        grid.grid(sticky="nsew")
        grid.columnconfigure(1, weight=1)

        self.language_box = self._combo(self.language_keys, app.options["language"])
        self.announce_box = self._combo(self.announce_keys, app.options["announce"])
        self.engine_box = self._combo(self.engine_keys, app.options["tts"])
        self.voice_box = self._combo([None], app.options["voice"])
        self.device_box = self._combo(self.device_keys, app.options["device"])
        self.autoplay_var = tk.BooleanVar(value=bool(app.options["autoplay"]))
        self.python_box = ttk.Entry(self.top, width=28)
        self.python_box.insert(0, app.options["python"] or "")

        clip_row = ttk.Frame(grid)
        self.clip_box = ttk.Entry(clip_row, width=22)
        self.clip_box.insert(0, app.options["clip"] or "")
        self.clip_box.pack(side="left")
        ttk.Button(clip_row, text=app.t("browse_output"), command=self._pick_clip).pack(side="left", padx=(6, 0))

        self._row(grid, "opt_language", 0, self.language_box)
        self._row(grid, "opt_announce", 1, self.announce_box)
        self._row(grid, "opt_autoplay", 2, ttk.Checkbutton(grid, variable=self.autoplay_var))
        self._row(grid, "opt_engine", 3, self.engine_box)
        self._row(grid, "opt_voice", 4, self.voice_box)
        self._row(grid, "opt_python", 5, self.python_box)
        self._row(grid, "opt_device", 6, self.device_box)
        self._row(grid, "opt_clip", 7, clip_row)
        ttk.Button(grid, text=app.t("opt_close"), command=self._close).grid(
            row=8, column=0, columnspan=2, sticky="e", pady=(12, 0)
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

    def _pick_clip(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("audio", "*.wav *.mp3 *.flac *.m4a"), ("all files", "*.*")])
        if path:
            self.clip_box.delete(0, "end")
            self.clip_box.insert(0, path)

    def _close(self) -> None:
        self.app.options.update(
            {
                "language": self._chosen(self.language_box, self.language_keys),
                "announce": self._chosen(self.announce_box, self.announce_keys),
                "autoplay": self.autoplay_var.get(),
                "tts": self._chosen(self.engine_box, self.engine_keys),
                "voice": self._chosen(self.voice_box, self.voice_keys),
                "python": self.python_box.get().strip() or None,
                "clip": self.clip_box.get().strip() or None,
                "device": self._chosen(self.device_box, self.device_keys),
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
