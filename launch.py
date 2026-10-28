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
    # Prefer the managed Docker service when it is already available.
    for address in ["http://127.0.0.1:8080", URL]:
        try:
            with urllib.request.urlopen(address + "/api/health", timeout=2) as response:
                if json.load(response).get("application") == "cap-avenir":
                    return address
        except (OSError, ValueError, urllib.error.URLError):
            pass
    return None


if __name__ == "__main__":
    running_address = already_running()
    if running_address:
        webbrowser.open(running_address)
    else:
        import uvicorn
        print("Cap Avenir : " + URL)
        print("Gardez cette fenetre ouverte pendant la presentation. Ctrl+C pour arreter.")
        threading.Timer(2, lambda: webbrowser.open(URL)).start()
        uvicorn.run("app:app", host="127.0.0.1", port=8000)
