"""Split a full English text into paragraphs and sentences."""

from __future__ import annotations

import re

ABBREVIATIONS = {
    "dr",
    "e.g",
    "etc",
    "i.e",
    "jr",
    "mr",
    "mrs",
    "ms",
    "prof",
    "sr",
    "st",
    "vs",
}


def split_paragraphs(text: str) -> list[str]:
    chunks = re.split(r"\r?\n\s*\r?\n", text.strip())
    return [re.sub(r"[ \t]*\r?\n[ \t]*", " ", chunk).strip() for chunk in chunks if chunk.strip()]


def split_sentences(paragraph: str) -> list[str]:
    text = re.sub(r"\s+", " ", paragraph.strip())
    if not text:
        return []

    sentences: list[str] = []
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in ".!?":
            if ch == "." and i + 1 < len(text) and text[i + 1] == ".":
                i += 1
                continue
            word = _word_before(text, start, i)
            if ch == "." and _is_abbreviation(word):
                i += 1
                continue
            nxt = text[i + 1 :].lstrip()
            if not nxt or nxt[0].isupper() or nxt[0] in "\"'":
                piece = text[start : i + 1].strip()
                if piece:
                    sentences.append(piece)
                start = i + 1
        i += 1

    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def split_text(text: str) -> list[list[str]]:
    return [split_sentences(paragraph) for paragraph in split_paragraphs(text)]


def _word_before(text: str, start: int, end: int) -> str:
    chunk = text[start:end]
    parts = chunk.split()
    return parts[-1] if parts else ""


def _is_abbreviation(word: str) -> bool:
    cleaned = word.strip("\"'()[]").casefold()
    if cleaned in ABBREVIATIONS:
        return True
    if len(cleaned) == 1 and cleaned.isalpha():
        return True
    return bool(re.fullmatch(r"[a-z]\.([a-z]\.)+", cleaned))
