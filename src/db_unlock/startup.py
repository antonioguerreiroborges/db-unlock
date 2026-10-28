"""Register the tool in the current user's Windows Startup folder (no admin needed)."""

import os
import subprocess
import sys
from pathlib import Path

from .config import app_dir

SHORTCUT_NAME = "db-unlock.lnk"
_WINDOW_MINIMIZED = 7

# Values are passed through environment variables to avoid quoting issues.
_CREATE_SHORTCUT_PS = """
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($env:DBU_LINK)
$link.TargetPath = $env:DBU_TARGET
$link.Arguments = $env:DBU_ARGS
$link.WorkingDirectory = $env:DBU_WORKDIR
$link.WindowStyle = [int]$env:DBU_STYLE
$link.Description = 'Kill stale MySQL connections at logon'
$link.Save()
"""


def startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return startup_dir() / SHORTCUT_NAME


def _launch_command() -> tuple[str, str, Path]:
    """Return (target, arguments, working directory) to run the tool."""
    if getattr(sys, "frozen", False):
        return sys.executable, "run", app_dir()
    return sys.executable, "-m db_unlock run", Path(__file__).resolve().parents[1]


def install() -> Path:
    target, arguments, workdir = _launch_command()
    env = dict(
        os.environ,
        DBU_LINK=str(shortcut_path()),
        DBU_TARGET=target,
        DBU_ARGS=arguments,
        DBU_WORKDIR=str(workdir),
        DBU_STYLE=str(_WINDOW_MINIMIZED),
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _CREATE_SHORTCUT_PS],
        env=env, check=True, capture_output=True,
    )
    return shortcut_path()


def uninstall() -> bool:
    path = shortcut_path()
    if path.exists():
        path.unlink()
        return True
    return False
