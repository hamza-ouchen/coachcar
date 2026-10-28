"""Host-side Docker operations. The web application never controls Docker.

prepare -> operator approval in the UI -> deploy -> rollback if needed.
The first bootstrap installs a known normal baseline; it is not a human review.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import release_registry as registry


def demo_versions():
    stable = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    major, minor, patch = stable.split(".")
    return stable, f"{major}.{minor}.{int(patch) + 1}-incident.1"


def docker(*arguments, capture=True, check=True):
    result = subprocess.run(["docker", *arguments], cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                            stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)
    if check and result.returncode:
        raise RuntimeError((result.stderr or "La commande Docker a échoué.").strip()[-1800:])
    return result


def image_info(image):
    return json.loads(docker("image", "inspect", image).stdout)[0]


def prepare(version, fault=False, image=None):
    if not registry.SEMVER.fullmatch(version):
        raise ValueError("Version SemVer invalide.")
    image = image or "cap-avenir:" + version
    existing = next((c for c in registry.read()["candidates"] if c["version"] == version), None)
    if existing:
        info = image_info(existing["image"])
        if info["Id"] != existing["image_id"]:
            raise ValueError("L'image enregistrée a changé. Utilisez une nouvelle version.")
        return existing
    if image.startswith("ghcr.io/"):
        docker("pull", image, capture=False)
        info = image_info(image)
        fault = (info["Config"].get("Labels") or {}).get("com.cap-avenir.demo-fault") == "1"
    else:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "local"
        docker("build", "--build-arg", "APP_VERSION=" + version, "--build-arg", "APP_COMMIT=" + commit,
               "--build-arg", "DEMO_FAULT=" + ("1" if fault else "0"), "-t", image, ".", capture=False)
        info = image_info(image)
    labels = info["Config"].get("Labels") or {}
    if labels.get("org.opencontainers.image.version") != version:
        raise ValueError("La version annoncée par l'image ne correspond pas à la candidate.")
    return registry.register(version, image, info["Id"], labels.get("org.opencontainers.image.revision", "local"), fault)


def settings():
    runtime = registry.runtime_dir()
    data = Path(os.getenv("CAP_AVENIR_DATA_DIR", str(ROOT / "data"))).resolve()
    port = int(os.getenv("CAP_AVENIR_PORT", "8787"))
    return {"runtime": runtime, "data": data, "port": port,
            "name": os.getenv("CAP_AVENIR_CONTAINER", "cap-avenir-demo"),
            "owner": hashlib.sha256(str(runtime).encode()).hexdigest()[:16],
            "url": f"http://127.0.0.1:{port}"}


def state_path():
    return registry.runtime_dir() / "deployment.json"


def current_deployment():
    path = state_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def remove_owned(config):
    result = docker("container", "inspect", config["name"], check=False)
    if result.returncode:
        return
    container = json.loads(result.stdout)[0]
    if (container["Config"].get("Labels") or {}).get("com.cap-avenir.owner") != config["owner"]:
        raise ValueError("Ce nom appartient à un autre conteneur. Aucun arrêt n'a été effectué.")
    docker("stop", "--time", "10", container["Id"])
    docker("rm", container["Id"])


def start_image(candidate, config):
    config["data"].mkdir(parents=True, exist_ok=True)
    config["runtime"].mkdir(parents=True, exist_ok=True)
    args = ["run", "-d", "--restart", "unless-stopped", "--name", config["name"], "--label", "com.cap-avenir.owner=" + config["owner"],
            "--publish", f"127.0.0.1:{config['port']}:8000",
            "--mount", f"type=bind,source={config['data']},target=/app/data",
            "--mount", f"type=bind,source={config['runtime']},target=/app/runtime",
            "--env", "CAP_AVENIR_RUNTIME_DIR=/app/runtime", "--env", "CAP_AVENIR_DB=/app/data/cap_avenir.db"]
    # On Linux, keep bind-mounted files owned by the operator/CI runner.
    # Otherwise root-owned backup directories cannot be cleaned up by the runner.
    if hasattr(os, "getuid") and os.getuid() != 0:
        args += ["--user", f"{os.getuid()}:{os.getgid()}", "--env", "HOME=/tmp"]
    secret_file = ROOT / ".env"
    if os.getenv("CAP_AVENIR_WITH_SECRETS", "1") == "1" and secret_file.exists():
        args += ["--env-file", str(secret_file)]
    else:
        args += ["--env", "OPENROUTER_API_KEY="]
    # Run the exact approved image ID, even if its friendly tag changes later.
    docker(*args, candidate["image_id"])
    deadline = time.monotonic() + 60
    last_error = "Serveur indisponible"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(config["url"] + "/api/health", timeout=3)
            response.raise_for_status()
            health = response.json()
            if health.get("version") == candidate["version"] and health.get("application") == "cap-avenir":
                return health
        except (httpx.HTTPError, ValueError) as exc:
            last_error = type(exc).__name__
        time.sleep(1)
    raise RuntimeError("Le nouveau conteneur n'est pas devenu disponible : " + last_error)


def deploy(version, actor, bootstrap=False, rollback=False):
    config = settings()
    previous = current_deployment()
    candidate = next((c for c in registry.read()["candidates"] if c["version"] == version), None)
    if not candidate:
        raise ValueError("Candidate absente. Préparez d'abord l'image.")
    info = image_info(candidate["image_id"])
    if (info["Config"].get("Labels") or {}).get("org.opencontainers.image.version") != version:
        raise ValueError("L'image exacte ne correspond pas à la version demandée.")
    if bootstrap:
        if previous or registry.read()["deployments"] or candidate["demo_fault"]:
            raise ValueError("Bootstrap réservé à la toute première installation d'une image normale.")
    elif rollback:
        if not any(d["image_id"] == candidate["image_id"] for d in registry.read()["deployments"]):
            raise ValueError("Rollback limité à une image déjà déployée.")
    else:
        registry.approved(version, info["Id"])
    if previous and previous["image_id"] == candidate["image_id"]:
        return {"version": version, "url": config["url"], "unchanged": True}
    if previous:
        # Keep the pause in SQLite across replacement. Reopening is explicit.
        with httpx.Client(base_url=config["url"], timeout=20) as client:
            pause = client.post("/api/ops/pause", json={"paused": True, "actor": actor, "reason": "Préparation du remplacement de version"})
            pause.raise_for_status()
            backup = client.post("/api/ops/backup", json={"actor": actor, "reason": "Sauvegarde avant remplacement"})
            backup.raise_for_status()
    remove_owned(config)
    try:
        health = start_image(candidate, config)
    except Exception:
        # Preserve service availability if the replacement fails its health check.
        remove_owned(config)
        if previous:
            start_image(previous, config)
            registry.record_deployment(previous["version"], previous["image"], previous["image_id"], actor, "automatic_rollback")
        raise
    kind = "bootstrap" if bootstrap else "rollback" if rollback else "deploy"
    registry.record_deployment(version, candidate["image"], candidate["image_id"], actor, kind)
    state_path().write_text(json.dumps({k: candidate[k] for k in ("version", "image", "image_id")}, indent=2), encoding="utf-8")
    return {"version": version, "url": config["url"], "paused": health["paused"], "kind": kind}


def rollback(actor):
    current = current_deployment()
    if not current:
        raise ValueError("Aucune version gérée n'est actuellement déployée.")
    previous = next((d for d in reversed(registry.read()["deployments"]) if d["image_id"] != current["image_id"]), None)
    if not previous:
        raise ValueError("Aucune version précédente disponible.")
    return deploy(previous["version"], actor, rollback=True)


def restart_existing(actor):
    config = settings()
    current = current_deployment()
    if not current:
        raise ValueError("Aucune installation existante à relancer.")
    found = docker("container", "inspect", config["name"], check=False)
    if found.returncode == 0:
        container = json.loads(found.stdout)[0]
        if (container["Config"].get("Labels") or {}).get("com.cap-avenir.owner") != config["owner"]:
            raise ValueError("Ce conteneur n'appartient pas à cette installation.")
        if container["State"]["Running"]:
            response = httpx.get(config["url"] + "/api/health", timeout=5)
            response.raise_for_status()
            if response.json()["version"] != current["version"]:
                raise ValueError("La version active ne correspond pas au registre de déploiement.")
            return {"version": current["version"], "url": config["url"], "already_running": True}
    remove_owned(config)
    health = start_image(current, config)
    registry.record_deployment(current["version"], current["image"], current["image_id"], actor, "restart")
    return {"version": current["version"], "url": config["url"], "paused": health["paused"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "bootstrap", "deploy", "rollback", "prepare-demo", "status", "stop", "start"])
    parser.add_argument("--version")
    parser.add_argument("--image")
    parser.add_argument("--fault", action="store_true")
    parser.add_argument("--actor", default="Opérateur local")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.version or input("Version SemVer : ").strip(), args.fault, args.image)
    elif args.command == "prepare-demo":
        stable, incident = demo_versions()
        result = {"stable": prepare(stable), "incident": prepare(incident, True)}
    elif args.command == "bootstrap":
        result = deploy(args.version or demo_versions()[0], args.actor, bootstrap=True)
    elif args.command == "deploy":
        default = demo_versions()[1]
        result = deploy(args.version or input(f"Version approuvée à déployer [{default}] : ").strip() or default, args.actor)
    elif args.command == "rollback":
        result = rollback(args.actor)
    elif args.command == "start":
        result = restart_existing(args.actor)
    elif args.command == "stop":
        remove_owned(settings())
        result = {"stopped": True, "data_preserved": True}
    else:
        result = {"current": current_deployment(), "releases": registry.read()}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, httpx.HTTPError) as exc:
        print("Operation refusee ou echouee : " + str(exc), file=sys.stderr)
        raise SystemExit(1)
