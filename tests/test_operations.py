"""Operations tests use real task cancellation, isolated data and mocked agents."""
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app
import operations
import provider
import release_registry
import storage

PROFILE = {"situation": "Développeur junior", "skills": "Python, SQL"}


class OperationsChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "test.db"
        self.environment = patch.dict(os.environ, {"CAP_AVENIR_RUNTIME_DIR": str(Path(self.temp.name) / "runtime"), "CAP_AVENIR_DEMO_FAULT": "0"})
        self.environment.start()
        self.client = TestClient(app.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.environment.stop()
        storage.DB_PATH = self.old_db
        self.temp.cleanup()

    def test_kill_switch_cancels_tasks_and_blocks_new_runs(self):
        async def slow(*args, **kwargs):
            await asyncio.sleep(10)
            return {"summary": "Must not finish"}, {"cost": .01}

        with patch.object(provider, "demo_agent", slow):
            created = self.client.post("/api/runs", json={"profile": PROFILE, "mode": "demo"})
            run_id = created.json()["id"]
            time.sleep(.08)
            result = self.client.post("/api/ops/pause", json={"paused": True, "actor": "Test automatique", "reason": "Test d'annulation"})
            self.assertEqual(result.status_code, 200)
            run = self.client.get("/api/runs/" + run_id).json()
            self.assertEqual(run["status"], "cancelled")
            self.assertTrue(run["steps"])
            self.assertTrue(all(s["status"] == "cancelled" for s in run["steps"]))
            self.assertFalse(any(e["agent"] == "supervisor" and e["type"] == "agent_started" for e in run["events"]))
            self.assertTrue(any(e["type"] == "run_cancelled" for e in run["events"]))
            self.assertEqual(self.client.post("/api/runs", json={"profile": PROFILE, "mode": "demo"}).status_code, 503)
            storage.init_db()
            self.assertTrue(operations.get_state()["paused"])
            self.client.post("/api/ops/pause", json={"paused": False, "actor": "Test automatique"})
            self.assertFalse(operations.get_state()["paused"])

    def test_incident_never_changes_a_real_run(self):
        calls = []

        async def execute(run_id, profile, demo, scenario):
            calls.append((demo, scenario))
            storage.finish_run(run_id, "completed", 1, {"recommendation": "Fixture"})

        self.client.post("/api/ops/incident", json={"incident": "provider_error", "actor": "Test automatique"})
        with patch.object(app.workflow, "execute", execute), patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}):
            self.assertEqual(self.client.post("/api/runs", json={"profile": PROFILE, "mode": "demo"}).status_code, 202)
            self.assertEqual(self.client.post("/api/runs", json={"profile": PROFILE, "mode": "live"}).status_code, 202)
            time.sleep(.03)
        self.assertIn((True, "incident_error"), calls)
        self.assertIn((False, "normal"), calls)

    def test_review_binds_to_exact_image_and_is_audited(self):
        image_id = "sha256:" + "a" * 64
        release_registry.register("1.1.0", "cap-avenir:1.1.0", image_id)
        with self.assertRaises(ValueError):
            release_registry.approved("1.1.0", image_id)
        self.assertEqual(self.client.post("/api/ops/releases/1.1.0/review", json={"decision": "approved", "actor": "Validateur de test"}).status_code, 409)
        result = self.client.post("/api/ops/releases/1.1.0/review", json={"decision": "approved", "actor": "Validateur de test", "agent_card_reviewed": True})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(release_registry.approved("1.1.0", image_id)["reviewer"], "Validateur de test")
        with self.assertRaises(ValueError):
            release_registry.approved("1.1.0", "sha256:" + "b" * 64)
        self.assertTrue(any(e["action"] == "release_approved" for e in self.client.get("/api/ops").json()["audit"]))
        self.assertEqual(self.client.post("/api/ops/releases/1.1.0/review", json={"decision": "approved", "actor": "  "}).status_code, 422)

    def test_backup_preserves_database_and_exports_control(self):
        result = self.client.post("/api/ops/backup", json={"actor": "Test automatique"})
        self.assertEqual(result.status_code, 200)
        self.assertTrue((storage.DB_PATH.parent / "backups" / result.json()["filename"]).exists())
        exported = self.client.get("/api/ops/export")
        self.assertEqual(exported.status_code, 200)
        self.assertNotIn("sk-or-v1-", exported.text)
        self.assertTrue(exported.json()["version"])
