CREATE TABLE IF NOT EXISTS identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'person',
    mood REAL NOT NULL DEFAULT 0,
    language TEXT,  -- fixed language code (e.g. "en"), NULL = auto-detect
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    fact TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    due_at TEXT NOT NULL,
    fired INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alarms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour INTEGER NOT NULL,
    minute INTEGER NOT NULL,
    recurring INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT 'Sveglia!',
    enabled INTEGER NOT NULL DEFAULT 1,
    last_fired_date TEXT  -- "YYYY-MM-DD", avoids re-firing the same day after a restart
);

CREATE INDEX IF NOT EXISTS idx_messages_identity ON messages(identity_id, id);
CREATE INDEX IF NOT EXISTS idx_facts_identity ON facts(identity_id);
CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders(fired, due_at);
CREATE INDEX IF NOT EXISTS idx_alarms_enabled ON alarms(enabled);
