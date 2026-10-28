"""Publish the tested tar after the GitHub environment approval, without rebuild."""
import os
import subprocess

from pathlib import Path


def run(*args, input=None):
    subprocess.run(args, input=input, text=True, check=True)


if __name__ == "__main__":
    image = "ghcr.io/" + os.environ["GITHUB_REPOSITORY"].lower() + ":" + os.environ["RELEASE_VERSION"]
    run("docker", "load", "--input", "ci-output/release-image.tar")
    run("docker", "login", "ghcr.io", "--username", os.environ["GITHUB_ACTOR"], "--password-stdin", input=os.environ["GHCR_TOKEN"])
    try:
        # Authenticate before looking for an existing private package as well.
        exists = subprocess.run(["docker", "manifest", "inspect", image], capture_output=True)
        if exists.returncode == 0:
            raise SystemExit("Cette version existe déjà dans le registre. Incrémentez VERSION.")
        run("docker", "tag", "cap-avenir:release", image)
        run("docker", "push", image)
    finally:
        run("docker", "logout", "ghcr.io")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("Image testée puis approuvée : `" + image + "`.\n\nDéploiement local explicite avec le gestionnaire de versions.\n")
