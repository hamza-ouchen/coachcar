"""Small SQLite store. All writes use short, independent transactions."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("CAP_AVENIR_DB", "data/cap_avenir.db"))


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, finished_at TEXT,
          status TEXT NOT NULL, mode TEXT NOT NULL, profile TEXT NOT NULL,
          result TEXT, duration_ms REAL, error TEXT, model TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS steps (
          id TEXT PRIMARY KEY, run_id TEXT NOT NULL, agent TEXT NOT NULL,
          status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
          duration_ms REAL, prompt_tokens INTEGER, completion_tokens INTEGER,
          cost REAL, dossier TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          step_id TEXT, agent TEXT, type TEXT NOT NULL, timestamp TEXT NOT NULL,
          elapsed_ms REAL NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS events_run ON events(run_id, id);
        CREATE TABLE IF NOT EXISTS alerts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          agent TEXT NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL,
          created_at TEXT NOT NULL, UNIQUE(run_id, agent, code));
        CREATE TABLE IF NOT EXISTS operation_control (
          id INTEGER PRIMARY KEY CHECK(id=1), paused INTEGER NOT NULL DEFAULT 0,
          incident TEXT NOT NULL DEFAULT 'normal', reason TEXT NOT NULL DEFAULT '',
          actor TEXT NOT NULL DEFAULT '', updated_at TEXT);
        INSERT OR IGNORE INTO operation_control(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS operation_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
          actor TEXT NOT NULL, created_at TEXT NOT NULL, details TEXT NOT NULL);
        """)
        # An in-process task cannot survive a server restart.
        conn.execute("UPDATE runs SET status='interrupted', finished_at=?, error=? WHERE status='running'",
                     (now(), "Exécution interrompue par le redémarrage du serveur.",))
        conn.execute("UPDATE steps SET status='interrupted', finished_at=? WHERE status='running'", (now(),))


def create_run(run_id, profile, mode, model):
    with connect() as conn:
        conn.execute("INSERT INTO runs(id,created_at,status,mode,profile,model) VALUES(?,?,'running',?,?,?)",
                     (run_id, now(), mode, json.dumps(profile, ensure_ascii=False), model))


def start_step(step_id, run_id, agent):
    with connect() as conn:
        conn.execute("INSERT INTO steps(id,run_id,agent,status,started_at) VALUES(?,?,?,'running',?)",
                     (step_id, run_id, agent, now()))


def finish_step(step_id, status, duration, dossier=None, usage=None, error=None):
    usage = usage or {}
    with connect() as conn:
        conn.execute("""UPDATE steps SET status=?, finished_at=?, duration_ms=?, prompt_tokens=?,
          completion_tokens=?, cost=?, dossier=?, error=? WHERE id=?""",
                     (status, now(), duration, usage.get("prompt_tokens"), usage.get("completion_tokens"),
                      usage.get("cost"), json.dumps(dossier, ensure_ascii=False) if dossier else None, error, step_id))


def finish_run(run_id, status, duration, result=None, error=None):
    with connect() as conn:
        conn.execute("UPDATE runs SET status=?, finished_at=?, duration_ms=?, result=?, error=? WHERE id=?",
                     (status, now(), duration, json.dumps(result, ensure_ascii=False) if result else None, error, run_id))


def emit(run_id, event_type, elapsed_ms, payload=None, agent=None, step_id=None):
    with connect() as conn:
        cur = conn.execute("INSERT INTO events(run_id,step_id,agent,type,timestamp,elapsed_ms,payload) VALUES(?,?,?,?,?,?,?)",
                           (run_id, step_id, agent, event_type, now(), elapsed_ms, json.dumps(payload or {}, ensure_ascii=False)))
        return cur.lastrowid


def add_alert(run_id, agent, code, message):
    with connect() as conn:
        cur = conn.execute("INSERT OR IGNORE INTO alerts(run_id,agent,code,message,created_at) VALUES(?,?,?,?,?)",
                           (run_id, agent or "workflow", code, message, now()))
        return cur.rowcount > 0


def decode(row, fields):
    item = dict(row)
    for key in fields:
        if item.get(key):
            item[key] = json.loads(item[key])
    return item


def events(run_id, after=0):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id", (run_id, after)).fetchall()
    return [decode(row, ["payload"]) for row in rows]


def get_run(run_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        item = decode(row, ["profile", "result"])
        item["steps"] = [decode(r, ["dossier"]) for r in conn.execute("SELECT * FROM steps WHERE run_id=? ORDER BY started_at", (run_id,))]
        item["alerts"] = [dict(r) for r in conn.execute("SELECT * FROM alerts WHERE run_id=? ORDER BY id", (run_id,))]
    item["correlation_id"] = item["id"]
    costs = [s["cost"] for s in item["steps"] if s["cost"] is not None]
    item["cost"] = sum(costs) if costs else None
    item["cost_complete"] = bool(item["steps"]) and all(s["cost"] is not None for s in item["steps"])
    item["tokens"] = sum((s["prompt_tokens"] or 0) + (s["completion_tokens"] or 0) for s in item["steps"])
    return item


def list_runs(mode=None):
    with connect() as conn:
        if mode:
            ids = [r[0] for r in conn.execute("SELECT id FROM runs WHERE mode=? ORDER BY created_at DESC", (mode,))]
        else:
            ids = [r[0] for r in conn.execute("SELECT id FROM runs ORDER BY created_at DESC")]
    return [get_run(run_id) for run_id in ids]


def metrics(mode="live"):
    runs = list_runs(mode)
    terminal = [r for r in runs if r["status"] != "running"]
    successful = [r for r in terminal if r["status"] == "completed"]
    projected = [r for r in successful if r["cost_complete"]]
    known = [r["cost"] for r in runs if r["cost"] is not None]
    agents = []
    for agent in ["evolution", "reconversion", "supervisor"]:
        steps = [s for r in runs for s in r["steps"] if s["agent"] == agent]
        done = [s for s in steps if s["duration_ms"] is not None]
        agents.append({"agent": agent, "count": len(steps),
                       "avg_ms": sum(s["duration_ms"] for s in done) / len(done) if done else 0,
                       "tokens": sum((s["prompt_tokens"] or 0) + (s["completion_tokens"] or 0) for s in steps),
                       "cost": sum(s["cost"] for s in steps if s["cost"] is not None) if any(s["cost"] is not None for s in steps) else None})
    durations = [r["duration_ms"] for r in terminal if r["duration_ms"] is not None]
    return {"mode": mode, "total": len(runs), "avg_ms": sum(durations) / len(durations) if durations else 0,
            "success_rate": 100 * len(successful) / len(terminal) if terminal else None,
            "cost": sum(known) if known else None,
            "unknown_cost_runs": sum(not r["cost_complete"] for r in runs),
            "projection_average": sum(r["cost"] for r in projected) / len(projected) if projected else None,
            "projection_sample": len(projected), "agents": agents,
            "alerts": [dict(a, mode=r["mode"]) for r in runs for a in r["alerts"]]}
