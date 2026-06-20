"""SQLite-backed storage for per-identity conversation history and facts."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


class MemoryStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        self._conn.commit()
        self._migrate()

    def _migrate(self):
        # Databases created before these features don't have these columns
        # yet; CREATE TABLE IF NOT EXISTS won't add them.
        for ddl in (
            "ALTER TABLE identities ADD COLUMN language TEXT",
            "ALTER TABLE identities ADD COLUMN last_routine TEXT",
        ):
            try:
                self._conn.execute(ddl)
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

    def close(self):
        self._conn.close()

    # -- identities ---------------------------------------------------

    def list_identity_names(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM identities ORDER BY name").fetchall()
        return [row["name"] for row in rows]

    def get_or_create_identity(self, name: str, kind: str = "person") -> int:
        row = self._conn.execute("SELECT id FROM identities WHERE name = ?", (name,)).fetchone()
        if row is not None:
            return row["id"]
        cur = self._conn.execute(
            "INSERT INTO identities (name, kind) VALUES (?, ?)", (name, kind)
        )
        self._conn.commit()
        return cur.lastrowid

    def rename_identity(self, old_name: str, new_name: str):
        self._conn.execute(
            "UPDATE identities SET name = ? WHERE name = ?", (new_name, old_name)
        )
        self._conn.commit()

    def touch_last_seen(self, identity_id: int):
        self._conn.execute(
            "UPDATE identities SET last_seen = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), identity_id),
        )
        self._conn.commit()

    def get_mood(self, identity_id: int) -> float:
        row = self._conn.execute("SELECT mood FROM identities WHERE id = ?", (identity_id,)).fetchone()
        return row["mood"] if row else 0.0

    def update_mood(self, identity_id: int, valence: float, alpha: float) -> float:
        """Nudges the identity's running mood score towards `valence` by
        `alpha` (exponential moving average) and returns the new value."""
        current = self.get_mood(identity_id)
        new_mood = (1 - alpha) * current + alpha * valence
        self._conn.execute("UPDATE identities SET mood = ? WHERE id = ?", (new_mood, identity_id))
        self._conn.commit()
        return new_mood

    def get_language(self, identity_id: int) -> str | None:
        row = self._conn.execute("SELECT language FROM identities WHERE id = ?", (identity_id,)).fetchone()
        return row["language"] if row else None

    def set_language(self, identity_id: int, lang: str | None):
        self._conn.execute("UPDATE identities SET language = ? WHERE id = ?", (lang, identity_id))
        self._conn.commit()

    def get_last_routine(self, identity_id: int) -> str | None:
        row = self._conn.execute("SELECT last_routine FROM identities WHERE id = ?", (identity_id,)).fetchone()
        return row["last_routine"] if row else None

    def set_last_routine(self, identity_id: int, marker: str):
        self._conn.execute("UPDATE identities SET last_routine = ? WHERE id = ?", (marker, identity_id))
        self._conn.commit()

    # -- messages -------------------------------------------------------

    def add_message(self, identity_id: int, role: str, content: str):
        self._conn.execute(
            "INSERT INTO messages (identity_id, role, content) VALUES (?, ?, ?)",
            (identity_id, role, content),
        )
        self._conn.commit()

    def get_history(self, identity_id: int, limit: int = 30) -> list[dict]:
        rows = self._conn.execute(
            "SELECT role, content FROM messages WHERE identity_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (identity_id, limit),
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    # -- facts ------------------------------------------------------------

    def add_fact(self, identity_id: int, fact: str):
        self._conn.execute(
            "INSERT INTO facts (identity_id, fact) VALUES (?, ?)", (identity_id, fact)
        )
        self._conn.commit()

    def get_facts(self, identity_id: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT fact FROM facts WHERE identity_id = ? ORDER BY id", (identity_id,)
        ).fetchall()
        return [row["fact"] for row in rows]

    # -- reminders ----------------------------------------------------------

    def add_reminder(self, message: str, due_at: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO reminders (message, due_at) VALUES (?, ?)", (message, due_at)
        )
        self._conn.commit()
        return cur.lastrowid

    def get_pending_reminders(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, message, due_at FROM reminders WHERE fired = 0 ORDER BY due_at"
        ).fetchall()
        return [{"id": row["id"], "message": row["message"], "due_at": row["due_at"]} for row in rows]

    def mark_reminder_fired(self, reminder_id: int):
        self._conn.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))
        self._conn.commit()

    # -- alarms ---------------------------------------------------------

    def add_alarm(self, hour: int, minute: int, recurring: bool, message: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO alarms (hour, minute, recurring, message) VALUES (?, ?, ?, ?)",
            (hour, minute, int(recurring), message),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_active_alarms(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, hour, minute, recurring, message, last_fired_date "
            "FROM alarms WHERE enabled = 1"
        ).fetchall()
        return [
            {
                "id": row["id"], "hour": row["hour"], "minute": row["minute"],
                "recurring": bool(row["recurring"]), "message": row["message"],
                "last_fired_date": row["last_fired_date"],
            }
            for row in rows
        ]

    def mark_alarm_fired(self, alarm_id: int, fired_date: str):
        self._conn.execute("UPDATE alarms SET last_fired_date = ? WHERE id = ?", (fired_date, alarm_id))
        self._conn.commit()

    def disable_alarm(self, alarm_id: int):
        self._conn.execute("UPDATE alarms SET enabled = 0 WHERE id = ?", (alarm_id,))
        self._conn.commit()
