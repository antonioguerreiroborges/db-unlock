"""Find and kill MySQL connections of the target user, except our own session."""

import logging
from dataclasses import dataclass

import pymysql

from .config import Config

log = logging.getLogger(__name__)

# Thread finished between listing and killing it.
_ER_NO_SUCH_THREAD = 1094

_LIST_SQL = """
    SELECT ID, USER, HOST, DB, COMMAND, TIME
    FROM information_schema.PROCESSLIST
    WHERE USER = %s AND ID <> CONNECTION_ID()
    ORDER BY ID
"""


@dataclass
class Session:
    id: int
    user: str
    host: str
    db: str | None
    command: str
    time: int

    def __str__(self) -> str:
        return (f"id={self.id} user={self.user} host={self.host} db={self.db} "
                f"command={self.command} time={self.time}s")


def connect(config: Config) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        connect_timeout=config.connect_timeout,
        autocommit=True,
    )


def list_sessions(conn: pymysql.connections.Connection, target_user: str) -> list[Session]:
    with conn.cursor() as cur:
        cur.execute(_LIST_SQL, (target_user,))
        return [Session(*row) for row in cur.fetchall()]


def kill_sessions(conn: pymysql.connections.Connection, sessions: list[Session]) -> int:
    killed = 0
    with conn.cursor() as cur:
        for session in sessions:
            try:
                cur.execute(f"KILL {int(session.id)}")
                killed += 1
                log.info("Killed %s", session)
            except pymysql.MySQLError as exc:
                if exc.args[0] == _ER_NO_SUCH_THREAD:
                    log.info("Already gone: %s", session)
                else:
                    log.error("Could not kill %s: %s", session, exc)
    return killed
