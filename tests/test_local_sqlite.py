"""Tests for local SQLite initialization."""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


class TestLocalSQLiteInitialization(unittest.TestCase):
    def test_init_db_creates_expected_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            previous_backend = os.environ.get("DATABASE_BACKEND")
            previous_path = os.environ.get("SQLITE_DB_PATH")
            os.environ["DATABASE_BACKEND"] = "sqlite"
            os.environ["SQLITE_DB_PATH"] = str(db_path)

            try:
                for module_name in ["src.api.config", "src.api.database"]:
                    sys.modules.pop(module_name, None)

                config = importlib.import_module("src.api.config")
                database = importlib.import_module("src.api.database")
                self.assertEqual(config.DATABASE_BACKEND, "sqlite")

                database.init_db()

                conn = sqlite3.connect(db_path)
                try:
                    tables = {
                        row[0]
                        for row in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }
                finally:
                    conn.close()
            finally:
                if previous_backend is None:
                    os.environ.pop("DATABASE_BACKEND", None)
                else:
                    os.environ["DATABASE_BACKEND"] = previous_backend

                if previous_path is None:
                    os.environ.pop("SQLITE_DB_PATH", None)
                else:
                    os.environ["SQLITE_DB_PATH"] = previous_path

                for module_name in ["src.api.config", "src.api.database"]:
                    sys.modules.pop(module_name, None)

            self.assertTrue({"novels", "chapters", "chapter_audio", "audio_timings"}.issubset(tables))


if __name__ == "__main__":
    unittest.main()
