"""Browser QA on an isolated Docker instance; decisions are test fixtures."""
import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import release_manager as manager
import release_registry as registry


def main():
    errors = []
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    saved = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="cap-avenir-browser-") as temporary:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        os.environ.update(CAP_AVENIR_RUNTIME_DIR=str(Path(temporary) / "runtime"), CAP_AVENIR_DATA_DIR=str(Path(temporary) / "data"),
                          CAP_AVENIR_CONTAINER="cap-avenir-browser-" + uuid4().hex[:8], CAP_AVENIR_PORT=str(port), CAP_AVENIR_WITH_SECRETS="0")
        config = manager.settings()
        try:
            for image in ["cap-avenir:verify-stable", "cap-avenir:verify-incident"]:
                info = manager.image_info(image)
                labels = info["Config"]["Labels"]
                registry.register(labels["org.opencontainers.image.version"], image, info["Id"], demo_fault=labels.get("com.cap-avenir.demo-fault") == "1")
            manager.deploy("1.1.0", "Initialisation test navigateur", bootstrap=True)
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width":1512,"height":1100})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(config["url"] + "/#operations", wait_until="networkidle")
                page.wait_for_function("document.querySelector('#ops-version').textContent === 'v1.1.0'")
                page.fill("#ops-actor", "Validation navigateur (test)")
                assert page.request.get(config["url"] + "/api/ops/agent-card").status == 200
                page.screenshot(path=str(output / "07-exploitation.png"), full_page=True)
                page.locator('[data-review="approved"][data-version="1.1.1-incident.1"]').click()
                page.wait_for_function("document.querySelector('#toast').textContent.includes('Agent Card')")
                assert registry.read()["candidates"][1]["status"] == "pending"
                page.check("#ops-card-reviewed")
                page.locator('[data-review="approved"][data-version="1.1.1-incident.1"]').click()
                page.wait_for_function("document.querySelector('#ops-releases').textContent.includes('Approuvée')")
                assert registry.read()["candidates"][1]["agent_card_reviewed"]
                page.select_option("#ops-incident", "slow")
                page.click("#ops-test-incident")
                page.wait_for_selector(".agent-node.evolution-node.running")
                page.click('[data-view="operations"]')
                page.click("#ops-stop")
                page.wait_for_function("document.querySelector('#ops-service').textContent.includes('suspendues')")
                assert page.request.post(config["url"] + "/api/runs", data={"profile":{"situation":"Test navigateur","skills":"Python"},"mode":"demo"}).status == 503
                page.screenshot(path=str(output / "08-arret-urgence.png"), full_page=True)
                page.click("#ops-resume")
                page.wait_for_function("document.querySelector('#ops-service').textContent.includes('autorisées')")
                page.select_option("#ops-incident", "normal")
                page.click("#ops-test-incident")
                page.wait_for_selector(".recommendation", timeout=25000)
                assert page.locator(".roadmap-step").count() == 3
                page.click('[data-view="supervision"]')
                page.click('[data-metric-mode="demo"]')
                page.wait_for_function("document.querySelector('#kpi-total').textContent === '2'")
                page.click('[data-view="operations"]')
                page.set_viewport_size({"width":390,"height":844})
                page.screenshot(path=str(output / "09-exploitation-mobile.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert not errors, errors
                browser.close()
        finally:
            try:
                manager.remove_owned(config)
            finally:
                os.environ.clear()
                os.environ.update(saved)
    print(json.dumps({"passed":True,"javascript_errors":errors,"checks":["operations view", "version", "card download", "card review required", "approval", "kill switch", "resume", "normal recommendation", "supervision", "mobile"]}))


if __name__ == "__main__":
    main()
