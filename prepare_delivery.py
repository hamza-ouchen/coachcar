"""Create reproducible classroom deliverables without copying local secrets."""
import csv
import importlib.metadata
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import storage
from workflow import export_workflow

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "livrables"
OUT.mkdir(exist_ok=True)
(OUT / "workflow.json").write_text(json.dumps(export_workflow(), ensure_ascii=False, indent=2), encoding="utf-8")
runs = storage.list_runs()
with (OUT / "executions.csv").open("w", encoding="utf-8-sig", newline="") as output:
    writer = csv.writer(output)
    writer.writerow(["correlation_id", "date", "mode", "statut", "situation", "duree_ms", "tokens", "cout_connu_usd", "cout_complet"])
    for run in runs:
        writer.writerow([run["id"], run["created_at"], run["mode"], run["status"], run["profile"]["situation"], run["duration_ms"], run["tokens"], run["cost"], run["cost_complete"]])
runtime = ["fastapi", "uvicorn", "langgraph", "openai", "python-dotenv", "httpx"]
(ROOT / "requirements.txt").write_text("\n".join(f"{name}=={importlib.metadata.version(name)}" for name in runtime) + "\n", encoding="utf-8")

# Explicit allowlist: .env, SQLite files and virtualenv are never included.
sources = [*ROOT.glob("*.py"), ROOT / "LANCER.cmd", ROOT / "requirements.txt", ROOT / ".env.example", ROOT / ".gitignore", ROOT / "README.md", ROOT / "PLAN.md"]
sources += [p for folder in ["static", "tests", "livrables"] for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix not in (".pyc", ".zip")]
archive = OUT / "Cap-Avenir-TP.zip"
with ZipFile(archive, "w", ZIP_DEFLATED) as package:
    for path in sources:
        package.write(path, "Cap-Avenir/" + path.relative_to(ROOT).as_posix())
    assert not any(Path(name).name == ".env" for name in package.namelist())
print(json.dumps({"archive": str(archive.relative_to(ROOT)), "files": len(sources), "runs_exported": len(runs)}))
