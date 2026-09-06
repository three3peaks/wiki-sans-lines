"""Rewrite an English line using only words attested in the textbox lexicon."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

ProgressFn = Callable[[str], None]

from wiki_sans.lexicon import Lexicon
from wiki_sans.memory import LetterBank, Memory, display_line, pick_line
from wiki_sans.nltk_setup import tagger_ready, wordnet_ready
from wiki_sans.ollama_setup import generate, ollama_ready
from wiki_sans.session_log import write_session
from wiki_sans.synonyms import closest_in_lexicon
from wiki_sans.text_split import split_text

TOKEN_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|[0-9]+|[^\s\w]")

KEEP_WORDS = {
    "a",
    "an",
    "the",
    "this",
    "that",
    "these",
    "those",
    "i",
    "me",
    "my",
    "mine",
    "you",
    "your",
    "yours",
    "he",
    "him",
    "his",
    "she",
    "her",
    "hers",
    "it",
    "its",
    "we",
    "us",
    "our",
    "ours",
    "they",
    "them",
    "their",
    "theirs",
    "who",
    "whom",
    "whose",
    "what",
    "which",
    "and",
    "or",
    "but",
    "if",
    "than",
    "as",
    "of",
    "to",
    "in",
    "on",
    "at",
    "by",
    "for",
    "from",
    "with",
    "about",
    "into",
    "onto",
    "over",
    "under",
    "after",
    "before",
    "because",
    "while",
    "though",
    "not",
    "no",
    "nor",
    "so",
    "too",
    "very",
    "just",
    "only",
    "also",
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "do",
    "does",
    "did",
    "have",
    "has",
    "had",
    "can",
    "could",
    "may",
    "might",
    "must",
    "shall",
    "should",
    "will",
    "would",
    "there",
    "here",
}

KEEP_TAGS = {
    "CC",
    "DT",
    "EX",
    "IN",
    "MD",
    "PDT",
    "POS",
    "PRP",
    "PRP$",
    "TO",
    "WDT",
    "WP",
    "WP$",
    "WRB",
}

VOWEL_SOUND = re.compile(r"^[aeiou]", re.IGNORECASE)

WORD_TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
CLITICS = {"n't", "'s", "'re", "'ve", "'ll", "'d", "'m"}
NLTK_NEG_HEADS = {
    "ca": "can't",
    "wo": "won't",
    "sha": "shan't",
    "ai": "ain't",
}
CONTRACTION_EXPAND = {
    "can't": "cannot",
    "cannot": "cannot",
    "won't": "will not",
    "shan't": "shall not",
    "ain't": "is not",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "haven't": "have not",
    "hasn't": "has not",
    "hadn't": "had not",
    "wouldn't": "would not",
    "couldn't": "could not",
    "shouldn't": "should not",
    "mustn't": "must not",
    "needn't": "need not",
    "i'm": "I am",
    "you're": "you are",
    "we're": "we are",
    "they're": "they are",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "i've": "I have",
    "you've": "you have",
    "we've": "we have",
    "they've": "they have",
    "i'd": "I would",
    "you'd": "you would",
    "he'd": "he would",
    "she'd": "she would",
    "we'd": "we would",
    "they'd": "they would",
    "i'll": "I will",
    "you'll": "you will",
    "he'll": "he will",
    "she'll": "she will",
    "we'll": "we will",
    "they'll": "they will",
    "that's": "that is",
    "there's": "there is",
    "here's": "here is",
    "what's": "what is",
    "who's": "who is",
    "let's": "let us",
}


@dataclass
class TokenChange:
    original: str
    written: str
    in_corpus: bool
    source: str | None
    via: str
    letters: list[tuple[str, str, str]] | None = None


@dataclass
class RewriteResult:
    text: str
    changes: list[TokenChange]
    missing: list[str]
    engine: str = "local"


def rewrite_text(
    text: str,
    lexicon: Lexicon,
    *,
    mode: str = "word",
    memory: Memory | None = None,
    letters: LetterBank | None = None,
    use_ollama: bool | None = None,
    on_progress: ProgressFn | None = None,
) -> RewriteResult:
    def note(message: str) -> None:
        if on_progress:
            on_progress(message)
        else:
            print(message)

    paragraphs = split_text(text)
    if not paragraphs:
        return RewriteResult(text="", changes=[], missing=[], engine="local")
    if mode == "sentence":
        return _rewrite_sentences(paragraphs, memory, on_progress)
    if len(paragraphs) == 1 and len(paragraphs[0]) == 1:
        return rewrite_line(
            paragraphs[0][0],
            lexicon,
            mode=mode,
            letters=letters,
            use_ollama=use_ollama,
            on_progress=on_progress,
        )

    written_paragraphs: list[str] = []
    changes: list[TokenChange] = []
    missing: list[str] = []
    engines: set[str] = set()
    total = sum(len(sentences) for sentences in paragraphs)
    index = 0
    for sentences in paragraphs:
        pieces: list[str] = []
        for sentence in sentences:
            index += 1
            if total > 1:
                note(f"Sentence {index}/{total}...")
            result = rewrite_line(
                sentence,
                lexicon,
                mode=mode,
                letters=letters,
                use_ollama=use_ollama,
                on_progress=on_progress,
            )
            if result.text.strip():
                pieces.append(result.text)
            changes.extend(result.changes)
            missing.extend(result.missing)
            engines.add(result.engine)
        if pieces:
            written_paragraphs.append(" ".join(pieces))

    if not engines or engines == {"local"}:
        engine = "local"
    elif engines == {"ollama"}:
        engine = "ollama"
    elif engines == {"letter"}:
        engine = "letter"
    elif engines == {"sentence"}:
        engine = "sentence"
    else:
        engine = "mixed"
    return RewriteResult(
        text="\n\n".join(written_paragraphs),
        changes=changes,
        missing=missing,
        engine=engine,
    )


def _rewrite_sentences(
    paragraphs: list[list[str]],
    memory: Memory | None,
    on_progress: ProgressFn | None,
) -> RewriteResult:
    def note(message: str) -> None:
        if on_progress:
            on_progress(message)
        else:
            print(message)

    if memory is None or not memory.lines:
        return RewriteResult(text="", changes=[], missing=[], engine="sentence")

    written_paragraphs: list[str] = []
    changes: list[TokenChange] = []
    used: set[str] = set()
    total = sum(len(sentences) for sentences in paragraphs)
    index = 0
    for sentences in paragraphs:
        pieces: list[str] = []
        for sentence in sentences:
            index += 1
            if total > 1:
                note(f"Sentence {index}/{total}...")
            line = pick_line(sentence, memory, used=used)
            if line is None:
                continue
            used.add(line.text.casefold())
            written = display_line(line.text)
            pieces.append(written)
            changes.append(
                TokenChange(sentence, written, True, line.character, "sentence")
            )
        if pieces:
            written_paragraphs.append(" ".join(pieces))
    return RewriteResult(
        text="\n\n".join(written_paragraphs),
        changes=changes,
        missing=[],
        engine="sentence",
    )


def rewrite_line(
    text: str,
    lexicon: Lexicon,
    *,
    mode: str = "word",
    letters: LetterBank | None = None,
    use_ollama: bool | None = None,
    on_progress: ProgressFn | None = None,
) -> RewriteResult:
    if use_ollama is None:
        use_ollama = ollama_ready()
    local = _assemble(text, lexicon, engine="local", mode=mode, letters=letters)
    if mode != "word" or not use_ollama or not local.missing:
        return local
    message = "Ollama: writing the line..."
    if on_progress:
        on_progress(message)
    else:
        print(message)
    try:
        generated = _rewrite_with_ollama(text, lexicon, dropped=local.missing)
    except Exception as exc:
        write_session(
            "ollama.log",
            [
                "generate: failed, falling back to local rewrite",
                f"exception: {type(exc).__name__}: {exc}",
            ],
        )
        return local
    if _kept_words(generated) >= _kept_words(local):
        return generated
    return local


def _assemble(
    text: str,
    lexicon: Lexicon,
    *,
    engine: str,
    mode: str = "word",
    letters: LetterBank | None = None,
    punct_from: str | None = None,
    dropped: list[str] | None = None,
) -> RewriteResult:
    text = _normalize_apostrophes(text.strip())
    tokens = _merge_contractions(_tokenize_and_tag(text))
    resolved: list[tuple[str, str, TokenChange | None]] = []
    missing: list[str] = []

    for raw, tag in tokens:
        if not WORD_TOKEN.fullmatch(raw):
            resolved.append((raw, "punct", None))
            continue
        folded = raw.casefold()
        keep = tag in KEEP_TAGS or folded in KEEP_WORDS
        if mode == "letter" and letters is not None and lexicon.get(raw) is None and not keep:
            expanded = _expand_contraction(raw, lexicon)
            if expanded is not None:
                form, via, source = expanded
            else:
                spelled, picks = letters.spell(raw)
                change = TokenChange(raw, spelled, False, None, "letters", letters=picks)
                resolved.append((spelled, "spelled", change))
                continue
        else:
            form, via, source = _resolve_word(raw, tag, lexicon, keep=keep)
        if engine == "ollama" and via == "corpus":
            via = "ollama"
        if via == "original":
            missing.append(raw)
            change = TokenChange(raw, "", False, None, "dropped")
            resolved.append((raw, "dropped", change))
            continue
        display = _apply_case(raw, form)
        in_corpus = via in {
            "corpus",
            "ollama",
            "lemma",
            "synonym",
            "similar",
            "near",
            "hypernym",
            "expanded",
        }
        change = TokenChange(raw, display, in_corpus, source, via)
        resolved.append((display, "word", change))

    written = [item for item, kind, _change in resolved if kind != "dropped" and item]
    engine_name = "letter" if mode == "letter" else engine
    changes = [change for _item, _kind, change in resolved if change is not None]
    written = _fix_articles(written)
    protected: dict[str, str] = {}
    safe_written: list[str] = []
    for index, item in enumerate(written):
        if item.startswith("  ") and item.endswith("  "):
            key = f"__SPELL{index}__"
            protected[key] = item
            safe_written.append(key)
        else:
            safe_written.append(item)
    sentence = _cleanup_sentence(_capitalize_sentence(_join_tokens(safe_written)))
    source = punct_from or text
    sentence = _reattach_punctuation(source, sentence, dropped if dropped is not None else missing)
    sentence = _restore_end_punct(source, sentence)
    for key, value in protected.items():
        sentence = sentence.replace(" " + key, value)
        sentence = sentence.replace(key, value)
        sentence = sentence.replace(key.casefold(), value)
    return RewriteResult(text=sentence, changes=changes, missing=missing, engine=engine_name)


def _kept_words(result: RewriteResult) -> int:
    return sum(
        1
        for change in result.changes
        if change.written and change.via not in {"dropped", "dropped_with"}
    )


def _rewrite_locally(text: str, lexicon: Lexicon) -> RewriteResult:
    return _assemble(text, lexicon, engine="local")


SYSTEM_PROMPT = """You rewrite short English sentences using ONLY words from the allowed list.
Keep the original meaning. Do not drop verbs, articles, or helper words if they are allowed.
Use correct English grammar, spelling, and punctuation.
Reply with one sentence only. No quotes, no markdown, no explanation."""


def _rewrite_with_ollama(
    text: str, lexicon: Lexicon, *, dropped: list[str] | None = None
) -> RewriteResult:
    allowed = " ".join(sorted(lexicon.words))
    raw_reply = generate(
        (
            f"Allowed words:\n{allowed}\n\n"
            f"Rewrite this sentence with allowed words only:\n{text.strip()}"
        ),
        SYSTEM_PROMPT,
    )
    cleaned = _clean_model_text(raw_reply)
    if not cleaned:
        raise ValueError("Ollama reply had no usable sentence")
    return _assemble(
        cleaned,
        lexicon,
        engine="ollama",
        punct_from=text,
        dropped=dropped,
    )


def _clean_model_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    text = text.strip().strip('"').strip("'")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("*"):
            line = line[1:].strip()
        if line:
            return line
    return text


def _normalize_apostrophes(text: str) -> str:
    return (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u02bc", "'")
        .replace("`", "'")
    )


def _tokenize_and_tag(text: str) -> list[tuple[str, str]]:
    text = _normalize_apostrophes(text)
    if tagger_ready():
        try:
            from nltk import pos_tag, word_tokenize

            return _merge_contractions(pos_tag(word_tokenize(text)))
        except (LookupError, OSError):
            pass
    return _merge_contractions([(token, _guess_tag(token)) for token in TOKEN_RE.findall(text)])


def _merge_contractions(tokens: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    for raw, tag in tokens:
        clitic = raw.casefold()
        if clitic in CLITICS and merged:
            prev, prev_tag = merged.pop()
            merged.append((_attach_clitic(prev, raw), prev_tag))
            continue
        merged.append((raw, tag))
    return merged


def _attach_clitic(head: str, clitic: str) -> str:
    if clitic.casefold() != "n't":
        return head + clitic
    special = NLTK_NEG_HEADS.get(head.casefold())
    if special:
        return special[:1].upper() + special[1:] if head[:1].isupper() else special
    return head + "n't"


def _guess_tag(token: str) -> str:
    folded = token.casefold()
    if folded in KEEP_WORDS:
        return "DT"
    if folded.endswith("ly"):
        return "RB"
    if folded.endswith("ing"):
        return "VBG"
    if folded.endswith("ed"):
        return "VBD"
    if folded.endswith("s") and not folded.endswith("ss"):
        return "NNS"
    if token[:1].isupper() and folded != "i":
        return "NNP"
    return "NN"


def _resolve_word(
    word: str, tag: str, lexicon: Lexicon, *, keep: bool
) -> tuple[str, str, str | None]:
    entry = lexicon.get(word)
    if entry is not None:
        return word, "corpus", entry.preferred_source

    expanded = _expand_contraction(word, lexicon)
    if expanded is not None:
        return expanded

    if keep:
        return word, "kept", None

    closest = closest_in_lexicon(word, tag, lexicon)
    if closest is not None:
        candidate, via = closest
        found = lexicon.get(candidate)
        if found is not None:
            chosen = lexicon.form_in_corpus(candidate) or found.preferred_form
            return chosen, via, found.preferred_source

    for stem in _stems(word):
        found = lexicon.get(stem)
        if found is not None:
            chosen = lexicon.form_in_corpus(stem) or stem
            return chosen, "lemma", found.preferred_source

    return word, "original", None


def _expand_contraction(word: str, lexicon: Lexicon) -> tuple[str, str, str | None] | None:
    phrase = CONTRACTION_EXPAND.get(word.casefold())
    if not phrase:
        return None
    parts = phrase.split()
    if all(lexicon.get(part) or part.casefold() in KEEP_WORDS for part in parts):
        source = None
        for part in parts:
            found = lexicon.get(part)
            if found is not None:
                source = found.preferred_source
                break
        return phrase, "expanded", source
    return None


def _cleanup_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"[,;:]+([.!?])", r"\1", text)
    text = re.sub(r"[,;:]{2,}", ",", text)
    text = re.sub(r"^[,;:\s]+", "", text)
    text = re.sub(r"[,;:\s]+$", "", text)
    text = re.sub(r"\s+(and|but|or)(\s+(and|but|or))+", r" \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    text = _capitalize_after_breaks(text)
    return text


def _capitalize_after_breaks(text: str) -> str:
    chars = list(text)
    cap_next = True
    for index, ch in enumerate(chars):
        if cap_next and ch.isalpha():
            if ch.casefold() == "i" and (
                index + 1 == len(chars) or not chars[index + 1].isalpha()
            ):
                chars[index] = "I"
            else:
                chars[index] = ch.upper()
            cap_next = False
        elif ch in ".!?":
            cap_next = True
    return "".join(chars)


def _punct_count(text: str) -> int:
    return sum(1 for ch in text if ch in ",.;:!?")


def _word_punct_pairs(text: str) -> list[tuple[str, str]]:
    tokens = TOKEN_RE.findall(text)
    pairs: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if WORD_TOKEN.fullmatch(token):
            punct = ""
            index += 1
            while index < len(tokens) and not WORD_TOKEN.fullmatch(tokens[index]):
                punct += tokens[index]
                index += 1
            pairs.append((token, punct))
            continue
        pairs.append(("", token))
        index += 1
    return pairs


def _merge_punct(left: str, right: str) -> str:
    combined = left + right
    ends = [ch for ch in combined if ch in ".!?"]
    if ends:
        return ends[-1]
    marks = [ch for ch in combined if ch in ",;:"]
    return marks[-1] if marks else combined


def _reattach_punctuation(original: str, written: str, dropped: list[str]) -> str:
    if not written or _punct_count(written) >= _punct_count(original):
        return written
    pending = [item.casefold() for item in dropped]
    kept: list[tuple[str, str]] = []
    for word, punct in _word_punct_pairs(original):
        if word and pending and word.casefold() == pending[0]:
            pending.pop(0)
            if kept:
                prev_word, prev_punct = kept[-1]
                kept[-1] = (prev_word, _merge_punct(prev_punct, punct))
            continue
        kept.append((word, punct))

    new_words = [token for token in TOKEN_RE.findall(written) if WORD_TOKEN.fullmatch(token)]
    if not new_words:
        return written

    pieces: list[str] = []
    index = 0
    for word, punct in kept:
        if not word:
            if punct:
                pieces.append(punct)
            continue
        if index < len(new_words):
            pieces.append(new_words[index] + punct)
            index += 1
    pieces.extend(new_words[index:])
    return _cleanup_sentence(_join_tokens(pieces))


def _restore_end_punct(original: str, sentence: str) -> str:
    if not sentence or sentence[-1] in ".!?":
        return sentence
    match = re.search(r"[.!?]+$", original.strip())
    if match:
        return sentence + match.group(0)
    return sentence


def _stems(word: str) -> list[str]:
    folded = word.casefold()
    stems: list[str] = []
    for suffix in ("'s", "s", "es", "ed", "ing", "ly", "er", "est"):
        if folded.endswith(suffix) and len(folded) > len(suffix) + 2:
            stems.append(folded[: -len(suffix)])
    if wordnet_ready():
        try:
            from nltk.corpus import wordnet as wn

            morphed = wn.morphy(folded)
            if morphed:
                stems.append(morphed)
        except LookupError:
            pass
    return stems


def _apply_case(original: str, replacement: str) -> str:
    if original.casefold() == "i" or replacement.casefold() == "i":
        return "I"
    if " " in replacement:
        parts = replacement.split()
        return " ".join(
            _apply_case(original if index == 0 else "word", part)
            for index, part in enumerate(parts)
        )
    base = replacement
    if base.isupper() and len(base) > 1 and not original.isupper():
        base = base.casefold()
    if original.isupper() and len(original) > 1:
        return base.upper()
    if original[:1].isupper():
        return base[:1].upper() + base[1:]
    if not base:
        return base
    return base[:1].lower() + base[1:]


def _fix_articles(tokens: list[str]) -> list[str]:
    fixed = list(tokens)
    for i, token in enumerate(fixed[:-1]):
        if token.casefold() not in {"a", "an"}:
            continue
        nxt = next((item for item in fixed[i + 1 :] if re.search(r"[A-Za-z]", item)), "")
        if not nxt:
            continue
        article = "an" if VOWEL_SOUND.match(nxt) else "a"
        fixed[i] = article.capitalize() if token[:1].isupper() else article
    return fixed


def _join_tokens(tokens: list[str]) -> str:
    out = ""
    for token in tokens:
        if not out:
            out = token
            continue
        if re.fullmatch(r"[.,!?;:%)]+", token) or token in {
            "n't",
            "'s",
            "'re",
            "'ve",
            "'ll",
            "'d",
            "'m",
        }:
            out += token
            continue
        if token in {"``", "''"}:
            continue
        if out.endswith("(") or out.endswith("["):
            out += token
            continue
        if token.startswith("  ") or out.endswith("  "):
            out += token
            continue
        out += " " + token
    return out


def _capitalize_sentence(text: str) -> str:
    for i, ch in enumerate(text):
        if ch.isalpha():
            if text[i : i + 1].casefold() == "i" and (
                i + 1 == len(text) or not text[i + 1].isalpha()
            ):
                return text[:i] + "I" + text[i + 1 :]
            return text[:i] + ch.upper() + text[i + 1 :]
    return text


VIA_LABELS = {
    "corpus": "from a line",
    "ollama": "Ollama",
    "synonym": "synonym",
    "similar": "nearby sense",
    "near": "nearby sense",
    "hypernym": "broader sense",
    "lemma": "word stem",
    "kept": "function word",
    "expanded": "contraction",
    "sentence": "from a line",
    "letters": "spelled from letters",
    "dropped": "removed",
    "original": "not found",
}


def format_output(text: str) -> str:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    formatted: list[str] = []
    for paragraph in paragraphs:
        if not paragraph.startswith("*"):
            paragraph = f"* {paragraph}"
        formatted.append(paragraph)
    return "\n\n".join(formatted)


def format_sources(result: RewriteResult) -> str:
    lines: list[str] = []
    if result.engine == "ollama":
        lines.append("Engine: Ollama")
    elif result.engine == "mixed":
        lines.append("Engine: local + Ollama")
    elif result.engine == "sentence":
        lines.append("Engine: sentence match")
    elif result.engine == "letter":
        lines.append("Engine: letter mode")
    else:
        lines.append("Engine: local lexicon")
    lines.append("")
    for change in result.changes:
        source = change.source or "—"
        via = VIA_LABELS.get(change.via, change.via)
        if change.via == "dropped":
            lines.append(f"{change.original:<18} removed (no close replacement)")
        elif change.via == "letters":
            lines.append(f"{change.original} →{change.written}({via})")
            for glyph, donor, donor_source in change.letters or ():
                if not glyph.isalpha():
                    continue
                origin = f"{donor} ({donor_source})" if donor else "—"
                lines.append(f"  {glyph} ← {origin}")
        elif change.via == "sentence":
            lines.append(f"{change.original}")
            lines.append(f"  → {change.written}    {source}")
        elif change.original.casefold() == change.written.casefold():
            word = change.written
            lines.append(f"{word:<18} {source} ({via})")
        else:
            lines.append(
                f"{change.original} → {change.written:<12} {source} ({via})"
            )
    if result.missing:
        lines.append("")
        lines.append(
            "No close replacement for: " + ", ".join(dict.fromkeys(result.missing))
        )
    return "\n".join(lines)
