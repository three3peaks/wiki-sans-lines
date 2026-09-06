"""Local desktop UI for Wiki!Sans."""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import threading
import tkinter as tk
from dataclasses import asdict, dataclass
from pathlib import Path

from wiki_sans.config import get_config
from wiki_sans.paths import history_path, images_dir, resource_dir

ROOT_DIR = resource_dir()
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from wiki_sans.lexicon import load_or_build
from wiki_sans.memory import LetterBank, load_or_build_memory
from wiki_sans import nltk_setup, ollama_setup
from wiki_sans.rewrite import format_output, format_sources, rewrite_text

BG = "#1A0D1F"
PANEL = "#140916"
FG = "#FFFFFF"
MUTED = "#7A7A7A"
ACCENT = "#FFB800"
ACCENT_HOT = "#FFD24A"
ACCENT_DARK = "#C45A14"
BUTTON = "#2A1528"
ENTRY_BG = "#100810"
TRACK = "#241018"
CARD = "#2A1528"
CARD_HOT = "#3A1F30"
CARD_PICKED = "#3A2410"
HISTORY_LIMIT = 50


@dataclass
class HistoryEntry:
    source: str
    output: str
    sources: str
    engine: str


class ModernScrollbar(tk.Canvas):
    """Thin amber scrollbar that matches the character palette."""

    def __init__(self, master, command=None, **kwargs) -> None:
        super().__init__(
            master,
            width=10,
            highlightthickness=0,
            bd=0,
            bg=TRACK,
            **kwargs,
        )
        self.command = command
        self._first = 0.0
        self._last = 1.0
        self._grab = None
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_grab", None))
        self.bind("<Enter>", lambda _e: self._draw(hover=True))
        self.bind("<Leave>", lambda _e: self._draw(hover=False))

    def set(self, first, last) -> None:
        self._first = float(first)
        self._last = float(last)
        self._draw()

    def _draw(self, hover: bool = False) -> None:
        self.delete("all")
        height = max(self.winfo_height(), 1)
        width = max(self.winfo_width(), 1)
        self.create_rectangle(0, 0, width, height, fill=TRACK, outline="")
        span = self._last - self._first
        if span >= 0.999:
            return
        pad = 2
        thumb_h = max(28, int(span * (height - pad * 2)))
        thumb_y = pad + int(self._first * (height - pad * 2 - thumb_h))
        color = ACCENT_HOT if hover or self._grab is not None else ACCENT
        self.create_rectangle(
            2,
            thumb_y,
            width - 2,
            thumb_y + thumb_h,
            fill=color,
            outline="",
        )

    def _press(self, event) -> None:
        height = max(self.winfo_height(), 1)
        thumb_top = self._first * height
        thumb_bottom = self._last * height
        if thumb_top <= event.y <= thumb_bottom:
            self._grab = event.y - thumb_top
        elif self.command:
            self.command("moveto", event.y / height)
            self._grab = None

    def _move(self, event) -> None:
        if self._grab is None or not self.command:
            return
        height = max(self.winfo_height(), 1)
        self.command("moveto", max(0.0, (event.y - self._grab) / height))


class WikiSansApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.lexicon = None
        self.memory = None
        self.letters = None
        self.use_ollama = False
        self.busy = False
        self.mode = tk.StringVar(value=get_config().default_mode)
        self._photos: list[tk.PhotoImage] = []
        self._history: list[HistoryEntry] = []
        self._selected_history: int | None = None

        root.title("WIKI!Sans lines")
        root.minsize(960, 560)
        root.geometry("1180x840")
        root.configure(bg=BG)
        root.option_add("*Font", "{Segoe UI} 11")
        self._set_icon()

        self._build()
        self.status.set("Loading lexicon and connections...")
        self.root.after_idle(self._set_icon)
        self.root.after(100, self._start_loading)

    def _set_icon(self) -> None:
        ico = images_dir() / "wiki_sans_v2_face.ico"
        if not ico.exists():
            return
        path = ico
        try:
            self.root.iconbitmap(default=str(path))
            self.root.iconbitmap(str(path))
        except tk.TclError:
            path = Path(tempfile.gettempdir()) / "wiki_sans_app.ico"
            try:
                shutil.copyfile(ico, path)
                self.root.iconbitmap(default=str(path))
                self.root.iconbitmap(str(path))
            except (OSError, tk.TclError):
                return

    def _build(self) -> None:
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, minsize=260, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_history(body).grid(row=0, column=0, sticky="nsew")

        shell = tk.Frame(body, bg=BG)
        shell.grid(row=0, column=1, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(4, weight=2, minsize=72)
        shell.grid_rowconfigure(6, weight=2, minsize=72)
        shell.grid_rowconfigure(7, weight=3, minsize=96)

        header = tk.Frame(shell, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 0))
        tk.Label(
            header,
            text="WIKI!Sans lines",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w")

        self.checker = tk.Canvas(shell, height=10, bg=BG, highlightthickness=0, bd=0)
        self.checker.grid(row=1, column=0, sticky="ew", padx=18, pady=(8, 4))
        self.checker.bind("<Configure>", lambda _e: self._draw_checker())

        self.status = tk.StringVar(value="")
        tk.Label(
            shell,
            textvariable=self.status,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
            wraplength=720,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", padx=18)

        self._build_modes(shell).grid(row=3, column=0, sticky="ew", padx=18, pady=(8, 0))

        self._labeled_text(shell, "Source text", "input").grid(
            row=4, column=0, sticky="nsew", padx=18, pady=(8, 4)
        )

        buttons = tk.Frame(shell, bg=BG)
        buttons.grid(row=5, column=0, sticky="ew", padx=18, pady=(2, 8))
        self.run_button = self._button(
            buttons,
            "Interpret",
            self.interpret,
            filled=True,
        )
        self.run_button.pack(side="left")
        self.clear_button = self._button(
            buttons,
            "Clear",
            self.clear_input,
            filled=False,
        )
        self.clear_button.pack(side="left", padx=(10, 0))
        self.run_button.configure(state="disabled")

        self.sources_title = tk.StringVar(value="Where the words come from")
        self._labeled_text(
            shell, "Where the words come from", "sources", readonly=True, title_var=self.sources_title
        ).grid(row=6, column=0, sticky="nsew", padx=18, pady=(4, 4))

        speak = tk.Frame(shell, bg=BG)
        speak.grid(row=7, column=0, sticky="nsew", padx=18, pady=(4, 14))
        speak.grid_columnconfigure(0, weight=1)
        speak.grid_rowconfigure(1, weight=1)

        tk.Label(
            speak,
            text="He says",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).grid(row=0, column=0, sticky="w")

        bubble_row = tk.Frame(speak, bg=BG)
        bubble_row.grid(row=1, column=0, sticky="nsew")
        bubble_row.grid_columnconfigure(0, weight=1)
        bubble_row.grid_rowconfigure(0, weight=1)
        bubble = tk.Frame(bubble_row, bg=ACCENT, padx=2, pady=2)
        bubble.grid(row=0, column=0, sticky="nsew")
        inner = tk.Frame(bubble, bg=ENTRY_BG)
        inner.pack(fill="both", expand=True)
        self._make_text(inner, "output", readonly=True)
        tail = tk.Canvas(
            bubble_row,
            width=22,
            height=70,
            bg=BG,
            highlightthickness=0,
            bd=0,
        )
        tail.grid(row=0, column=1, sticky="ns")
        tail.create_polygon(0, 18, 22, 38, 0, 50, fill=ACCENT, outline=ACCENT)
        tail.create_polygon(0, 21, 16, 38, 0, 47, fill=ENTRY_BG, outline=ENTRY_BG)

        self.body_label = tk.Label(speak, bg=BG)
        self.body_label.grid(row=0, column=1, rowspan=2, sticky="s", padx=(8, 0))
        self._load_body()
        self._history = self._load_history()
        self._render_history()
        self._paint_modes()

    def _build_modes(self, parent: tk.Misc) -> tk.Frame:
        wrap = tk.Frame(parent, bg=BG)
        tk.Label(
            wrap,
            text="Mode",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w")
        row = tk.Frame(wrap, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        self._mode_buttons: dict[str, tk.Button] = {}
        for key, label in (
            ("sentence", "Sentence mode"),
            ("word", "Word mode"),
            ("letter", "Letter mode"),
        ):
            button = tk.Button(
                row,
                text=label,
                command=lambda value=key: self._set_mode(value),
                relief="flat",
                padx=14,
                pady=6,
                font=("Segoe UI", 10),
                cursor="hand2",
                bd=0,
            )
            button.pack(side="left", padx=(0, 8))
            self._mode_buttons[key] = button
        return wrap

    def _set_mode(self, mode: str) -> None:
        self.mode.set(mode)
        self._paint_modes()

    def _paint_modes(self) -> None:
        current = self.mode.get()
        titles = {
            "sentence": "Where the lines come from",
            "word": "Where the words come from",
            "letter": "Where the words and letters come from",
        }
        if hasattr(self, "sources_title"):
            self.sources_title.set(titles.get(current, titles["word"]))
        for key, button in getattr(self, "_mode_buttons", {}).items():
            if key == current:
                button.configure(
                    bg=ACCENT,
                    fg=BG,
                    activebackground=ACCENT_HOT,
                    activeforeground=BG,
                    font=("Segoe UI", 10, "bold"),
                )
            else:
                button.configure(
                    bg=BUTTON,
                    fg=FG,
                    activebackground=ACCENT_DARK,
                    activeforeground=FG,
                    font=("Segoe UI", 10),
                )

    def _build_history(self, parent: tk.Misc) -> tk.Frame:
        wrap = tk.Frame(parent, bg=PANEL)
        wrap.grid_rowconfigure(1, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        header = tk.Frame(wrap, bg=PANEL)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(14, 8))
        tk.Label(
            header,
            text="History",
            bg=PANEL,
            fg=ACCENT,
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left")
        self.clear_history_button = self._button(
            header,
            "Clear",
            self.clear_history,
            filled=False,
        )
        self.clear_history_button.configure(padx=10, pady=4, font=("Segoe UI", 9))
        self.clear_history_button.pack(side="right")

        list_wrap = tk.Frame(wrap, bg=PANEL)
        list_wrap.grid(row=1, column=0, sticky="nsew", padx=(6, 4), pady=(0, 12))
        list_wrap.grid_rowconfigure(0, weight=1)
        list_wrap.grid_columnconfigure(0, weight=1)

        self.history_canvas = tk.Canvas(
            list_wrap,
            bg=PANEL,
            highlightthickness=0,
            bd=0,
        )
        scroll = ModernScrollbar(list_wrap, command=self.history_canvas.yview)
        self.history_canvas.configure(yscrollcommand=scroll.set)
        self.history_canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        self.history_inner = tk.Frame(self.history_canvas, bg=PANEL)
        self._history_window = self.history_canvas.create_window(
            (0, 0),
            window=self.history_inner,
            anchor="nw",
        )
        self.history_inner.bind(
            "<Configure>",
            lambda _e: self.history_canvas.configure(
                scrollregion=self.history_canvas.bbox("all")
            ),
        )
        self.history_canvas.bind(
            "<Configure>",
            lambda event: self.history_canvas.itemconfigure(
                self._history_window, width=event.width
            ),
        )
        self._bind_history_wheel(self.history_canvas)
        self._bind_history_wheel(self.history_inner)
        return wrap

    def _bind_history_wheel(self, widget: tk.Misc) -> None:
        widget.bind(
            "<Enter>",
            lambda _e: widget.bind_all("<MouseWheel>", self._history_wheel),
        )
        widget.bind(
            "<Leave>",
            lambda _e: widget.unbind_all("<MouseWheel>"),
        )

    def _history_wheel(self, event) -> str:
        self.history_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _preview(self, text: str, limit: int = 140) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 1].rstrip() + "…"

    def _load_history(self) -> list[HistoryEntry]:
        path = history_path()
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        entries: list[HistoryEntry] = []
        if not isinstance(raw, list):
            return entries
        for item in raw:
            if not isinstance(item, dict) or not item.get("source"):
                continue
            entries.append(
                HistoryEntry(
                    source=str(item.get("source", "")),
                    output=str(item.get("output", "")),
                    sources=str(item.get("sources", "")),
                    engine=str(item.get("engine", "local")),
                )
            )
            if len(entries) >= HISTORY_LIMIT:
                break
        return entries

    def _save_history(self) -> None:
        path = history_path()
        try:
            path.write_text(
                json.dumps([asdict(entry) for entry in self._history], ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def _render_history(self) -> None:
        for child in self.history_inner.winfo_children():
            child.destroy()
        if not self._history:
            empty = tk.Label(
                self.history_inner,
                text="No interpretations yet.",
                bg=PANEL,
                fg=MUTED,
                wraplength=200,
                justify="left",
                font=("Segoe UI", 9),
            )
            empty.pack(anchor="w", padx=8, pady=8)
            self._bind_history_wheel(empty)
            return
        for index, entry in enumerate(self._history):
            self._history_card(index, entry)

    def _history_card(self, index: int, entry: HistoryEntry) -> None:
        selected = index == self._selected_history
        bg = CARD_PICKED if selected else CARD
        border = ACCENT if selected else "#3A2030"
        card = tk.Frame(self.history_inner, bg=border, padx=1, pady=1)
        card.pack(fill="x", padx=4, pady=(0, 8))
        inner = tk.Frame(card, bg=bg)
        inner.pack(fill="both", expand=True)
        label = tk.Label(
            inner,
            text=self._preview(entry.source),
            bg=bg,
            fg=FG,
            wraplength=200,
            justify="left",
            anchor="nw",
            font=("Segoe UI", 9),
            padx=8,
            pady=8,
        )
        label.pack(fill="x")
        for widget in (card, inner, label):
            widget.bind("<Button-1>", lambda _e, i=index: self._open_history(i))
            widget.configure(cursor="hand2")
            self._bind_history_wheel(widget)

    def _open_history(self, index: int) -> None:
        if index < 0 or index >= len(self._history):
            return
        self._selected_history = index
        entry = self._history[index]
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", entry.source)
        self._set_readonly(self.output_text, entry.output)
        self._set_readonly(self.sources_text, entry.sources)
        extra = ""
        if entry.engine == "ollama":
            extra = "  ·  via Ollama"
        elif entry.engine == "mixed":
            extra = "  ·  local + Ollama"
        self.status.set(f"Restored from history.{extra}")
        self._render_history()

    def _remember(self, source: str, result) -> None:
        entry = HistoryEntry(
            source=source,
            output=format_output(result.text),
            sources=format_sources(result),
            engine=result.engine,
        )
        if self._history and self._history[0].source == source:
            self._history[0] = entry
        else:
            self._history.insert(0, entry)
        self._history = self._history[:HISTORY_LIMIT]
        self._selected_history = 0
        self._save_history()
        self._render_history()

    def clear_history(self) -> None:
        if not self._history:
            return
        self._history.clear()
        self._selected_history = None
        self._save_history()
        self._render_history()

    def _button(self, parent, text: str, command, *, filled: bool) -> tk.Button:
        if filled:
            return tk.Button(
                parent,
                text=text,
                command=command,
                bg=ACCENT,
                fg=BG,
                activebackground=ACCENT_HOT,
                activeforeground=BG,
                relief="flat",
                padx=18,
                pady=8,
                font=("Segoe UI", 11, "bold"),
                cursor="hand2",
                bd=0,
            )
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=BUTTON,
            fg=FG,
            activebackground=ACCENT_DARK,
            activeforeground=FG,
            relief="flat",
            padx=18,
            pady=8,
            font=("Segoe UI", 11),
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=ACCENT,
            bd=0,
        )

    def _labeled_text(
        self,
        parent: tk.Misc,
        title: str,
        name: str,
        *,
        readonly: bool = False,
        title_var: tk.StringVar | None = None,
    ) -> tk.Frame:
        wrap = tk.Frame(parent, bg=BG)
        wrap.grid_rowconfigure(1, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        label = tk.Label(wrap, text=title, bg=BG, fg=MUTED, font=("Segoe UI", 10))
        if title_var is not None:
            label.configure(textvariable=title_var)
        label.grid(row=0, column=0, sticky="w")
        box = tk.Frame(wrap, bg=ACCENT, padx=1, pady=1)
        box.grid(row=1, column=0, sticky="nsew")
        inner = tk.Frame(box, bg=ENTRY_BG)
        inner.pack(fill="both", expand=True)
        self._make_text(inner, name, readonly=readonly)
        return wrap

    def _make_text(self, parent: tk.Misc, name: str, *, readonly: bool) -> None:
        text = tk.Text(
            parent,
            height=1,
            wrap="word",
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=ACCENT,
            relief="flat",
            padx=10,
            pady=10,
            font=("Consolas", 11),
            highlightthickness=0,
            bd=0,
        )
        scroll = ModernScrollbar(parent, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text._readonly = readonly
        self._bind_clipboard(text, readonly=readonly)
        text.bind("<Enter>", lambda _e, widget=text: widget.bind_all("<MouseWheel>", lambda ev: self._wheel(ev, widget)))
        text.bind("<Leave>", lambda _e, widget=text: widget.unbind_all("<MouseWheel>"))
        setattr(self, f"{name}_text", text)

    def _wheel(self, event, widget: tk.Text) -> str:
        widget.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _bind_clipboard(self, widget: tk.Text, *, readonly: bool) -> None:
        menu = tk.Menu(widget, tearoff=0, bg=PANEL, fg=FG, activebackground=ACCENT, activeforeground=BG)
        if not readonly:
            menu.add_command(label="Cut", command=lambda: self._cut(widget))
        menu.add_command(label="Copy", command=lambda: self._copy(widget))
        if not readonly:
            menu.add_command(label="Paste", command=lambda: self._paste(widget))
        menu.add_separator()
        menu.add_command(label="Select all", command=lambda: self._select_all(widget))

        widget.bind("<Control-KeyPress>", lambda event: self._ctrl_key(event, widget, readonly))
        widget.bind("<Shift-Insert>", lambda _e: self._paste(widget) or "break")
        widget.bind("<Control-Insert>", lambda _e: self._copy(widget) or "break")
        widget.bind("<Shift-Delete>", lambda _e: (None if readonly else self._cut(widget)) or "break")
        widget.bind("<Button-3>", lambda event: self._show_menu(event, menu))
        if readonly:
            widget.bind("<Key>", lambda event: self._readonly_key(event))

    def _ctrl_key(self, event, widget: tk.Text, readonly: bool) -> str | None:
        # keycode keeps C/V/X/A on a Russian keyboard layout.
        if event.keycode == 67:
            self._copy(widget)
            return "break"
        if event.keycode == 86:
            if not readonly:
                self._paste(widget)
            return "break"
        if event.keycode == 88:
            if not readonly:
                self._cut(widget)
            return "break"
        if event.keycode == 65:
            self._select_all(widget)
            return "break"
        return None

    def _readonly_key(self, event) -> str | None:
        if event.state & 0x4:
            return None
        if event.keysym in {"Left", "Right", "Up", "Down", "Home", "End", "Next", "Prior", "Shift_L", "Shift_R"}:
            return None
        return "break"

    def _selected(self, widget: tk.Text) -> str | None:
        try:
            return widget.get("sel.first", "sel.last")
        except tk.TclError:
            return None

    def _copy(self, widget: tk.Text) -> None:
        text = self._selected(widget)
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()

    def _cut(self, widget: tk.Text) -> None:
        if getattr(widget, "_readonly", False):
            return
        text = self._selected(widget)
        if text is None:
            return
        self._copy(widget)
        widget.delete("sel.first", "sel.last")

    def _paste(self, widget: tk.Text) -> None:
        if getattr(widget, "_readonly", False):
            return
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return
        try:
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        widget.insert("insert", text)

    def _select_all(self, widget: tk.Text) -> None:
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set("insert", "1.0")
        widget.see("insert")

    def _show_menu(self, event, menu: tk.Menu) -> str:
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _draw_checker(self) -> None:
        canvas = self.checker
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        size = 5
        for y in range(0, height, size):
            for x in range(0, width, size):
                color = ACCENT if ((x // size) + (y // size)) % 2 == 0 else PANEL
                canvas.create_rectangle(x, y, x + size, y + size, fill=color, outline="")

    def _load_body(self) -> None:
        path = images_dir() / "wiki_sans_v2_body.png"
        if not path.exists():
            return
        try:
            from PIL import Image, ImageTk

            image = Image.open(path)
            target = 160
            scale = target / max(image.height, 1)
            size = (max(1, int(image.width * scale)), target)
            image = image.resize(size, Image.Resampling.NEAREST)
            photo = ImageTk.PhotoImage(image)
        except Exception:
            photo = tk.PhotoImage(file=str(path))
        self._photos.append(photo)
        self.body_label.configure(image=photo)

    def _set_readonly(self, widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        if widget is getattr(self, "output_text", None):
            self._tag_spelled(widget)

    def _tag_spelled(self, widget: tk.Text) -> None:
        widget.tag_configure("spelled", foreground=ACCENT, font=("Consolas", 11, "bold"))
        widget.tag_remove("spelled", "1.0", "end")
        content = widget.get("1.0", "end-1c")
        for match in re.finditer(r"  (?:[A-Za-z'] )+[A-Za-z']  ", content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            widget.tag_add("spelled", start, end)

    def _start_loading(self) -> None:
        threading.Thread(target=self._load_backend, daemon=True).start()

    def _load_backend(self) -> None:
        try:
            wordnet = nltk_setup.ensure_wordnet()
            ollama = ollama_setup.ensure_ollama()
            lexicon = load_or_build()
            memory = load_or_build_memory()
            letters = LetterBank(lexicon)
        except Exception as exc:
            self.root.after(0, lambda: self._ready(None, None, None, False, f"Load failed: {exc}"))
            return
        cfg = get_config()
        parts = [f"Lexicon: {len(lexicon.words)} words"]
        parts.append(f"Lines: {len(memory.lines)}")
        if not cfg.wordnet:
            parts.append("WordNet: off")
        else:
            parts.append("WordNet: yes" if wordnet else "WordNet: no")
        if not cfg.ollama:
            parts.append("Ollama: off")
        elif ollama:
            parts.append(f"Ollama: {ollama_setup.chosen_model()}")
        else:
            parts.append("Ollama: no")
        self.root.after(
            0, lambda: self._ready(lexicon, memory, letters, ollama, "  ·  ".join(parts))
        )

    def _ready(self, lexicon, memory, letters, ollama: bool, status: str) -> None:
        self.lexicon = lexicon
        self.memory = memory
        self.letters = letters
        self.use_ollama = ollama
        self.status.set(status)
        self.run_button.configure(state="normal" if lexicon else "disabled")

    def clear_input(self) -> None:
        self.input_text.delete("1.0", "end")
        self.input_text.focus_set()

    def interpret(self) -> None:
        if self.busy or self.lexicon is None:
            return
        source = self.input_text.get("1.0", "end").strip()
        if not source:
            self.status.set("Enter text to interpret.")
            return
        self.busy = True
        self.run_button.configure(state="disabled")
        self.clear_button.configure(state="disabled")
        self.status.set("Interpreting...")
        threading.Thread(target=self._interpret_worker, args=(source,), daemon=True).start()

    def _interpret_worker(self, source: str) -> None:
        def on_progress(message: str) -> None:
            self.root.after(0, lambda m=message: self.status.set(m))

        try:
            result = rewrite_text(
                source,
                self.lexicon,
                mode=self.mode.get(),
                memory=self.memory,
                letters=self.letters,
                use_ollama=self.use_ollama,
                on_progress=on_progress,
            )
        except Exception as exc:
            self.root.after(0, lambda: self._show_error(str(exc)))
            return
        self.root.after(0, lambda s=source, r=result: self._show_result(s, r))

    def _show_error(self, message: str) -> None:
        self.busy = False
        self.run_button.configure(state="normal")
        self.clear_button.configure(state="normal")
        self.status.set(f"Error: {message}")

    def _show_result(self, source: str, result) -> None:
        self._set_readonly(self.output_text, format_output(result.text))
        self._set_readonly(self.sources_text, format_sources(result))
        self._remember(source, result)
        self.busy = False
        self.run_button.configure(state="normal")
        self.clear_button.configure(state="normal")
        extra = ""
        if result.engine == "ollama":
            extra = "  ·  via Ollama"
        elif result.engine == "mixed":
            extra = "  ·  local + Ollama"
        elif result.engine == "sentence":
            extra = "  ·  sentence mode"
        elif result.engine == "letter":
            extra = "  ·  letter mode"
        self.status.set(f"Done.{extra}")


def run_gui() -> None:
    root = tk.Tk()
    WikiSansApp(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
