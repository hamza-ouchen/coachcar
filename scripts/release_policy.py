"""Fail closed if a production publication has no real GitHub approval gate."""
import json
import os
import re
from pathlib import Path

import httpx


def verify():
    version = os.environ["RELEASE_VERSION"].removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Publication stable : version attendue sous la forme 1.1.0.")
    if version != Path("VERSION").read_text(encoding="utf-8").strip():
        raise ValueError("La version demandée doit correspondre au fichier VERSION de cette révision.")
    repository = os.environ["GITHUB_REPOSITORY"]
    headers = {"Accept": "application/vnd.github+json"}
    if os.getenv("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    response = httpx.get(f"https://api.github.com/repos/{repository}/environments/production", headers=headers, timeout=20)
    if response.status_code != 200:
        raise ValueError("Configurez l'environnement GitHub production avec Required reviewers avant de publier.")
    rules = response.json().get("protection_rules", [])
    if not any(rule.get("type") == "required_reviewers" and rule.get("reviewers") for rule in rules):
        raise ValueError("Publication refusée : aucun approbateur obligatoire sur production.")
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("version=" + version + "\n")
    print(json.dumps({"version": version, "required_reviewers_configured": True}))


if __name__ == "__main__":
    verify()
