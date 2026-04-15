from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient


def make_pcm_bytes() -> bytes:
    waveform = (np.array([0, 8192, -8192, 16384, -16384], dtype=np.int16)).tobytes()
    return waveform


class FakeElevenLabsProvider:
    sample_rate = 24000
    supports_voice_cloning = False

    def __init__(self):
        self.calls = []

    def synthesize(self, text: str, voice: str, *, speed: float = 1.0, profile=None):
        self.calls.append({"text": text, "voice": voice, "speed": speed, "profile": profile})
        return np.ones(2400, dtype=np.float32)

    def health(self):
        return {
            "provider": "elevenlabs",
            "device": "cloud",
            "gpu_name": None,
            "supports_voice_cloning": False,
            "base_url": "https://api.elevenlabs.io",
            "model": "eleven_multilingual_v2",
        }

    def list_voices(self):
        return {"ElevenLabs Premade": ["voice-123"]}

    def list_voice_choices(self):
        return [{"id": "voice-123", "label": "Narrator (voice-12)", "name": "Narrator", "group": "ElevenLabs Premade"}]


class FakeResponse:
    def __init__(self, *, json_data=None, content=b"", status_code=200):
        self._json = json_data or {}
        self.content = content
        self.status_code = status_code
        try:
            self.text = content.decode("utf-8")
        except Exception:
            self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._json


class FakeHttpxClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None, params=None):
        self.calls.append({"method": "GET", "url": url, "headers": headers, "params": params})
        if url.endswith("/v2/voices"):
            return FakeResponse(json_data={"voices": [{"voice_id": "voice-123", "name": "Narrator", "category": "premade"}]})
        return FakeResponse()

    def post(self, url, headers=None, params=None, json=None):
        self.calls.append({"method": "POST", "url": url, "headers": headers, "params": params, "json": json})
        return FakeResponse(content=make_pcm_bytes())


class TestElevenLabsIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        base = Path(self.temp_dir.name)
        self.db_path = base / "app.db"
        self.audio_dir = base / "audio"
        self.profile_dir = base / "profiles"
        self.previous = {
            "NOVELLABS_ENV_FILE": os.environ.get("NOVELLABS_ENV_FILE"),
            "DATABASE_BACKEND": os.environ.get("DATABASE_BACKEND"),
            "SQLITE_DB_PATH": os.environ.get("SQLITE_DB_PATH"),
            "AUDIO_DIR": os.environ.get("AUDIO_DIR"),
            "TTS_PROVIDER": os.environ.get("TTS_PROVIDER"),
            "TTS_VOICE_PROFILE_DIR": os.environ.get("TTS_VOICE_PROFILE_DIR"),
            "ELEVENLABS_API_KEY": os.environ.get("ELEVENLABS_API_KEY"),
            "ELEVENLABS_OUTPUT_FORMAT": os.environ.get("ELEVENLABS_OUTPUT_FORMAT"),
        }
        # Force config loading to ignore the repository-level .env during this test.
        os.environ["NOVELLABS_ENV_FILE"] = str(base / ".env.test")
        os.environ["DATABASE_BACKEND"] = "sqlite"
        os.environ["SQLITE_DB_PATH"] = str(self.db_path)
        os.environ["AUDIO_DIR"] = str(self.audio_dir)
        os.environ["TTS_PROVIDER"] = "kokoro"
        os.environ["TTS_VOICE_PROFILE_DIR"] = str(self.profile_dir)
        os.environ["ELEVENLABS_API_KEY"] = "test-key"
        os.environ["ELEVENLABS_OUTPUT_FORMAT"] = "pcm_24000"

        for module_name in [
            "src.api.config",
            "src.api.database",
            "src.api.services.tts_provider",
            "src.api.routes.audio",
            "src.api.main",
        ]:
            sys.modules.pop(module_name, None)

        self.database = importlib.import_module("src.api.database")
        self.audio = importlib.import_module("src.api.routes.audio")
        self.main = importlib.import_module("src.api.main")
        self.database.init_db()

        with self.database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO novels (slug, title, chapter_count, data_path, source_toc_url)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("test-novel", "Test Novel", 1, str(base / "output"), "https://example.com/novel"),
            )
            cursor.execute("SELECT id FROM novels WHERE slug = ?", ("test-novel",))
            novel_id = cursor.fetchone()["id"]
            cursor.execute(
                """
                INSERT INTO chapters (novel_id, chapter_number, title, content, word_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (novel_id, 1, "Chapter 1", "Hello world.\n\nAnother sentence.", 4),
            )

    def tearDown(self):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        for module_name in [
            "src.api.config",
            "src.api.database",
            "src.api.services.tts_provider",
            "src.api.routes.audio",
            "src.api.main",
        ]:
            sys.modules.pop(module_name, None)

    def test_elevenlabs_provider_lists_named_choices_and_decodes_pcm(self):
        provider_module = importlib.import_module("src.api.services.tts_provider")

        with patch.object(provider_module.httpx, "Client", FakeHttpxClient):
            provider = provider_module.ElevenLabsProvider()
            audio = provider.synthesize("Hello there", "voice-123")
            voices = provider.list_voice_choices()

        self.assertIsInstance(audio, np.ndarray)
        self.assertGreater(len(audio), 0)
        self.assertEqual(provider.sample_rate, 24000)
        self.assertEqual(voices[0]["id"], "voice-123")
        self.assertIn("Narrator", voices[0]["label"])

    def test_audio_routes_support_elevenlabs_provider_query(self):
        provider = FakeElevenLabsProvider()

        with patch.object(self.audio, "get_tts_provider", return_value=provider):
            with TestClient(self.main.app) as client:
                health = client.get("/api/audio/health?provider=elevenlabs")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json()["provider"], "elevenlabs")

                voices = client.get("/api/audio/voices/flat?provider=elevenlabs")
                self.assertEqual(voices.status_code, 200)
                self.assertEqual(voices.json()[0]["id"], "voice-123")

                generate = client.post("/api/audio/generate/test-novel/1?provider=elevenlabs&voice=voice-123")
                self.assertEqual(generate.status_code, 200)
                self.assertEqual(generate.json()["status"], "queued")
                self.assertEqual(generate.json()["provider"], "elevenlabs")

        wav_path = self.audio.AUDIO_ROOT / "test-novel" / "Chapter_0001.wav"
        self.assertTrue(wav_path.exists())
        self.assertGreaterEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0]["voice"], "voice-123")


if __name__ == "__main__":
    unittest.main()
