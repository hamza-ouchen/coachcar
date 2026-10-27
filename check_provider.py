"""One real search call; prints metadata only, never the credential."""
import asyncio
import json
import sys

import provider


async def main():
    profile = {"situation": "Développeur web junior", "skills": "Python, JavaScript, SQL débutant", "objective": "compare",
               "market": "Maroc", "remote": True, "hours": 8, "horizon": 6, "interests": "Automatisation et data"}
    try:
        dossier, usage = await provider.call_agent("evolution", profile)
        print(json.dumps({"ok": True, "title": dossier.get("title"), "sources": len(dossier.get("sources", [])),
                          "web_verified": dossier.get("web_verified"), "usage": usage}, ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "message": provider.friendly_error(exc)}, ensure_ascii=True))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
