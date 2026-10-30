"""Register Task Scheduler tasks for the current user (no admin needed).

One task records when the session is locked, the other runs the tool when the
session is unlocked; "on-unlock" itself decides if the lock lasted long enough.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from .config import app_dir

# (task name, session state change, command)
TASKS = [
    ("db-unlock-on-lock", "SessionLock", "on-lock"),
    ("db-unlock-on-unlock", "SessionUnlock", "on-unlock"),
]

# Shortcut created by older versions to run at logon.
LEGACY_SHORTCUT_NAME = "db-unlock.lnk"

_TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{description}</Description>
  </RegistrationInfo>
  <Triggers>
    <SessionStateChangeTrigger>
      <Enabled>true</Enabled>
      <StateChange>{state_change}</StateChange>
      <UserId>{user}</UserId>
    </SessionStateChangeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>conhost.exe</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{workdir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _current_user() -> str:
    return f"{os.environ['USERDOMAIN']}\\{os.environ['USERNAME']}"


def _launch_command(command: str) -> tuple[str, str, Path]:
    """Return (target, arguments, working directory) to run a tool command."""
    if getattr(sys, "frozen", False):
        return sys.executable, command, app_dir()
    return sys.executable, f"-m db_unlock {command}", Path(__file__).resolve().parents[1]


def _task_xml(state_change: str, command: str) -> str:
    target, arguments, workdir = _launch_command(command)
    # conhost --headless runs the console program without showing a window.
    return _TASK_XML.format(
        description=escape(f"db-unlock: run '{command}' on {state_change}"),
        state_change=state_change,
        user=escape(_current_user()),
        arguments=escape(f'--headless "{target}" {arguments}'),
        workdir=escape(str(workdir)),
    )


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True)


def legacy_shortcut_path() -> Path:
    startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup_dir / LEGACY_SHORTCUT_NAME


def _remove_legacy_shortcut() -> bool:
    path = legacy_shortcut_path()
    if path.exists():
        path.unlink()
        return True
    return False


def install() -> list[str]:
    """Create (or replace) the tasks; return their names."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, state_change, command in TASKS:
            xml_path = Path(tmp) / f"{name}.xml"
            xml_path.write_text(_task_xml(state_change, command), encoding="utf-16")
            result = _schtasks("/Create", "/TN", name, "/XML", str(xml_path), "/F")
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create task {name}: {(result.stderr or result.stdout).strip()}")
    _remove_legacy_shortcut()
    return [name for name, _, _ in TASKS]


def uninstall() -> list[str]:
    """Delete the tasks and the legacy shortcut; return what was removed."""
    removed = [name for name, _, _ in TASKS if _schtasks("/Delete", "/TN", name, "/F").returncode == 0]
    if _remove_legacy_shortcut():
        removed.append(str(legacy_shortcut_path()))
    return removed
