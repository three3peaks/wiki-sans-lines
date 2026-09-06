"""Sentence memory and letter bank built from Undertale textboxes."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass

from wiki_sans.lexicon import Lexicon, WORD_RE
from wiki_sans.paths import sentences_path, textboxes_path
from wiki_sans.synonyms import related_words
from wiki_sans.text_split import split_sentences

STOP = {
    "a",
    "an",
    "the",
    "to",
    "of",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "for",
    "from",
    "with",
    "by",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "am",
    "do",
    "does",
    "did",
    "have",
    "has",
    "had",
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "me",
    "my",
    "your",
    "this",
    "that",
    "these",
    "those",
}

_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class MemoryLine:
    text: str
    character: str
    words: frozenset[str]


class Memory:
    def __init__(self, lines: list[MemoryLine]) -> None:
        self.lines = lines
        self.index: dict[str, list[int]] = defaultdict(list)
        for index, line in enumerate(lines):
            for word in line.words:
                self.index[word].append(index)

    def __len__(self) -> int:
        return len(self.lines)


def load_or_build_memory() -> Memory:
    path = sentences_path()
    if path.exists():
        return load_memory(path)
    memory = build_memory()
    save_memory(memory, path)
    return memory


def load_memory(path=None) -> Memory:
    raw = json.loads((path or sentences_path()).read_text(encoding="utf-8"))
    lines = [
        MemoryLine(
            text=item["text"],
            character=item["character"],
            words=frozenset(item["words"]),
        )
        for item in raw
        if item.get("text") and item.get("words") is not None
    ]
    return Memory(lines)


def save_memory(memory: Memory, path=None) -> None:
    dest = path or sentences_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "text": line.text,
            "character": line.character,
            "words": sorted(line.words),
        }
        for line in memory.lines
    ]
    dest.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def build_memory(textboxes=None) -> Memory:
    raw = json.loads((textboxes or textboxes_path()).read_text(encoding="utf-8"))
    seen: set[str] = set()
    lines: list[MemoryLine] = []
    for character, boxes in raw.items():
        for box in boxes:
            for piece in _memory_pieces(box):
                key = piece.casefold()
                if key in seen:
                    continue
                words = content_words(piece)
                if not words:
                    continue
                seen.add(key)
                lines.append(MemoryLine(text=piece, character=character, words=frozenset(words)))
    return Memory(lines)


def _memory_pieces(box: str) -> list[str]:
    cleaned = _SPACE.sub(" ", box.replace("\n", " ")).strip()
    if not cleaned:
        return []
    pieces = [cleaned]
    for sentence in split_sentences(cleaned):
        if sentence and sentence not in pieces:
            pieces.append(sentence)
    return pieces


def content_words(text: str) -> list[str]:
    words: list[str] = []
    for match in WORD_RE.finditer(text.casefold()):
        word = match.group(0)
        if word in STOP or len(word) == 1:
            continue
        words.append(word)
    return words


def expand_words(words: list[str]) -> set[str]:
    expanded = set(words)
    for word in words:
        for related, _via in related_words(word, "NN")[:8]:
            expanded.add(related)
    return expanded


def score_line(query: list[str], expanded: set[str], line: MemoryLine) -> float:
    if not query:
        return 0.0
    query_set = set(query)
    exact_hits = query_set & line.words
    exact = len(exact_hits) / len(query_set)
    near = len(expanded & line.words) / len(query_set)
    union = expanded | line.words
    jaccard = len(expanded & line.words) / len(union) if union else 0.0
    head = 2.2 if query and query[0] in line.words else 0.0
    return exact * 3.0 + near * 1.0 + jaccard + len(exact_hits) * 0.8 + head


def best_lines(text: str, memory: Memory, *, limit: int = 12, used: set[str] | None = None) -> list[tuple[float, MemoryLine]]:
    query = content_words(text)
    expanded = expand_words(query)
    blocked = used or set()
    candidate_ids: set[int] = set()
    for word in expanded:
        candidate_ids.update(memory.index.get(word, ()))
    ranked: list[tuple[float, MemoryLine]] = []
    for index in candidate_ids:
        line = memory.lines[index]
        if line.text.casefold() in blocked:
            continue
        score = score_line(query, expanded, line)
        if score <= 0:
            continue
        ranked.append((score, line))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:limit]


def pick_line(
    text: str,
    memory: Memory,
    *,
    used: set[str] | None = None,
) -> MemoryLine | None:
    ranked = best_lines(text, memory, used=used)
    if ranked:
        return ranked[0][1]
    return _fallback_line(text, memory, used or set())


def _fallback_line(text: str, memory: Memory, used: set[str]) -> MemoryLine | None:
    want_question = "?" in text
    for line in memory.lines:
        if line.text.casefold() in used:
            continue
        if want_question and "?" in line.text:
            return line
    for line in memory.lines:
        if line.text.casefold() not in used:
            return line
    return None


def display_line(text: str) -> str:
    cleaned = _SPACE.sub(" ", text.replace("\n", " ")).strip()
    if cleaned.startswith("*"):
        cleaned = cleaned[1:].strip()
    return cleaned


class LetterBank:
    def __init__(self, lexicon: Lexicon) -> None:
        buckets: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for entry in lexicon.words.values():
            form = entry.preferred_form
            source = entry.preferred_source
            seen: set[str] = set()
            for char in form:
                key = char.casefold()
                if not key.isalpha() or key in seen:
                    continue
                seen.add(key)
                buckets[key].append((form, source))
        self._letters = {key: values for key, values in buckets.items() if values}

    def spell(self, word: str) -> tuple[str, list[tuple[str, str, str]]]:
        picks: list[tuple[str, str, str]] = []
        used: set[str] = set()
        for char in word:
            if not char.isalpha():
                picks.append((char, "", ""))
                continue
            key = char.casefold()
            donor, source = self._pick(key, used)
            if donor:
                used.add(donor.casefold())
            picks.append((char, donor, source))
        glyphs = [item[0] for item in picks]
        written = "  " + " ".join(glyphs) + "  "
        return written, picks

    def _pick(self, letter: str, used: set[str]) -> tuple[str, str]:
        options = self._letters.get(letter, [])
        if not options:
            return "", ""
        unused = [item for item in options if item[0].casefold() not in used]
        pool = unused or options
        usable = [
            item
            for item in pool
            if sum(1 for ch in item[0] if ch.isalpha()) >= 3
        ] or [item for item in pool if len(item[0]) > 1] or pool
        for form, source in usable:
            if form.casefold().startswith(letter):
                return form, source
        return min(usable, key=lambda item: len(item[0]))
