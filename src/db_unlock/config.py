"""Load and save config.ini, stored next to the executable."""

import configparser
import sys
from dataclasses import dataclass
from pathlib import Path

from . import dpapi

CONFIG_NAME = "config.ini"


def app_dir() -> Path:
    """Folder holding the exe (frozen) or the project root (source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def config_path() -> Path:
    return app_dir() / CONFIG_NAME


@dataclass
class Config:
    host: str = "localhost"
    port: int = 3306
    user: str = ""
    password_encrypted: str = ""
    target_user: str = ""
    retries: int = 5
    retry_delay_seconds: int = 10
    connect_timeout: int = 10

    @property
    def password(self) -> str:
        return dpapi.unprotect(self.password_encrypted) if self.password_encrypted else ""

    @password.setter
    def password(self, value: str) -> None:
        self.password_encrypted = dpapi.protect(value) if value else ""

    @property
    def effective_target_user(self) -> str:
        return self.target_user or self.user


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}. Run 'db-unlock setup' first.")
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    db = parser["database"] if parser.has_section("database") else {}
    run = parser["run"] if parser.has_section("run") else {}
    defaults = Config()
    return Config(
        host=db.get("host", defaults.host),
        port=int(db.get("port", defaults.port)),
        user=db.get("user", defaults.user),
        password_encrypted=db.get("password_encrypted", defaults.password_encrypted),
        target_user=db.get("target_user", defaults.target_user),
        retries=int(run.get("retries", defaults.retries)),
        retry_delay_seconds=int(run.get("retry_delay_seconds", defaults.retry_delay_seconds)),
        connect_timeout=int(run.get("connect_timeout", defaults.connect_timeout)),
    )


def save(config: Config, path: Path | None = None) -> Path:
    path = path or config_path()
    parser = configparser.ConfigParser()
    parser["database"] = {
        "host": config.host,
        "port": str(config.port),
        "user": config.user,
        "password_encrypted": config.password_encrypted,
        "target_user": config.target_user,
    }
    parser["run"] = {
        "retries": str(config.retries),
        "retry_delay_seconds": str(config.retry_delay_seconds),
        "connect_timeout": str(config.connect_timeout),
    }
    with path.open("w", encoding="utf-8") as fh:
        parser.write(fh)
    return path
