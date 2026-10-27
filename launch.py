"""Double-click launcher: reuse the existing app or start it and open a browser."""
import json
import os
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
URL = "http://127.0.0.1:8000"


def already_running():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=2) as response:
            return json.load(response).get("application") == "cap-avenir"
    except (OSError, ValueError, urllib.error.URLError):
        return False


if __name__ == "__main__":
    if already_running():
        webbrowser.open(URL)
    else:
        import uvicorn
        print("Cap Avenir : " + URL)
        print("Gardez cette fenetre ouverte pendant la presentation. Ctrl+C pour arreter.")
        threading.Timer(2, lambda: webbrowser.open(URL)).start()
        uvicorn.run("app:app", host="127.0.0.1", port=8000)
