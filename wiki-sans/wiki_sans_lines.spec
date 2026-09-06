# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

SPECDIR = Path(SPECPATH)
REPO = SPECDIR.parent
IMAGES = REPO / "images"
DATA = SPECDIR / "data"
ICON = IMAGES / "wiki_sans_v2_face.ico"


def _nltk_roots() -> list[Path]:
    roots = [
        Path.home() / "AppData" / "Roaming" / "nltk_data",
        Path.home() / "nltk_data",
    ]
    try:
        import nltk

        roots = [Path(item) for item in nltk.data.path] + roots
    except ImportError:
        pass
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root)
        if key in seen or not root.is_dir():
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _collect_tree(src: Path, dest_prefix: str) -> list:
    items = []
    if not src.exists():
        return items
    if src.is_file():
        return [(str(src), dest_prefix.replace("\\", "/"))]
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        dest = Path(dest_prefix) / rel.parent
        items.append((str(path), str(dest).replace("\\", "/")))
    return items


def _collect_nltk() -> list:
    items = []
    seen: set[tuple[str, str]] = set()
    parts = (
        ("taggers/averaged_perceptron_tagger", "nltk_data/taggers/averaged_perceptron_tagger"),
        ("taggers/averaged_perceptron_tagger_eng", "nltk_data/taggers/averaged_perceptron_tagger_eng"),
        ("tokenizers/punkt", "nltk_data/tokenizers/punkt"),
        ("tokenizers/punkt_tab", "nltk_data/tokenizers/punkt_tab"),
        ("corpora/wordnet.zip", "nltk_data/corpora"),
        ("corpora/wordnet", "nltk_data/corpora/wordnet"),
        ("corpora/omw-1.4.zip", "nltk_data/corpora"),
        ("corpora/omw-1.4", "nltk_data/corpora/omw-1.4"),
    )
    for root in _nltk_roots():
        for rel, dest in parts:
            src = root / rel
            for item in _collect_tree(src, dest):
                key = (item[0], item[1])
                if key not in seen:
                    seen.add(key)
                    items.append(item)
    return items


datas = [
    (str(DATA / "lexicon.json"), "data"),
]
sentences = DATA / "sentences.json"
if sentences.exists():
    datas.append((str(sentences), "data"))
for name in (
    "wiki_sans_v2_face.ico",
    "wiki_sans_v2_face.png",
    "wiki_sans_v2_body.png",
):
    image = IMAGES / name
    if image.exists():
        datas.append((str(image), "images"))
datas += _collect_nltk()

a = Analysis(
    [str(SPECDIR / "main.py")],
    pathex=[str(SPECDIR)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "nltk",
        "nltk.corpus",
        "nltk.corpus.wordnet",
        "nltk.data",
        "nltk.downloader",
        "nltk.tag",
        "nltk.tag.perceptron",
        "nltk.tokenize",
        "nltk.tokenize.punkt",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "wiki_sans",
        "wiki_sans.config",
        "wiki_sans.gui",
        "wiki_sans.lexicon",
        "wiki_sans.memory",
        "wiki_sans.nltk_setup",
        "wiki_sans.ollama_setup",
        "wiki_sans.paths",
        "wiki_sans.rewrite",
        "wiki_sans.session_log",
        "wiki_sans.synonyms",
        "wiki_sans.text_split",
        "wiki_sans.wordnet_log",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "numpy",
        "pandas",
        "pytest",
        "scipy",
        "tkinter.test",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WIKI!Sans lines",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
    version=str(SPECDIR / "file_version_info.txt"),
)
