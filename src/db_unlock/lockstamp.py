"""Remember when the Windows session was locked, to measure how long it stayed locked."""

import time
from datetime import timedelta

from .config import lock_stamp_path


def write() -> None:
    lock_stamp_path().write_text(f"{time.time():.0f}\n", encoding="utf-8")


def locked_for() -> timedelta | None:
    """Time since the last recorded lock, or None if no valid lock was recorded."""
    try:
        locked_at = float(lock_stamp_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return timedelta(seconds=max(0.0, time.time() - locked_at))
