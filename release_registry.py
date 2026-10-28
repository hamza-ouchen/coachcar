"""Local classroom release registry shared by the app and host-side scripts.

Only one operator should change releases at a time. No Docker socket is exposed
to the application; the host script verifies the approved immutable image ID.
"""
import json
import os
import re
import threading
from pathlib import Path

import storage

LOCK = threading.RLock()
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def runtime_dir():
    return Path(os.getenv("CAP_AVENIR_RUNTIME_DIR", "runtime")).resolve()


def read():
    path = runtime_dir() / "releases.json"
    with LOCK:
        if not path.exists():
            return {"candidates": [], "deployments": []}
        return json.loads(path.read_text(encoding="utf-8"))


def save(data):
    folder = runtime_dir()
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / "releases.next.json"
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(folder / "releases.json")


def register(version, image, image_id, commit="local", demo_fault=False):
    if not SEMVER.fullmatch(version):
        raise ValueError("Version SemVer invalide, exemple : 1.1.0.")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Identifiant d'image Docker invalide.")
    with LOCK:
        data = read()
        existing = next((c for c in data["candidates"] if c["version"] == version), None)
        if existing:
            if existing["image_id"] != image_id:
                raise ValueError("Cette version désigne déjà une autre image. Choisissez une nouvelle version.")
            return existing
        candidate = {"version": version, "image": image, "image_id": image_id, "commit": commit,
                     "demo_fault": bool(demo_fault), "status": "pending", "created_at": storage.now(),
                     "reviewer": None, "reviewed_at": None, "note": ""}
        data["candidates"].append(candidate)
        save(data)
        return candidate


def review(version, decision, actor, note="", card_reviewed=False):
    if decision not in ("approved", "rejected") or len(actor.strip()) < 2:
        raise ValueError("Une décision et un nom de validateur sont requis.")
    if decision == "approved" and not card_reviewed:
        raise ValueError("Confirmez la lecture de l'Agent Card avant d'approuver.")
    with LOCK:
        data = read()
        candidate = next((c for c in data["candidates"] if c["version"] == version), None)
        if not candidate:
            raise ValueError("Version candidate introuvable.")
        if candidate["status"] != "pending":
            raise ValueError("Cette candidate a déjà été revue.")
        candidate.update(status=decision, reviewer=actor.strip(), reviewed_at=storage.now(), note=note, agent_card_reviewed=bool(card_reviewed))
        save(data)
        return candidate


def approved(version, image_id):
    candidate = next((c for c in read()["candidates"] if c["version"] == version), None)
    if not candidate or candidate["status"] != "approved" or candidate["image_id"] != image_id:
        raise ValueError("Déploiement refusé : cette image exacte n'a pas été approuvée.")
    return candidate


def record_deployment(version, image, image_id, operator, kind="deploy"):
    with LOCK:
        data = read()
        record = {"version": version, "image": image, "image_id": image_id, "operator": operator,
                  "kind": kind, "at": storage.now()}
        data["deployments"].append(record)
        save(data)
        return record
