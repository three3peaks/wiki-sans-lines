#!/usr/bin/env python3
"""Build Undertale {character: [textboxes]} dictionaries from hushbugger's dump."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "hushbugger.github.io" / "dialogue" / "textdump.js"


def load_textdump(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("var d = "):
        raise ValueError(f"Unexpected textdump format: {path}")
    payload = text[len("var d = ") :].rstrip()
    if payload.endswith(";"):
        payload = payload[:-1]
    data = json.loads(payload)
    return {name: list(boxes) for name, boxes in data.items()}


def plain_textbox(text: str) -> str:
    """Strip Undertale control codes, matching dialogue.js rendering rules."""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if nxt in "WXYRLBGOPC":
                i += 2
            elif nxt in "EFMT":
                i += 3
            elif nxt == "z":
                out.append("∞")
                i += 6
            else:
                i += 1
            continue
        if ch == "/":
            i += 2 if i + 1 < len(text) and text[i + 1] == "*" else 1
            continue
        if ch in "&#":
            out.append("\n")
            i += 1
            continue
        if ch == "^" and i + 1 < len(text) and text[i + 1].isdigit():
            i += 2
            continue
        if ch == "%":
            i += 1
            continue
        out.append(ch)
        i += 1

    lines = [" ".join(line.split()) for line in "".join(out).splitlines()]
    return "\n".join(line for line in lines if line)


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    by_character = load_textdump(SOURCE)
    plain = {
        name: [plain_textbox(box) for box in boxes]
        for name, boxes in by_character.items()
    }
    plain = {
        name: [box for box in boxes if box]
        for name, boxes in plain.items()
    }

    write_json(ROOT / "undertale.json", by_character)
    write_json(ROOT / "undertale.plain.json", plain)
    write_json(
        ROOT / "undertale.characters.json",
        {
            name: {
                "textboxes": len(boxes),
                "plain_textboxes": len(plain[name]),
            }
            for name, boxes in sorted(by_character.items())
        },
    )


if __name__ == "__main__":
    main()
