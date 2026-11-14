"""SQLite storage for the public site: users, places, private additions, submissions, daily usage.

One file (DB_PATH, default <data dir>/site.db). Every call opens its own short connection: the site is small,
SQLite in WAL mode handles a few writers per second easily, and nothing is shared between threads.
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  google_sub TEXT UNIQUE NOT NULL,
  email TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  picture TEXT NOT NULL DEFAULT '',
  is_admin INTEGER NOT NULL DEFAULT 0,
  banned INTEGER NOT NULL DEFAULT 0,
  session_v INTEGER NOT NULL DEFAULT 0,
  created REAL NOT NULL,
  last_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS places (
  slug TEXT PRIMARY KEY,
  osm_type TEXT, osm_id INTEGER,
  name TEXT NOT NULL, name_local TEXT, display_name TEXT NOT NULL DEFAULT '',
  lang TEXT NOT NULL, size TEXT NOT NULL, radius REAL NOT NULL,
  lat REAL NOT NULL, lon REAL NOT NULL,
  status TEXT NOT NULL,            -- queued | fetching | rendering | ready | failed
  error TEXT,
  hidden INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created REAL NOT NULL, updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS places_osm ON places(osm_type, osm_id, size, lang);
CREATE INDEX IF NOT EXISTS places_created ON places(created);
CREATE TABLE IF NOT EXISTS docs (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  slug TEXT NOT NULL REFERENCES places(slug) ON DELETE CASCADE,
  doc TEXT NOT NULL,
  updated REAL NOT NULL,
  PRIMARY KEY (user_id, slug)
);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL REFERENCES places(slug) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,              -- place | path | note
  item_id TEXT NOT NULL,           -- id of the item in the user's own document
  item TEXT NOT NULL,              -- JSON copy of the item when submitted
  status TEXT NOT NULL,            -- pending | approved | rejected | withdrawn
  public_id TEXT,                  -- id in the public custom.json once approved
  admin_note TEXT,
  created REAL NOT NULL, reviewed REAL, reviewed_by INTEGER
);
CREATE INDEX IF NOT EXISTS subs_status ON submissions(status, created);
CREATE INDEX IF NOT EXISTS subs_user ON submissions(user_id, slug);
CREATE TABLE IF NOT EXISTS user_fonts (  -- a visitor's own font choices: {lang: {theme: {role: family}}}
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  slug TEXT NOT NULL REFERENCES places(slug) ON DELETE CASCADE,
  prefs TEXT NOT NULL,
  PRIMARY KEY (user_id, slug)
);
CREATE TABLE IF NOT EXISTS usage (
  key TEXT NOT NULL,               -- 'u<id>' or 'ip:<addr>'
  day TEXT NOT NULL,
  action TEXT NOT NULL,
  n INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (key, day, action)
);
"""


def init(path):
    global DB_PATH
    DB_PATH = Path(path)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
        if "session_v" not in cols:  # databases made before sign-out invalidated sessions
            c.execute("ALTER TABLE users ADD COLUMN session_v INTEGER NOT NULL DEFAULT 0")


@contextmanager
def connect():
    c = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=15000")
    try:
        yield c
    finally:
        c.close()


def one(sql, *args):
    with connect() as c:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None


def all_(sql, *args):
    with connect() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def run(sql, *args):
    with connect() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid if cur.lastrowid else cur.rowcount


def today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def used(key, action):
    r = one("SELECT n FROM usage WHERE key=? AND day=? AND action=?", key, today(), action)
    return r["n"] if r else 0


def take(key, action, limit):
    """Count one use of `action` today; False (and nothing counted) when the limit is reached."""
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        r = c.execute("SELECT n FROM usage WHERE key=? AND day=? AND action=?", (key, today(), action)).fetchone()
        n = r["n"] if r else 0
        if limit is not None and n >= limit:
            c.execute("ROLLBACK")
            return False
        c.execute("INSERT INTO usage(key, day, action, n) VALUES(?,?,?,1) "
                  "ON CONFLICT(key, day, action) DO UPDATE SET n = n + 1", (key, today(), action))
        c.execute("COMMIT")
        return True


def give_back(key, action):
    run("UPDATE usage SET n = MAX(0, n - 1) WHERE key=? AND day=? AND action=?", key, today(), action)


def prune_usage(keep_days=8):
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - keep_days * 86400))
    run("DELETE FROM usage WHERE day < ?", cutoff)


# ---------------------------------------------------------------- users

def upsert_google_user(sub, email, name, picture, admin_emails):
    now = time.time()
    is_admin = 1 if email.lower() in admin_emails else 0
    u = one("SELECT * FROM users WHERE google_sub=?", sub)
    if u:
        run("UPDATE users SET email=?, name=?, picture=?, last_seen=?, is_admin=MAX(is_admin, ?) WHERE id=?",
            email, name, picture, now, is_admin, u["id"])
    else:
        run("INSERT INTO users(google_sub, email, name, picture, is_admin, created, last_seen) VALUES(?,?,?,?,?,?,?)",
            sub, email, name, picture, is_admin, now, now)
    return one("SELECT * FROM users WHERE google_sub=?", sub)


def user(uid):
    return one("SELECT * FROM users WHERE id=?", uid) if uid else None


# ---------------------------------------------------------------- docs

def get_doc(uid, slug):
    r = one("SELECT doc FROM docs WHERE user_id=? AND slug=?", uid, slug)
    doc = json.loads(r["doc"]) if r else {}
    for k in ("places", "paths", "notes"):
        if not isinstance(doc.get(k), list):
            doc[k] = []
    return doc


def put_doc(uid, slug, doc):
    run("INSERT INTO docs(user_id, slug, doc, updated) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id, slug) DO UPDATE SET doc=excluded.doc, updated=excluded.updated",
        uid, slug, json.dumps(doc, ensure_ascii=False), time.time())


# ---------------------------------------------------------------- font choices

def get_fonts(uid, slug):
    r = one("SELECT prefs FROM user_fonts WHERE user_id=? AND slug=?", uid, slug)
    try:
        prefs = json.loads(r["prefs"]) if r else {}
    except ValueError:
        prefs = {}
    return prefs if isinstance(prefs, dict) else {}


def put_fonts(uid, slug, prefs):
    if prefs:
        run("INSERT INTO user_fonts(user_id, slug, prefs) VALUES(?,?,?) "
            "ON CONFLICT(user_id, slug) DO UPDATE SET prefs=excluded.prefs", uid, slug, json.dumps(prefs, ensure_ascii=False))
    else:
        run("DELETE FROM user_fonts WHERE user_id=? AND slug=?", uid, slug)


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default
