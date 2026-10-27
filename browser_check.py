"""Browser acceptance test against the local server (offline demo only)."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("artifacts")
OUT.mkdir(exist_ok=True)


def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1512, "height": 1100}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
        page.screenshot(path=str(OUT / "01-accueil.png"), full_page=True)
        page.click("#example-btn")
        page.select_option("#run-mode", "demo")
        page.click("#launch-btn")
        page.wait_for_selector(".agent-node.evolution-node.running", timeout=10000)
        page.screenshot(path=str(OUT / "02-workflow-actif.png"), full_page=True)
        active_id = page.evaluate("localStorage.getItem('capavenir-last-run')")
        page.reload(wait_until="networkidle")
        page.wait_for_selector(".agent-node.evolution-node.running", timeout=10000)
        assert page.evaluate("localStorage.getItem('capavenir-last-run')") == active_id
        page.wait_for_selector(".recommendation", timeout=30000)
        page.screenshot(path=str(OUT / "03-resultat.png"), full_page=True)
        assert page.locator(".roadmap-step").count() == 3
        assert page.locator(".dossier-card").count() == 2
        page.click(".agent-node.evolution-node")
        page.wait_for_selector("#detail-dialog[open]")
        assert "Python" in page.locator("#dialog-body").inner_text()
        page.click("#dialog-close")
        run_id = page.evaluate("localStorage.getItem('capavenir-last-run')")
        before = page.request.get("http://127.0.0.1:8000/api/runs").json()
        page.click("#replay-btn")
        page.wait_for_selector(".scene.replaying")
        page.click("#replay-btn")
        after = page.request.get("http://127.0.0.1:8000/api/runs").json()
        assert len(before) == len(after), "Replay must not create a run"
        page.reload(wait_until="networkidle")
        page.wait_for_selector(".recommendation")
        assert page.evaluate("localStorage.getItem('capavenir-last-run')") == run_id
        page.click('[data-view="supervision"]')
        page.click('[data-metric-mode="demo"]')
        page.wait_for_function("document.querySelector('#kpi-total').textContent !== '0'")
        page.screenshot(path=str(OUT / "04-supervision.png"), full_page=True)
        assert page.locator("#history-body tr").count() > 0
        page.click('[data-view="orientation"]')
        page.click("#alert-scenario")
        page.click("#launch-btn")
        page.wait_for_selector(".badge.partial", timeout=30000)
        # Wait for the final report rather than an intermediate alert badge.
        page.wait_for_function("document.querySelector('#mission-status').textContent.includes('Partielle')", timeout=30000)
        page.click('[data-view="supervision"]')
        page.click("#refresh-btn")
        page.wait_for_selector(".alert-row.error", timeout=10000)
        assert page.locator(".alert-row.slow").count() >= 1
        assert page.locator(".alert-row.budget").count() >= 1
        page.screenshot(path=str(OUT / "05-alertes.png"), full_page=True)
        page.set_viewport_size({"width":390,"height":844})
        page.click('[data-view="orientation"]')
        page.screenshot(path=str(OUT / "06-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile overflow"
        assert not errors, errors
        browser.close()
    print(json.dumps({"ok": True, "checks": ["form", "parallel workflow", "active reload/SSE resume", "report", "agent detail", "replay", "reload restore", "supervision", "three alerts", "mobile"], "javascript_errors": errors}))


if __name__ == "__main__":
    main()
