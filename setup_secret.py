"""Local one-time configuration. Never prints the supplied credential."""
import getpass
from pathlib import Path

if __name__ == "__main__":
    secret = getpass.getpass("OpenRouter key (hidden): ").strip()
    if not secret.startswith("sk-or-") or "\n" in secret:
        raise SystemExit("Invalid key format")
    defaults = Path(".env.example").read_text(encoding="utf-8")
    Path(".env").write_text(defaults.replace("OPENROUTER_API_KEY=", "OPENROUTER_API_KEY=" + secret, 1), encoding="utf-8")
    print("Local configuration saved.")
