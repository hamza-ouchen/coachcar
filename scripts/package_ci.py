"""Package sources from a fresh checkout. No database, .env or API needed."""
import json
import os
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ROOT_FILES = (
    "app.py", "provider.py", "workflow.py", "storage.py", "launch.py",
    "setup_secret.py", "prepare_delivery.py", "browser_check.py",
    "check_provider.py", "live_check.py", "LANCER.cmd", "VERIFIER.cmd",
    "requirements.txt", ".env.example", ".gitignore", "README.md", "PLAN.md",
    "operations.py", "release_registry.py", "VERSION", "Dockerfile", ".dockerignore", "compose.yaml",
    "INTEGRATION-EXPLOITATION.md", "DOCKER.cmd", "DEPLOYER.cmd", "ROLLBACK.cmd", "EXERCICE.cmd",
)


def source_files(root):
    files = [root / name for name in ROOT_FILES if (root / name).is_file()]
    patterns = {
        "static": {".html", ".css", ".js", ".svg"},
        "tests": {".py"},
        "scripts": {".py"},
        ".github/workflows": {".yml", ".yaml"},
        "livrables": {".md"},
    }
    for folder, extensions in patterns.items():
        files.extend(path for path in (root / folder).rglob("*")
                     if path.is_file() and path.suffix in extensions)
    return sorted(set(files))


def build_package(root=ROOT, output=None):
    # Importing/exporting the graph does not execute it or open the database.
    from workflow import export_workflow

    root = Path(root).resolve()
    output = Path(output) if output else root / "ci-output"
    output.mkdir(parents=True, exist_ok=True)
    required = ["app.py", "workflow.py", "provider.py", "storage.py", "requirements.txt", "static/index.html"]
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ValueError("Fichiers requis absents : " + ", ".join(missing))
    sources = source_files(root)
    manifest = {
        "project": "Cap Avenir",
        "commit": os.getenv("GITHUB_SHA") or "verification-locale",
        "files": [path.relative_to(root).as_posix() for path in sources],
        "generated_files": ["livrables/workflow.json"],
        "api_calls": False,
        "deployment": False,
    }
    archive = output / "Cap-Avenir-CI.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as package:
        for path in sources:
            package.write(path, "Cap-Avenir/" + path.relative_to(root).as_posix())
        package.writestr("Cap-Avenir/livrables/workflow.json",
                          json.dumps(export_workflow(), ensure_ascii=False, indent=2))
        package.writestr("Cap-Avenir/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ValueError("Archive invalide.")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return archive, manifest


if __name__ == "__main__":
    archive, manifest = build_package()
    print(json.dumps({"archive": str(archive), "source_files": len(manifest["files"]), "api_calls": False}))
