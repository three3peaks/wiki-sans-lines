"""Optional WordNet. Use it when reachable; otherwise stay local."""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

from wiki_sans.config import get_config
from wiki_sans.paths import is_frozen, nltk_data_dirs
from wiki_sans.wordnet_log import write_session

try:
    import nltk
    from nltk.corpus import wordnet as wn
except ImportError as exc:
    nltk = None
    wn = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None
    for extra in reversed(nltk_data_dirs()):
        path = str(extra)
        if path not in nltk.data.path:
            nltk.data.path.insert(0, path)

_WORDNET_PATHS = ("corpora/wordnet",)
_TAGGER_PATHS = (
    "taggers/averaged_perceptron_tagger_eng",
    "taggers/averaged_perceptron_tagger",
)
_TOKENIZER_PATHS = (
    "tokenizers/punkt_tab",
    "tokenizers/punkt",
)


@dataclass
class NltkStatus:
    package: bool = False
    wordnet: bool = False
    tagger: bool = False


status = NltkStatus()
last_log_path = None


def _found(paths: tuple[str, ...]) -> bool:
    if nltk is None:
        return False
    for path in paths:
        try:
            nltk.data.find(path)
            return True
        except LookupError:
            continue
    return False


def _missing_paths(paths: tuple[str, ...]) -> list[str]:
    if nltk is None:
        return list(paths)
    missing: list[str] = []
    for path in paths:
        try:
            nltk.data.find(path)
        except LookupError:
            missing.append(path)
    return missing


def _refresh() -> None:
    status.package = nltk is not None
    status.wordnet = _found(_WORDNET_PATHS)
    status.tagger = _found(_TAGGER_PATHS) and _found(_TOKENIZER_PATHS)
    if not status.wordnet:
        global wn
        wn = None


def _download_one(name: str) -> tuple[bool, str, BaseException | None]:
    if nltk is None:
        return False, "", RuntimeError("nltk is not installed")
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            nltk.download(
                name,
                quiet=True,
                halt_on_error=True,
                raise_on_error=True,
                print_error_to=sink,
            )
    except Exception as exc:
        return False, sink.getvalue().strip(), exc
    return True, sink.getvalue().strip(), None


def wordnet_ready() -> bool:
    return bool(get_config().wordnet and status.wordnet)


def tagger_ready() -> bool:
    return status.tagger


def get_wn():
    return wn if wordnet_ready() else None


def ensure_wordnet() -> bool:
    """Connect to WordNet if possible. Failures are written to the log."""
    global last_log_path, wn
    notes: list[str] = []

    if not get_config().wordnet:
        status.wordnet = False
        notes.append("disabled in config.json (wordnet: false)")
        notes.append("result: skipped")
        last_log_path = write_session(notes)
        return False

    _refresh()
    if nltk is None:
        notes.append("nltk package: not installed")
        notes.append(f"import error: {_IMPORT_ERROR}")
        notes.append("result: unavailable")
        last_log_path = write_session(notes)
        return False

    notes.append(f"nltk package: installed ({getattr(nltk, '__version__', '?')})")
    missing = _missing_paths(_WORDNET_PATHS)
    if not missing:
        notes.append("local wordnet: found")
        notes.append("result: connected (local data)")
        last_log_path = write_session(notes)
        return True

    notes.append(f"local wordnet: missing ({', '.join(missing)})")
    if is_frozen():
        notes.append("frozen exe: skip download")
        notes.append("result: unavailable")
        last_log_path = write_session(notes)
        return False
    notes.append("trying download from NLTK servers")

    for name in ("wordnet", "omw-1.4"):
        ok, output, exc = _download_one(name)
        if ok and _found(_WORDNET_PATHS if name == "wordnet" else ("corpora/omw-1.4",)):
            notes.append(f"  {name}: downloaded")
        else:
            notes.append(f"  {name}: failed")
            if exc is not None:
                notes.append(f"    exception: {type(exc).__name__}: {exc}")
            if output:
                for line in output.splitlines():
                    notes.append(f"    {line}")
            if ok:
                notes.append("    nltk reported success, but data files are still missing")

    if nltk is not None:
        try:
            from nltk.corpus import wordnet as wordnet_mod

            wn = wordnet_mod
        except ImportError as exc:
            wn = None
            notes.append(f"reload error: {type(exc).__name__}: {exc}")

    _refresh()
    if status.wordnet:
        notes.append("result: connected")
    else:
        notes.append("result: unavailable")
        still_missing = _missing_paths(_WORDNET_PATHS)
        if still_missing:
            notes.append(f"still missing: {', '.join(still_missing)}")

    last_log_path = write_session(notes)
    return status.wordnet


_refresh()
