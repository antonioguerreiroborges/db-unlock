"""Load and save config.ini, stored next to the executable."""

import configparser
import sys
from dataclasses import dataclass
from pathlib import Path

from . import dpapi

CONFIG_NAME = "config.ini"


class PasswordDecryptError(Exception):
    """The password was encrypted by another Windows user or machine."""


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
        if not self.password_encrypted:
            return ""
        try:
            return dpapi.unprotect(self.password_encrypted)
        except OSError as exc:
            raise PasswordDecryptError(
                "Cannot decrypt the password in config.ini: it was encrypted by another "
                "Windows user or machine. Run 'db-unlock setup' on this machine as this user, "
                "or set 'password = <plain password>' in config.ini (it is encrypted on next run)."
            ) from exc

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
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    db = parser["database"] if parser.has_section("database") else {}
    run = parser["run"] if parser.has_section("run") else {}
    defaults = Config()
    config = Config(
        host=db.get("host", defaults.host),
        port=int(db.get("port", defaults.port)),
        user=db.get("user", defaults.user),
        password_encrypted=db.get("password_encrypted", defaults.password_encrypted),
        target_user=db.get("target_user", defaults.target_user),
        retries=int(run.get("retries", defaults.retries)),
        retry_delay_seconds=int(run.get("retry_delay_seconds", defaults.retry_delay_seconds)),
        connect_timeout=int(run.get("connect_timeout", defaults.connect_timeout)),
    )
    # A plain text password (handy to deploy the ini to other machines) is
    # encrypted for the current Windows user and removed from the file.
    plain_password = db.get("password", "")
    if plain_password:
        config.password = plain_password
        save(config, path)
    return config


def save(config: Config, path: Path | None = None) -> Path:
    path = path or config_path()
    parser = configparser.ConfigParser(interpolation=None)
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
