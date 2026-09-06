"""Собрать однофайловый WIKI!Sans lines.exe. Запускается из build-exe.bat."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "wiki_sans_lines.spec"
DIST = ROOT / "dist"
EXE_NAME = "WIKI!Sans lines.exe"
SHORTCUT_NAME = "WIKI!Sans lines.lnk"
CONFIG_NAME = "config.json"
PIP_TRUST = [
    "--trusted-host",
    "pypi.org",
    "--trusted-host",
    "pypi.python.org",
    "--trusted-host",
    "files.pythonhosted.org",
]


def run(args: list[str]) -> None:
    print(">", " ".join(args), flush=True)
    subprocess.check_call(args, cwd=ROOT)


def have_module(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


def pip_install(*packages: str) -> None:
    run([sys.executable, "-m", "pip", "install", *PIP_TRUST, *packages])


def copy_config() -> Path:
    source = ROOT / CONFIG_NAME
    dest = DIST / CONFIG_NAME
    DIST.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"Конфиг уже есть, не перезаписываю: {dest}")
        return dest
    if source.exists():
        shutil.copy2(source, dest)
    else:
        dest.write_text(
            '{\n'
            '  "wordnet": true,\n'
            '  "ollama": true,\n'
            '  "ollama_host": "http://127.0.0.1:11434",\n'
            '  "ollama_model": "qwen2.5:7b",\n'
            '  "default_mode": "word"\n'
            '}\n',
            encoding="utf-8",
        )
    print(f"Конфиг: {dest}")
    return dest


def create_shortcut(exe: Path) -> Path | None:
    shortcut = DIST / SHORTCUT_NAME
    if sys.platform != "win32":
        print("Ярлык: пропуск (нужен Windows).")
        return None
    script = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$s = $ws.CreateShortcut($env:WIKI_SANS_LINK)\n"
        "$s.TargetPath = $env:WIKI_SANS_TARGET\n"
        "$s.WorkingDirectory = $env:WIKI_SANS_WORKDIR\n"
        "$s.IconLocation = ($env:WIKI_SANS_TARGET + ',0')\n"
        "$s.Description = 'WIKI!Sans lines'\n"
        "$s.Save()\n"
    )
    env = {
        **os.environ,
        "WIKI_SANS_LINK": str(shortcut),
        "WIKI_SANS_TARGET": str(exe),
        "WIKI_SANS_WORKDIR": str(exe.parent),
    }
    subprocess.check_call(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        env=env,
    )
    if not shortcut.exists():
        raise RuntimeError(f"Ярлык не создан: {shortcut}")
    print(f"Ярлык: {shortcut}")
    return shortcut


def main() -> int:
    if sys.version_info < (3, 10):
        print("Нужен Python 3.10 или новее.")
        return 1

    print(f"Python: {sys.version}")
    missing = [name for name in ("nltk", "PIL") if not have_module(name)]
    if missing:
        print("Ставлю зависимости программы...")
        pip_install("-r", str(ROOT / "requirements.txt"))
    if not have_module("PyInstaller"):
        print("Ставлю PyInstaller...")
        pip_install("pyinstaller")
    else:
        print("PyInstaller уже установлен.")

    icon = ROOT.parent / "images" / "wiki_sans_v2_face.ico"
    lexicon = ROOT / "data" / "lexicon.json"
    if not icon.exists():
        print(f"Не найдена иконка: {icon}")
        return 1
    if not lexicon.exists():
        print(f"Не найден словарь: {lexicon}")
        return 1
    if not SPEC.exists():
        print(f"Не найден spec: {SPEC}")
        return 1

    print("Готовлю индекс реплик...")
    sys.path.insert(0, str(ROOT))
    from wiki_sans.memory import load_or_build_memory

    memory = load_or_build_memory()
    print(f"Реплик в индексе: {len(memory.lines)}")

    print("Собираю exe...")
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC),
        ]
    )

    exe = DIST / EXE_NAME
    if not exe.exists():
        print(f"PyInstaller завершился, но файл не найден: {exe}")
        return 1

    copy_config()
    create_shortcut(exe)

    size_mb = exe.stat().st_size / (1024 * 1024)
    print()
    print(f"Готово: {exe}")
    print(f"Размер: {size_mb:.1f} МБ")
    try:
        subprocess.Popen(["explorer", "/select,", str(exe)])
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Команда завершилась с кодом {exc.returncode}")
        print("Если pip ругается на SSL, отключите VPN и запустите сборку ещё раз.")
        raise SystemExit(exc.returncode)
