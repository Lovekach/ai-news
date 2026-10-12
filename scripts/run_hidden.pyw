"""Run the news collector from Task Scheduler without opening a terminal."""

from __future__ import annotations

import subprocess
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ainews.security import redact

COMMANDS = {"scan": "scan-once", "editor": "daily-prepare", "daily": "daily-publish", "telegram": "telegram-scan-once", "x": "x-scan-once", "full": "run-once"}
MODE = sys.argv[1] if len(sys.argv) > 1 else "full"
LOG_PATH = ROOT / ".state" / f"{MODE}.log"
PYTHON = Path(sys.executable).with_name("python.exe")


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"[{datetime.now(timezone(timedelta(hours=3))).isoformat()}] {redact(message)}\n")


def task_timeout(mode: str, now: datetime | None = None) -> float:
    if mode == "editor":
        current = (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=3)))
        stop = current.replace(hour=20, minute=59, second=10, microsecond=0)
        # The last editorial process is killed before publication even if a
        # source download or a model response stalls beyond its own timeout.
        return max(0, min(28 * 60, (stop - current).total_seconds()))
    return 55 if mode == "scan" else 4 * 60 if mode in {"telegram", "x"} else 120


def main() -> int:
    if MODE not in COMMANDS:
        return 2
    timeout = task_timeout(MODE)
    if timeout == 0:
        log("evening editorial deadline passed; no process started")
        return 0
    log("start (hidden)")
    try:
        result = subprocess.run(
            [str(PYTHON), "-m", "ainews", COMMANDS[MODE]],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
        if result.stdout:
            log(result.stdout.rstrip())
        if result.stderr:
            log(f"stderr: {result.stderr.rstrip()}")
        log(f"exit={result.returncode}")
        return result.returncode
    except subprocess.TimeoutExpired:
        log("error: task timed out")
        return 124
    except Exception:
        log(f"error: {traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
