"""Real Docker incident/rollback drill in isolated temporary volumes. No API key.

The approval in this automated drill is explicitly simulated. It verifies the
gate; a person must still approve the presentation candidate in the application.
"""
import argparse
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import release_manager as manager
import release_registry as registry

PROFILE = {"situation": "Développeur junior", "skills": "Python et SQL", "hours": 8, "horizon": 6}
ACTOR = "Test automatique (approbation simulée)"


def wait_run(client, run_id):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        run = client.get("/api/runs/" + run_id).json()
        if run["status"] != "running":
            return run
        time.sleep(.3)
    raise AssertionError("Le scénario n'a pas terminé dans le délai attendu.")


def request(client, path, payload):
    result = client.post(path, json=payload)
    result.raise_for_status()
    return result.json()


def rehearse(stable_image, incident_image):
    report = {"date_utc": None, "approval": "simulée par le test, pas une validation humaine", "api_calls": False, "checks": []}
    saved = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="cap-avenir-drill-") as temporary:
        folder = Path(temporary)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        os.environ.update(CAP_AVENIR_RUNTIME_DIR=str(folder / "runtime"), CAP_AVENIR_DATA_DIR=str(folder / "data"),
                          CAP_AVENIR_PORT=str(port), CAP_AVENIR_CONTAINER="cap-avenir-drill-" + uuid4().hex[:8], CAP_AVENIR_WITH_SECRETS="0")
        config = manager.settings()
        try:
            candidates = []
            for image in [stable_image, incident_image]:
                info = manager.image_info(image)
                labels = info["Config"]["Labels"]
                candidates.append(registry.register(labels["org.opencontainers.image.version"], image, info["Id"],
                                                     labels.get("org.opencontainers.image.revision", "local"), labels.get("com.cap-avenir.demo-fault") == "1"))
            stable, incident = candidates
            assert not stable["demo_fault"] and incident["demo_fault"]
            manager.deploy(stable["version"], ACTOR, bootstrap=True)
            report["checks"].append("Conteneur stable démarré et version vérifiée")
            try:
                manager.deploy(incident["version"], ACTOR)
            except ValueError:
                report["checks"].append("Déploiement non approuvé refusé avant tout remplacement")
            else:
                raise AssertionError("La candidate non approuvée a été déployée.")
            with httpx.Client(base_url=config["url"], timeout=25) as client:
                approved = request(client, f"/api/ops/releases/{incident['version']}/review", {"actor": ACTOR, "decision": "approved", "agent_card_reviewed": True, "reason": "Contrôle automatisé du mécanisme"})
                assert approved["image_id"] == incident["image_id"]
            manager.deploy(incident["version"], ACTOR)
            report["checks"].append("Image exacte déployée après approbation simulée")
            with httpx.Client(base_url=config["url"], timeout=25) as client:
                assert client.get("/api/health").json()["paused"]
                request(client, "/api/ops/pause", {"actor": ACTOR, "paused": False})
                run_id = request(client, "/api/runs", {"profile": PROFILE, "mode": "demo"})["id"]
                run = wait_run(client, run_id)
                assert run["status"] == "partial"
                assert any(a["code"] == "error" for a in run["alerts"])
                report["incident_correlation_id"] = run_id
                report["checks"].append("Panne de fournisseur simulée détectée et corrélée dans le conteneur")
                active_id = request(client, "/api/runs", {"profile": PROFILE, "mode": "demo"})["id"]
                time.sleep(.3)
                request(client, "/api/ops/pause", {"actor": ACTOR, "paused": True, "reason": "Exercice kill-switch"})
                cancelled = client.get("/api/runs/" + active_id).json()
                assert cancelled["status"] == "cancelled"
                assert all(step["status"] != "running" for step in cancelled["steps"])
                assert not any(e["agent"] == "supervisor" and e["type"] == "agent_started" for e in cancelled["events"])
                assert client.post("/api/runs", json={"profile": PROFILE, "mode": "demo"}).status_code == 503
                report["cancelled_correlation_id"] = active_id
                report["checks"].append("Kill-switch : tâches annulées, superviseur non lancé, nouvelles missions bloquées")
            result = manager.rollback(ACTOR)
            assert result["version"] == stable["version"]
            with httpx.Client(base_url=config["url"], timeout=25) as client:
                health = client.get("/api/health").json()
                assert health["paused"] and not health["demo_fault"]
                assert client.get("/api/runs/" + run_id).json()["status"] == "partial"
                report["checks"].append("Rollback réel vers l'image stable ; pause et historique conservés")
                request(client, "/api/ops/pause", {"actor": ACTOR, "paused": False, "reason": "Reprise après vérification"})
                restored_id = request(client, "/api/runs", {"profile": PROFILE, "mode": "demo"})["id"]
                assert wait_run(client, restored_id)["status"] == "completed"
                report["checks"].append("Reprise explicite puis mission complète réussie sur la version stable")
                report["operations"] = client.get("/api/ops").json()
            assert len(list((folder / "data" / "backups").glob("*.db"))) >= 2
            report["checks"].append("Sauvegardes SQLite créées avant les deux remplacements")
            from datetime import datetime, timezone
            report["date_utc"] = datetime.now(timezone.utc).isoformat()
            report["passed"] = True
        finally:
            try:
                manager.remove_owned(config)
            finally:
                os.environ.clear()
                os.environ.update(saved)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    stable, incident = manager.demo_versions()
    parser.add_argument("--stable", default="cap-avenir:" + stable)
    parser.add_argument("--incident", default="cap-avenir:" + incident)
    parser.add_argument("--output", default="livrables/exercice-docker.json")
    args = parser.parse_args()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = rehearse(args.stable, args.incident)
    except Exception:
        import traceback
        destination.write_text(json.dumps({"passed": False, "api_calls": False, "error": traceback.format_exc()}, indent=2), encoding="utf-8")
        raise
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "checks": len(result["checks"]), "report": str(destination), "api_calls": False}))
