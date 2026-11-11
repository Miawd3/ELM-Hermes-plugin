"""Fresh init regression for the disclosed five-template engine patch."""
import os
from pathlib import Path
import tempfile
import unittest

from test_provider import engine


class EngineInitMetadata(unittest.TestCase):
    def test_new_store_is_clean_and_metadata_is_indexed(self):
        with tempfile.TemporaryDirectory(prefix="elm-init-", dir=os.environ.get("TMPDIR")) as base:
            root = Path(base) / "new-store"
            engine(root, "init", "--project", "sample")
            self.assertEqual([], engine(root, "doctor", "--no-sync")["issues"])
            self.assertEqual(5, engine(root, "stats", "--no-sync")["docs"])
            results = engine(root, "search", "durable overview", "--project", "sample", "--no-sync")["results"]
            self.assertTrue(any("project" in row["tags"] for row in results))
            self.assertTrue(engine(root, "status", "--readiness-only")["healthy"])
