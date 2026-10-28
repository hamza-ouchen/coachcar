"""Production cannot publish without required GitHub reviewers."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from scripts.release_policy import verify


class ReleasePolicyChecks(unittest.TestCase):
    def test_missing_reviewers_refuses_publication(self):
        response = httpx.Response(200, json={"protection_rules": []})
        environment = {"RELEASE_VERSION": Path("VERSION").read_text().strip(), "GITHUB_REPOSITORY": "owner/repo", "GITHUB_OUTPUT": ""}
        with patch.dict(os.environ, environment), patch("scripts.release_policy.httpx.get", return_value=response):
            with self.assertRaises(ValueError):
                verify()

    def test_mismatched_version_refuses_before_network(self):
        with patch.dict(os.environ, {"RELEASE_VERSION": "9.9.9"}), patch("scripts.release_policy.httpx.get") as request:
            with self.assertRaises(ValueError):
                verify()
            request.assert_not_called()
