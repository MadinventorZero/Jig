#!/usr/bin/env python3
"""Jig — cross-platform setup.
Called by setup.command after Python is confirmed.
"""
import subprocess
import sys
import platform
from pathlib import Path

ROOT = Path(__file__).parent
VENV = ROOT / ".venv"
MIN_PY = (3, 13)
OS = platform.system()

DATA_DIRS = [
    ROOT / "data" / "profiles",
    ROOT / "data" / "bookings",
    ROOT / "data" / "schedules",
    ROOT / "data" / "credentials",
    ROOT / "data" / "logs",
]


def step(msg: str) -> None:
    print(f"\n  {msg}")


def fail(msg: str, fix: str = "") -> None:
    print(f"\n  ERROR: {msg}")
    if fix:
        print()
        for line in fix.strip().splitlines():
            print(f"  {line}")
    print()
    try:
        input("  Press Enter to exit...")
    except (EOFError, KeyboardInterrupt):
        pass
    sys.exit(1)


def check_python() -> None:
    if sys.version_info < MIN_PY:
        pv = (ROOT / ".python-version").read_text().strip()
        fail(
            f"Python {pv} required (found {sys.version.split()[0]}).",
            "Run setup.command — it installs the correct version automatically.",
        )
    step(f"Python {sys.version.split()[0]} — OK")


def create_venv() -> None:
    if VENV.exists():
        step("Virtual environment exists — skipping.")
        return
    step("Creating virtual environment...")
    try:
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    except subprocess.CalledProcessError:
        fail("Failed to create virtual environment.",
             f"Check write permissions for: {ROOT}")


def _venv_exe(name: str) -> Path:
    if OS == "Windows":
        return VENV / "Scripts" / f"{name}.exe"
    return VENV / "bin" / name


def install_deps() -> None:
    pip = _venv_exe("pip")
    step("Upgrading pip...")
    subprocess.run(
        [str(pip), "install", "--upgrade", "pip"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    step("Installing requirements...")
    try:
        subprocess.run(
            [str(pip), "install", "-r", str(ROOT / "requirements.txt")],
            check=True,
        )
    except subprocess.CalledProcessError:
        fail("Failed to install requirements.",
             "Check network access and the error above.")


def install_playwright_browser() -> None:
    step("Installing Playwright browser (Chromium)...")
    python = _venv_exe("python")
    try:
        subprocess.run(
            [str(python), "-m", "playwright", "install", "chromium"],
            check=True,
        )
    except subprocess.CalledProcessError:
        fail("Failed to install Playwright browser.",
             f"Manual fix: {python} -m playwright install chromium")


def create_data_dirs() -> None:
    step("Creating data directories...")
    for d in DATA_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()


def write_launcher() -> None:
    if OS == "Darwin":
        launcher = ROOT / "Jig.command"
        launcher.write_text(
            '#!/bin/bash\ncd "$(dirname "$0")"\n.venv/bin/python run.py\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
        setup_command = ROOT / "setup.command"
        setup_command.chmod(0o755)
        step(f"Launcher created: {launcher.name}")
    elif OS == "Windows":
        launcher = ROOT / "Jig.bat"
        launcher.write_text(
            '@echo off\ncd /d "%~dp0"\n.venv\\Scripts\\python.exe run.py\n',
            encoding="utf-8",
        )
        step(f"Launcher created: {launcher.name}")
    else:
        step("Unsupported OS — run manually: .venv/bin/python run.py")


def print_summary() -> None:
    print("\n" + "=" * 42)
    print("  Setup complete!")
    print("=" * 42)
    print()
    if OS == "Darwin":
        print("  Launch: double-click 'Jig.command'")
    elif OS == "Windows":
        print("  Launch: double-click 'Jig.bat'")
    print()
    print("  Next: open Settings in the app to connect your Gmail account.")
    print()


def main() -> None:
    print("\n" + "=" * 42)
    print("  Jig — Setup")
    print("=" * 42)

    check_python()
    create_venv()
    install_deps()
    install_playwright_browser()
    create_data_dirs()
    write_launcher()
    print_summary()


if __name__ == "__main__":
    main()
