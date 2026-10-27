"""Ensure the CI artifact works without a developer database or credentials."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import provider
import storage
from scripts.package_ci import build_package, ROOT


class DeliveryChecks(unittest.TestCase):
    def test_packages_checkout_without_local_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            # A package build must not read the application's database or call a model.
            with patch.object(storage, "connect", side_effect=AssertionError("Database used during packaging")), \
                 patch.object(provider, "call_agent", side_effect=AssertionError("Paid API called")):
                archive, manifest = build_package(ROOT, output)
            with ZipFile(archive) as package:
                names = package.namelist()
                self.assertIn("Cap-Avenir/app.py", names)
                self.assertIn("Cap-Avenir/.env.example", names)
                self.assertIn("Cap-Avenir/.github/workflows/ci.yml", names)
                self.assertIn("Cap-Avenir/livrables/workflow.json", names)
                self.assertFalse(any(Path(name).name == ".env" for name in names))
                self.assertFalse(any("/data/" in name or "/.venv/" in name or name.endswith(".db") for name in names))
                self.assertNotIn("Cap-Avenir/livrables/exemple-analyse-reelle.json", names)
                self.assertNotIn("Cap-Avenir/livrables/executions.csv", names)
                self.assertIsNone(package.testzip())
            self.assertFalse(manifest["api_calls"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
