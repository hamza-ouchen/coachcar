"""Internet access requires a password; local classroom use is unchanged."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import access
import app
import storage


class AccessChecks(unittest.TestCase):
    def test_authentication_protects_views_api_and_operations(self):
        with tempfile.TemporaryDirectory() as folder:
            original = storage.DB_PATH
            storage.DB_PATH = Path(folder) / 'test.db'
            try:
                with patch.dict(os.environ, {"CAP_AVENIR_REQUIRE_AUTH": "1", "CAP_AVENIR_ADMIN_PASSWORD": "mot-de-passe-test-é", "CAP_AVENIR_ADMIN_USER": "admin"}):
                    with TestClient(app.app) as client:
                        self.assertEqual(client.get('/api/health').status_code, 200)
                        for route in ['/', '/api/runs', '/api/ops', '/static/app.js']:
                            self.assertEqual(client.get(route).status_code, 401)
                        self.assertEqual(client.get('/api/ops', auth=('admin', 'wrong')).status_code, 401)
                        self.assertEqual(client.get('/api/ops', auth=('admin', 'mot-de-passe-test-é')).status_code, 200)
                        self.assertEqual(client.get('/api/ops', headers={'Authorization': 'Basic invalid%%'}).status_code, 401)
            finally:
                storage.DB_PATH = original

    def test_cloud_refuses_missing_password_or_database(self):
        with patch.dict(os.environ, {"RENDER": "true", "CAP_AVENIR_ADMIN_PASSWORD": "", "DATABASE_URL": ""}):
            with self.assertRaises(RuntimeError):
                access.validate_configuration()
        with patch.dict(os.environ, {"RENDER": "true", "CAP_AVENIR_ADMIN_PASSWORD": "test", "DATABASE_URL": "not-a-postgresql-url"}):
            with self.assertRaises(RuntimeError):
                access.validate_configuration()
