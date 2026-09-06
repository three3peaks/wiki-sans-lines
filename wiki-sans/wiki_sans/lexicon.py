"""Word bank built from Undertale textboxes."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from wiki_sans.paths import lexicon_path, textboxes_path

WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

DEFAULT_TEXTBOXES = textboxes_path()
DEFAULT_LEXICON = lexicon_path()
DATA_DIR = DEFAULT_LEXICON.parent


@dataclass
class WordEntry:
    forms: Counter[str] = field(default_factory=Counter)
    sources: Counter[str] = field(default_factory=Counter)

    @property
    def preferred_form(self) -> str:
        return self.forms.most_common(1)[0][0]

    @property
    def preferred_source(self) -> str:
        return self.sources.most_common(1)[0][0]


class Lexicon:
    def __init__(self, words: dict[str, WordEntry]) -> None:
        self.words = words

    def __contains__(self, word: str) -> bool:
        return word.casefold() in self.words

    def get(self, word: str) -> WordEntry | None:
        return self.words.get(word.casefold())

    def form_in_corpus(self, word: str) -> str | None:
        entry = self.get(word)
        if entry is None:
            return None
        folded = word.casefold()
        for form, _count in entry.forms.most_common():
            if form.casefold() == folded:
                return form
        return entry.preferred_form


def build_lexicon(textboxes_path: Path = DEFAULT_TEXTBOXES) -> Lexicon:
    raw = json.loads(textboxes_path.read_text(encoding="utf-8"))
    words: dict[str, WordEntry] = {}
    for character, boxes in raw.items():
        for box in boxes:
            for match in WORD_RE.finditer(box):
                form = match.group(0)
                key = form.casefold()
                entry = words.setdefault(key, WordEntry())
                entry.forms[form] += 1
                entry.sources[character] += 1
    return Lexicon(words)


def save_lexicon(lexicon: Lexicon, path: Path = DEFAULT_LEXICON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        key: {
            "forms": dict(entry.forms),
            "sources": dict(entry.sources),
        }
        for key, entry in sorted(lexicon.words.items())
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_lexicon(path: Path = DEFAULT_LEXICON) -> Lexicon:
    raw = json.loads(path.read_text(encoding="utf-8"))
    words = {
        key: WordEntry(forms=Counter(info["forms"]), sources=Counter(info["sources"]))
        for key, info in raw.items()
    }
    return Lexicon(words)


def load_or_build(
    lexicon_path: Path = DEFAULT_LEXICON,
    textboxes_path: Path = DEFAULT_TEXTBOXES,
) -> Lexicon:
    if lexicon_path.exists():
        return load_lexicon(lexicon_path)
    lexicon = build_lexicon(textboxes_path)
    save_lexicon(lexicon, lexicon_path)
    return lexicon
