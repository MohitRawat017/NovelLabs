"""Regression tests for lightweight backend imports."""

import importlib
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class TestBackendImports(unittest.TestCase):
    def setUp(self):
        self.previous_env = {
            "NOVELLABS_ENV_FILE": os.environ.get("NOVELLABS_ENV_FILE"),
            "TTS_PROVIDER": os.environ.get("TTS_PROVIDER"),
            "ELEVENLABS_API_KEY": os.environ.get("ELEVENLABS_API_KEY"),
            "DATABASE_BACKEND": os.environ.get("DATABASE_BACKEND"),
            "AUDIO_STORAGE_BACKEND": os.environ.get("AUDIO_STORAGE_BACKEND"),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL"),
        }

    def tearDown(self):
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        for module_name in [
            "src.api.config",
            "src.api.services.tts_provider",
            "src.api.main",
        ]:
            sys.modules.pop(module_name, None)

    def test_novels_route_imports_without_sqlalchemy_side_effects(self):
        module = importlib.import_module("src.api.routes.novels")
        self.assertTrue(hasattr(module, "router"))

    def test_app_imports(self):
        module = importlib.import_module("src.api.main")
        self.assertTrue(hasattr(module, "app"))

    def test_backend_logging_handlers_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("LOG_LEVEL=DEBUG\n", encoding="utf-8")

            os.environ["NOVELLABS_ENV_FILE"] = str(env_path)
            os.environ["LOG_LEVEL"] = "INFO"

            for module_name in ["src.api.config", "src.api.main"]:
                sys.modules.pop(module_name, None)

            module = importlib.import_module("src.api.main")
            root_logger = logging.getLogger()
            handler_names = {
                getattr(handler, "name", "")
                for handler in root_logger.handlers
            }

            self.assertTrue(hasattr(module, "app"))
            self.assertEqual(root_logger.level, logging.DEBUG)
            self.assertTrue(
                {
                    "novellabs_console",
                    "novellabs_app_file",
                    "novellabs_audio_file",
                    "novellabs_error_file",
                }.issubset(handler_names)
            )
            self.assertEqual(logging.getLogger("uvicorn.access").level, logging.WARNING)

    def test_scraper_route_exports_public_worker(self):
        module = importlib.import_module("src.api.routes.scraper")
        self.assertTrue(hasattr(module, "run_scraper_job"))

    def test_novels_endpoint_returns_success(self):
        module = importlib.import_module("src.api.main")
        client = TestClient(module.app)

        response = client.get("/api/novels")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("novels", payload)
        self.assertIn("total", payload)

    def test_config_reads_tts_provider_from_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("TTS_PROVIDER=qwen3\n", encoding="utf-8")

            os.environ["NOVELLABS_ENV_FILE"] = str(env_path)
            os.environ["TTS_PROVIDER"] = "kokoro"

            for module_name in ["src.api.config", "src.api.services.tts_provider"]:
                sys.modules.pop(module_name, None)

            config = importlib.import_module("src.api.config")
            self.assertEqual(config.TTS_PROVIDER, "qwen3")

    def test_config_accepts_elevenlabs_provider_from_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("TTS_PROVIDER=elevenlabs\n", encoding="utf-8")

            os.environ["NOVELLABS_ENV_FILE"] = str(env_path)
            os.environ["TTS_PROVIDER"] = "kokoro"

            for module_name in ["src.api.config", "src.api.services.tts_provider"]:
                sys.modules.pop(module_name, None)

            config = importlib.import_module("src.api.config")
            self.assertEqual(config.TTS_PROVIDER, "elevenlabs")

    def test_sqlite_mode_forces_local_audio_storage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "DATABASE_BACKEND=sqlite\nAUDIO_STORAGE_BACKEND=cloud\n",
                encoding="utf-8",
            )

            os.environ["NOVELLABS_ENV_FILE"] = str(env_path)

            for module_name in ["src.api.config"]:
                sys.modules.pop(module_name, None)

            config = importlib.import_module("src.api.config")
            self.assertEqual(config.DATABASE_BACKEND, "sqlite")
            self.assertEqual(config.AUDIO_STORAGE_BACKEND, "local")


if __name__ == "__main__":
    unittest.main()
