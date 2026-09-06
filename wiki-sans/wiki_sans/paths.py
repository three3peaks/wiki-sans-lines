"""Resolve resource and writable paths for source runs and the frozen exe."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    if is_frozen():
        return app_dir()
    return Path(__file__).resolve().parents[2]


def images_dir() -> Path:
    for candidate in (
        resource_dir() / "images",
        app_dir() / "images",
        repo_root() / "images",
    ):
        if candidate.is_dir():
            return candidate
    return resource_dir() / "images"


def data_dir() -> Path:
    bundled = resource_dir() / "data"
    if (bundled / "lexicon.json").exists():
        return bundled
    return app_dir() / "data"


def lexicon_path() -> Path:
    return data_dir() / "lexicon.json"


def sentences_path() -> Path:
    bundled = data_dir() / "sentences.json"
    if bundled.exists():
        return bundled
    return app_dir() / "data" / "sentences.json"


def textboxes_path() -> Path:
    return repo_root() / "character-textboxes" / "undertale.plain.json"


def log_dir() -> Path:
    return app_dir() / "logs"


def history_path() -> Path:
    return app_dir() / "history.json"


def config_path() -> Path:
    return app_dir() / "config.json"


def nltk_data_dirs() -> list[Path]:
    dirs = [resource_dir() / "nltk_data", app_dir() / "nltk_data"]
    return [path for path in dirs if path.is_dir()]
