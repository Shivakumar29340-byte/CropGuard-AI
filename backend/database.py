
"""SQLite helpers: connection handling and table creation."""

import sqlite3
from flask import current_app, g


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'farmer'
                  CHECK (role IN ('farmer','admin')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL,
    used_at    TEXT
);

CREATE TABLE IF NOT EXISTS detections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    crop          TEXT    NOT NULL,
    disease       TEXT    NOT NULL,
    confidence    REAL    NOT NULL CHECK (
        confidence >= 0 AND confidence <= 1
    ),
    notes         TEXT    NOT NULL DEFAULT '',
    source        TEXT    NOT NULL DEFAULT 'manual',
    record_hash   TEXT    NOT NULL,
    blockchain_tx TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_detections_user
ON detections(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sessions_user
ON sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_reset_tokens_user
ON password_reset_tokens(user_id);
"""


def get_db():
    """Get one SQLite connection per request."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            timeout=30
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


def close_db(_error=None):
    """Close the database connection after the request."""
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    """Create database tables if they do not already exist."""
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


def init_app(app):
    """Register database cleanup and initialize tables."""
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()
