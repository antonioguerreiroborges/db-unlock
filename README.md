# db-unlock

Small Windows tool that runs when the Windows session is **unlocked after a
long lock** (e.g. the laptop lid was closed overnight) and **kills every MySQL
connection of a given database user (except its own session)**, releasing
locks left behind by dead or hung connections.

It ships as a single `db-unlock.exe` with the MySQL client built in: the
machine does **not** need MySQL, Python or any other runtime installed.

## How it works

The user usually does not shut the laptop down: they close the lid at the end
of the day (the session is locked and the machine sleeps or hibernates) and
unlock it the next morning. So instead of running at logon, `install` creates
two tasks in the Windows Task Scheduler:

| Task | Trigger | What it does |
| --- | --- | --- |
| `db-unlock-on-lock` | Session locked | Records the lock time in `last-lock.txt` |
| `db-unlock-on-unlock` | Session unlocked | If the session stayed locked for at least `min_locked_hours` (default **6**), kills the connections; otherwise just logs "skipped" |

Closing the lid locks the session, so the locked time covers the time the
laptop was asleep or hibernated. The tasks run hidden (no console window).

> The tool does **not** run at logon after a restart or power-on: a logon is
> not an unlock. Use `db-unlock.exe run` manually if needed.

When it runs, it:

1. Connects to the MySQL server configured in `config.ini` (retrying a few
   times, since the network may not be ready right after waking up).
2. Lists the target user's connections:
   ```sql
   SELECT ID, USER, HOST, DB, COMMAND, TIME
   FROM information_schema.PROCESSLIST
   WHERE USER = '<target_user>' AND ID <> CONNECTION_ID();
   ```
3. Runs `KILL <id>` for each one and writes the result to `db-unlock.log`.

> **Warning:** every connection of the target user is killed, from any
> machine, whatever it is doing. Make sure no one else is using that user for
> important work when the tool runs.

## Installation

1. Create a folder the Windows user can write to, e.g. `C:\db-unlock\`, and
   copy `db-unlock.exe` into it. `config.ini` and `db-unlock.log` are kept in
   the same folder. Avoid `C:\Program Files`, which is read-only for normal
   users.
2. Open a terminal (`cmd` or PowerShell) in that folder **logged in as the
   Windows user that will run the tool** and configure the connection:
   ```
   db-unlock.exe setup
   ```
3. Check what would be killed, without killing anything:
   ```
   db-unlock.exe test
   ```
4. Register it to run when the session is unlocked after a long lock:
   ```
   db-unlock.exe install
   ```
   This creates the two scheduled tasks described above for the current
   Windows user. No administrator rights are needed. Run it again if the exe
   is moved to another folder.

   **Upgrading from an older version** that used a Startup folder shortcut:
   just run `install`; it removes the old `db-unlock.lnk` shortcut.

To run it manually at any time: `db-unlock.exe run` (or just double-click the
exe).

## Configuring the database connection and user

`db-unlock.exe setup` asks for:

| Prompt | Meaning |
| --- | --- |
| MySQL host | Server name or IP, e.g. `192.168.0.10` |
| MySQL port | Usually `3306` |
| MySQL user | User used to connect |
| MySQL password | Stored encrypted (see below). Leave empty to keep the current one |
| User whose connections will be killed | Empty = same as the MySQL user |

Run `setup` again at any time to change any value; current values are shown
as defaults, so press Enter to keep them.

The result is `config.ini` next to the exe (see `config.example.ini`):

```ini
[database]
host = 192.168.0.10
port = 3306
user = app_user
password_encrypted = AQAAANCMnd8BFdER...
target_user =

[run]
retries = 5
retry_delay_seconds = 10
connect_timeout = 10
; Minimum hours the session must stay locked before an unlock kills connections.
min_locked_hours = 6
```

`host`, `port`, `user`, `target_user` and the `[run]` options can also be
edited directly in a text editor.

### Password security

The password is encrypted with Windows DPAPI. Only the **same Windows user on
the same machine** that ran `setup` can decrypt it. Consequences:

- Run `setup` as the user who logs in and runs the tool.
- A `config.ini` with `password_encrypted` copied from another machine or
  user does **not** work (error "Cannot decrypt the password in config.ini").
- To change the password, run `setup` again or use a plain text password (below).

### Deploying a ready-made config.ini to other machines

Instead of running `setup` on each machine, ship `config.ini` with the
password in plain text and **without** `password_encrypted`:

```ini
[database]
host = db.example.com
port = 3306
user = app_user
password = my-secret-password
```

On the first run on the target machine, the tool encrypts the password for
that Windows user, writes it to `password_encrypted` and removes the plain
`password` line from the file.

### Required MySQL privileges

- Killing connections of **the same user** you connect with: no extra
  privilege required.
- Killing connections of **another user** (`target_user` different from
  `user`): the connecting user needs `PROCESS` (to see them) and
  `CONNECTION_ADMIN` (MySQL 8+) or `SUPER` (MySQL 5.7 / MariaDB).
  ```sql
  GRANT PROCESS, CONNECTION_ADMIN ON *.* TO 'admin_user'@'%';
  ```

## Commands

| Command | Description |
| --- | --- |
| `db-unlock.exe setup` | Interactively configure the connection |
| `db-unlock.exe test` | Connect and list connections that would be killed (dry run) |
| `db-unlock.exe run` | Kill the connections (default when no command is given) |
| `db-unlock.exe install` | Create the scheduled tasks (run on unlock after a long lock) |
| `db-unlock.exe uninstall` | Remove the scheduled tasks |
| `db-unlock.exe on-lock` | Record the lock time (called by the lock task) |
| `db-unlock.exe on-unlock` | Run if locked for at least `min_locked_hours` (called by the unlock task) |
| `db-unlock.exe --version` | Show version |

The exit code is `0` on success and `1` on any error.

## Logs

Every lock, unlock and run is appended to `db-unlock.log` next to the exe (rotated at 512 KB,
2 backups kept). Example:

```
2026-10-27 18:02:40,101 INFO Session locked: time recorded
2026-10-28 08:00:12,300 INFO Session unlocked after 13.96h locked (>= 6h)
2026-10-28 08:00:12,345 INFO Starting: host=192.168.0.10 port=3306 user=app_user target_user=app_user
2026-10-28 08:00:12,410 INFO Found 2 connection(s) to kill
2026-10-28 08:00:12,415 INFO Killed id=1201 user=app_user host=10.0.0.5:51234 db=erp command=Sleep time=3600s
2026-10-28 08:00:12,417 INFO Killed id=1207 user=app_user host=10.0.0.8:50110 db=erp command=Query time=95s
2026-10-28 08:00:12,420 INFO Done: 2 connection(s) killed
```

## Uninstall

```
db-unlock.exe uninstall
```

Then delete the folder with the exe.

## Building from source

Requirements: Windows and Python 3.11+.

```powershell
.\build.ps1
```

This creates `.venv`, installs the dependencies (`PyMySQL`, `cryptography`,
`PyInstaller`) and produces `dist\db-unlock.exe`.

To run from source without building:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m db_unlock --help
```

When run from source, `config.ini` and the log are stored in the project root.
