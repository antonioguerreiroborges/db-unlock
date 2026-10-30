"""Command line interface."""

import argparse
import getpass
import logging
import sys
import time
from logging.handlers import RotatingFileHandler

import pymysql

from . import __version__, config, killer, lockstamp, scheduler

LOG_NAME = "db-unlock.log"

log = logging.getLogger("db_unlock")


def _setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(
        config.app_dir() / LOG_NAME, maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console)


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def _connect_with_retries(cfg: config.Config) -> pymysql.connections.Connection:
    attempts = max(1, cfg.retries)
    for attempt in range(1, attempts + 1):
        try:
            return killer.connect(cfg)
        except pymysql.MySQLError as exc:
            log.warning("Connection attempt %d/%d failed: %s", attempt, attempts, exc)
            if attempt == attempts:
                raise
            time.sleep(cfg.retry_delay_seconds)
    raise AssertionError("unreachable")


def cmd_setup(_args: argparse.Namespace) -> int:
    try:
        cfg = config.load()
    except FileNotFoundError:
        cfg = config.Config()
    print(f"Configuring {config.config_path()}")
    cfg.host = _ask("MySQL host", cfg.host)
    cfg.port = int(_ask("MySQL port", str(cfg.port)))
    cfg.user = _ask("MySQL user", cfg.user)
    password = getpass.getpass("MySQL password (leave empty to keep current): ")
    if password:
        cfg.password = password
    cfg.target_user = _ask("User whose connections will be killed (empty = same user)",
                           cfg.target_user)
    path = config.save(cfg)
    print(f"Saved {path}")
    if _ask("Test the connection now? (y/n)", "y").lower().startswith("y"):
        return cmd_test(_args)
    return 0


def cmd_test(_args: argparse.Namespace) -> int:
    cfg = config.load()
    with killer.connect(cfg) as conn:
        sessions = killer.list_sessions(conn, cfg.effective_target_user)
    print(f"Connected to {cfg.host}:{cfg.port} as {cfg.user}.")
    print(f"{len(sessions)} connection(s) of '{cfg.effective_target_user}' would be killed:")
    for session in sessions:
        print(f"  {session}")
    return 0


def cmd_run(_args: argparse.Namespace) -> int:
    cfg = config.load()
    log.info("Starting: host=%s port=%s user=%s target_user=%s",
             cfg.host, cfg.port, cfg.user, cfg.effective_target_user)
    with _connect_with_retries(cfg) as conn:
        sessions = killer.list_sessions(conn, cfg.effective_target_user)
        log.info("Found %d connection(s) to kill", len(sessions))
        killed = killer.kill_sessions(conn, sessions)
    log.info("Done: %d connection(s) killed", killed)
    return 0


def cmd_on_lock(_args: argparse.Namespace) -> int:
    lockstamp.write()
    log.info("Session locked: time recorded")
    return 0


def cmd_on_unlock(args: argparse.Namespace) -> int:
    cfg = config.load()
    locked_for = lockstamp.locked_for()
    # Each lock records a new time; clearing it avoids reusing a stale one.
    lockstamp.clear()
    if locked_for is None:
        log.info("Session unlocked: skipped, no lock time recorded")
        return 0
    hours = locked_for.total_seconds() / 3600
    if hours < cfg.min_locked_hours:
        log.info("Session unlocked: skipped, locked for %.2fh < %gh", hours, cfg.min_locked_hours)
        return 0
    log.info("Session unlocked after %.2fh locked (>= %gh)", hours, cfg.min_locked_hours)
    return cmd_run(args)


def cmd_install(_args: argparse.Namespace) -> int:
    for name in scheduler.install():
        log.info("Scheduled task created: %s", name)
    return 0


def cmd_uninstall(_args: argparse.Namespace) -> int:
    removed = scheduler.uninstall()
    for item in removed:
        log.info("Removed: %s", item)
    if not removed:
        log.info("Nothing to remove")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="db-unlock",
        description="Kill all MySQL connections of a user (except its own) to release locks.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("setup", help="interactively configure the database connection")
    sub.add_parser("test", help="connect and list connections that would be killed (dry run)")
    sub.add_parser("run", help="kill the connections (default when no command is given)")
    sub.add_parser("install", aliases=["install-startup"],
                   help="run automatically when the session is unlocked after a long lock")
    sub.add_parser("uninstall", aliases=["uninstall-startup"], help="remove the scheduled tasks")
    sub.add_parser("on-lock", help="record the lock time (called by the scheduled task)")
    sub.add_parser("on-unlock", help="run if the session was locked long enough (called by the scheduled task)")
    return parser


COMMANDS = {
    "setup": cmd_setup,
    "test": cmd_test,
    "run": cmd_run,
    "install": cmd_install,
    "install-startup": cmd_install,
    "uninstall": cmd_uninstall,
    "uninstall-startup": cmd_uninstall,
    "on-lock": cmd_on_lock,
    "on-unlock": cmd_on_unlock,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging()
    command = args.command or "run"
    try:
        return COMMANDS[command](args)
    except (FileNotFoundError, config.PasswordDecryptError) as exc:
        log.error("%s", exc)
    except pymysql.MySQLError as exc:
        log.error("MySQL error: %s", exc)
    except KeyboardInterrupt:
        log.error("Interrupted")
    except Exception:
        log.exception("Unexpected error")
    return 1


if __name__ == "__main__":
    sys.exit(main())
