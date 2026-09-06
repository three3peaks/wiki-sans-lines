#!/usr/bin/env python3
"""Interactive Wiki!Sans console."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr is not None and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from wiki_sans.config import get_config
from wiki_sans.lexicon import load_or_build
from wiki_sans.memory import LetterBank, load_or_build_memory
from wiki_sans import nltk_setup, ollama_setup
from wiki_sans.rewrite import format_output, rewrite_text


def print_result(result, *, verbose: bool) -> None:
    print(format_output(result.text))
    if result.engine == "ollama":
        print("  [Ollama]")
    elif result.engine == "mixed":
        print("  [local + Ollama]")
    if result.missing:
        missing = ", ".join(dict.fromkeys(result.missing))
        print(f"  [no close replacement: {missing}]")
    if verbose:
        for change in result.changes:
            if change.original.casefold() == change.written.casefold() and change.in_corpus:
                origin = change.source or "?"
                print(f"  {change.written} <- {origin}")
            else:
                origin = change.source or "-"
                print(
                    f"  {change.original} -> {change.written} "
                    f"({change.via}, {origin})"
                )


def read_multiline() -> str:
    print("Paste text. Empty line ends input.")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def run_prompt(
    lexicon,
    verbose: bool,
    *,
    use_ollama: bool,
    mode: str,
    memory,
    letters,
) -> None:
    print("Wiki!Sans. Type a line, :text for a long passage, :file path, quit to exit.")
    if use_ollama:
        print("The first Ollama call can take up to a minute.")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line or line.casefold() in {"quit", "exit", "q"}:
            return

        if line.casefold() == ":text":
            text = read_multiline()
            if not text:
                continue
        elif line.casefold().startswith(":file"):
            path = line[5:].strip().strip('"')
            if not path:
                print("Give a path: :file story.txt")
                continue
            try:
                text = Path(path).read_text(encoding="utf-8")
            except OSError as exc:
                print(f"Could not read the file: {exc}")
                continue
        else:
            text = line

        print_result(
            rewrite_text(
                text,
                lexicon,
                mode=mode,
                memory=memory,
                letters=letters,
                use_ollama=use_ollama,
            ),
            verbose=verbose,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rewrite English as Wiki!Sans using words from other Undertale textboxes."
    )
    parser.add_argument("text", nargs="*", help="A phrase or short English text")
    parser.add_argument(
        "-f",
        "--file",
        help="Read the source text from a file",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write the result to a file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show which character each word came from",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Skip Ollama and use local synonyms only",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Open the text console instead of the window",
    )
    parser.add_argument(
        "--mode",
        choices=("word", "sentence", "letter"),
        default=None,
        help="Rewrite mode: word, sentence, or letter (default from config.json)",
    )
    args = parser.parse_args()

    batch = bool(args.file or args.text)
    stdin_tty = sys.stdin is not None and sys.stdin.isatty()
    if not args.cli and not batch and (getattr(sys, "frozen", False) or stdin_tty):
        from wiki_sans.gui import run_gui

        run_gui()
        return

    cfg = get_config()
    mode = args.mode or cfg.default_mode
    wordnet = nltk_setup.ensure_wordnet()
    ollama = False if args.local else ollama_setup.ensure_ollama()
    lexicon = load_or_build()
    memory = load_or_build_memory()
    letters = LetterBank(lexicon)
    print(f"Lexicon: {len(lexicon.words)} words from Undertale textboxes.")
    print(f"Lines: {len(memory.lines)}.")
    if not cfg.wordnet:
        print("WordNet: off (config.json).")
    elif wordnet:
        print("WordNet: connected.")
    else:
        print("WordNet: unavailable, using local synonyms.")
    if nltk_setup.last_log_path is not None:
        print(f"WordNet log: {nltk_setup.last_log_path}")
    if args.local:
        print("Ollama: off (--local).")
    elif not cfg.ollama:
        print("Ollama: off (config.json).")
    elif ollama:
        print(f"Ollama: {ollama_setup.chosen_model()}.")
    else:
        print("Ollama: unavailable, working without a model.")
    if ollama_setup.last_log_path is not None:
        print(f"Ollama log: {ollama_setup.last_log_path}")

    source = None
    if args.file:
        source = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        source = " ".join(args.text)
    elif not sys.stdin.isatty():
        source = sys.stdin.read()

    if source is None:
        run_prompt(
            lexicon,
            verbose=args.verbose,
            use_ollama=ollama,
            mode=mode,
            memory=memory,
            letters=letters,
        )
        return

    result = rewrite_text(
        source,
        lexicon,
        mode=mode,
        memory=memory,
        letters=letters,
        use_ollama=ollama,
    )
    print_result(result, verbose=args.verbose)
    if args.output:
        Path(args.output).write_text(format_output(result.text) + "\n", encoding="utf-8")
        print(f"Wrote: {args.output}")


def _show_startup_error(exc: BaseException) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "WIKI!Sans lines",
            f"The program failed to start:\n\n{type(exc).__name__}: {exc}",
        )
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _show_startup_error(exc)
        raise
