"""Integration checks on an isolated SQLite database; no paid API calls."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

import app
import provider
import storage
import workflow

PROFILE = {"situation": "Développeur junior", "skills": "Python, SQL", "objective": "compare", "market": "Maroc", "remote": True, "hours": 8, "horizon": 6, "interests": "Data"}


class WorkflowChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "test.db"
        storage.init_db()

    def tearDown(self):
        storage.DB_PATH = self.previous_db
        self.temp.cleanup()

    def run_workflow(self, function):
        run_id = str(uuid4())
        storage.create_run(run_id, PROFILE, "demo", "test-model")
        with patch.object(provider, "demo_agent", function):
            asyncio.run(workflow.execute(run_id, PROFILE, demo=True))
        return storage.get_run(run_id), storage.events(run_id)

    def test_parallel_research_join_and_billing(self):
        async def stub(agent, profile, dossiers=None, scenario="normal"):
            await asyncio.sleep(.04 if agent == "evolution" else .08 if agent == "reconversion" else .01)
            if agent == "supervisor":
                self.assertIn("summary", dossiers["evolution"])
                self.assertIn("summary", dossiers["reconversion"])
                return {"recommendation": "Test", "recommended_path": "Python"}, {"prompt_tokens": 20, "completion_tokens": 10, "cost": .02}
            return {"summary": agent, "sources": []}, {"prompt_tokens": 10, "completion_tokens": 5, "cost": .01}

        run, events = self.run_workflow(stub)
        self.assertEqual(run["status"], "completed")
        self.assertAlmostEqual(run["cost"], .04)
        self.assertEqual(run["tokens"], 60)
        starts = {e["agent"]: e["elapsed_ms"] for e in events if e["type"] == "agent_started"}
        ends = {e["agent"]: e["elapsed_ms"] for e in events if e["type"] == "agent_completed"}
        self.assertLess(starts["reconversion"], ends["evolution"])
        self.assertGreaterEqual(starts["supervisor"], max(ends["evolution"], ends["reconversion"]))
        self.assertTrue(all(e["run_id"] == run["id"] for e in events))
        self.assertEqual(len([e for e in events if e["type"] == "handoff"]), 2)
        self.assertEqual(storage.metrics("live")["total"], 0)
        self.assertEqual(storage.metrics("demo")["projection_sample"], 1)

    def test_partial_and_unknown_cost(self):
        async def stub(agent, profile, dossiers=None, scenario="normal"):
            if agent == "reconversion":
                raise ValueError("Recherche indisponible")
            if agent == "supervisor":
                self.assertIn("error", dossiers["reconversion"])
                return {"recommendation": "Partielle"}, {"cost": .01}
            return {"summary": "Test"}, {"cost": None}

        run, events = self.run_workflow(stub)
        self.assertEqual(run["status"], "partial")
        self.assertFalse(run["cost_complete"])
        self.assertAlmostEqual(run["cost"], .01)
        self.assertTrue(any(e["type"] == "alert" and e["payload"]["code"] == "error" for e in events))
        self.assertEqual(storage.metrics("demo")["projection_sample"], 0)

    def test_two_failures_skip_supervisor(self):
        calls = []

        async def stub(agent, *args, **kwargs):
            calls.append(agent)
            raise ValueError("Indisponible")

        run, events = self.run_workflow(stub)
        self.assertEqual(run["status"], "failed")
        self.assertNotIn("supervisor", calls)
        self.assertTrue(any(e["type"] == "agent_skipped" for e in events))
        self.assertIsNone(run["cost"])

    def test_all_alert_types(self):
        async def stub(agent, profile, dossiers=None, scenario="normal"):
            await asyncio.sleep(.035)
            if agent == "reconversion":
                raise ValueError("Erreur de test")
            return {"summary": "Test", "recommendation": "Test"}, {"cost": .2}

        with patch.object(workflow, "SLOW_SECONDS", .01):
            run, _ = self.run_workflow(stub)
        self.assertEqual({a["code"] for a in run["alerts"]}, {"slow", "budget", "error"})
        self.assertEqual(len([a for a in run["alerts"] if a["code"] == "budget"]), 1)

    def test_endpoints_exports_and_validation(self):
        with TestClient(app.app) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/api/runs/missing").status_code, 404)
            invalid = client.post("/api/runs", json={"profile": dict(PROFILE, situation=" "), "mode": "demo"})
            self.assertEqual(invalid.status_code, 422)
            self.assertEqual(len(storage.list_runs()), 0)
            exported = client.get("/api/workflow/export")
            self.assertEqual(exported.status_code, 200)
            self.assertEqual(len([n for n in exported.json()["graph"]["nodes"] if n["id"] not in ("__start__", "__end__")]), 3)
            self.assertIn("correlation_id", client.get("/api/exports/runs.csv").text)
            self.assertNotIn("sk-or-", client.get("/api/health").text)

    def test_restart_keeps_history_marks_active_interrupted(self):
        storage.create_run("restart", PROFILE, "demo", "test")
        storage.start_step("step", "restart", "evolution")
        storage.init_db()
        self.assertEqual(storage.get_run("restart")["status"], "interrupted")
        self.assertEqual(storage.get_run("restart")["steps"][0]["status"], "interrupted")


if __name__ == "__main__":
    unittest.main(verbosity=2)
