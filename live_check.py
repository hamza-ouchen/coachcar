"""One complete paid integration check against the running local application."""
import json
import time
from pathlib import Path

import httpx

PROFILE = {"situation": "Développeur web junior", "skills": "JavaScript, Python, SQL débutant", "objective": "compare", "market": "Maroc", "remote": True, "hours": 8, "horizon": 6, "interests": "Automatisation et analyse de données"}


with httpx.Client(base_url="http://127.0.0.1:8000", timeout=20) as client:
    response = client.post("/api/runs", json={"profile": PROFILE, "mode": "live"})
    response.raise_for_status()
    run_id = response.json()["id"]
    deadline = time.monotonic() + 210
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] != "running":
            break
        time.sleep(2)
    assert run["status"] == "completed", {"status": run["status"], "error": run.get("error"), "steps": [{"agent": s["agent"], "error": s["error"]} for s in run["steps"]]}
    assert run["result"]["recommendation"]
    assert len(run["result"].get("roadmap", [])) == 3
    assert all(s["dossier"].get("web_verified") for s in run["steps"] if s["agent"] != "supervisor")
    assert run["cost_complete"]
    Path("livrables").mkdir(exist_ok=True)
    Path("livrables/exemple-analyse-reelle.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("livrables/workflow.json").write_text(json.dumps(client.get("/api/workflow/export").json(), ensure_ascii=False, indent=2), encoding="utf-8")
    Path("livrables/executions.csv").write_bytes(client.get("/api/exports/runs.csv").content)
    print(json.dumps({"ok": True, "correlation_id": run_id, "duration_ms": run["duration_ms"], "cost": run["cost"], "tokens": run["tokens"], "sources": sum(len(s["dossier"].get("sources", [])) for s in run["steps"]), "steps": len(run["steps"])}))
