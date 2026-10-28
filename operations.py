"""Small persistent operations layer, separate from career recommendations."""
import os
from pathlib import Path

import release_registry
import storage
import database

ROOT = Path(__file__).resolve().parent


def version():
    return os.getenv("CAP_AVENIR_VERSION") or (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def image_fault():
    return os.getenv("CAP_AVENIR_DEMO_FAULT", "0") == "1"


def get_state():
    with storage.connect() as conn:
        row = conn.execute("SELECT * FROM operation_control WHERE id=1").fetchone()
    return dict(row)


def audit(action, actor, details=None):
    import json
    with storage.connect() as conn:
        conn.execute("INSERT INTO operation_audit(action,actor,created_at,details) VALUES(?,?,?,?)",
                     (action, actor, storage.now(), json.dumps(details or {}, ensure_ascii=False)))


def change_pause(paused, actor, reason):
    with storage.connect() as conn:
        conn.execute("UPDATE operation_control SET paused=?, actor=?, reason=?, updated_at=? WHERE id=1",
                     (int(paused), actor, reason, storage.now()))
    audit("kill_switch_on" if paused else "kill_switch_off", actor, {"reason": reason})


def change_incident(incident, actor):
    with storage.connect() as conn:
        conn.execute("UPDATE operation_control SET incident=?, updated_at=? WHERE id=1", (incident, storage.now()))
    audit("incident_changed", actor, {"incident": incident, "scope": "demo_only"})


def snapshot():
    state = get_state()
    with storage.connect() as conn:
        logs = [storage.decode(row, ["details"]) for row in conn.execute("SELECT * FROM operation_audit ORDER BY id DESC LIMIT 100")]
    return {"version": version(), "commit": os.getenv("RENDER_GIT_COMMIT") or os.getenv("CAP_AVENIR_COMMIT", "local"), "paused": bool(state["paused"]),
            "reason": state["reason"], "actor": state["actor"], "updated_at": state["updated_at"],
            "incident": state["incident"], "image_fault": image_fault(), "audit": logs,
            "releases": release_registry.read(), "active_runs": sum(r["status"] == "running" for r in storage.list_runs()),
            "platform": "render" if os.getenv("RENDER") else "local",
            "database": "postgresql" if database.postgres_url() else "sqlite",
            "render_dashboard_url": "https://dashboard.render.com/web/" + os.environ["RENDER_SERVICE_ID"] if os.getenv("RENDER_SERVICE_ID") else "https://dashboard.render.com/",
            "approval_scope": "Accès protégé par mot de passe sur Render ; nom du validateur déclaré dans l'application." if os.getenv("RENDER") else "Validation nominative locale pour TP, sans authentification d'identité."}


def record_render_deployment():
    commit = os.getenv("RENDER_GIT_COMMIT")
    if not os.getenv("RENDER") or not commit:
        return
    registry = release_registry.read()
    if not registry["deployments"] or registry["deployments"][-1]["image_id"] != "git:" + commit:
        release_registry.record_deployment(version(), "Render Docker", "git:" + commit, "Render", "render")
