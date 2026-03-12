from __future__ import annotations

import base64
import importlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient


def make_wav_bytes() -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, np.ones(2400, dtype=np.float32), 24000, format="WAV")
    return buffer.getvalue()


class FakeQwenProvider:
    sample_rate = 24000
    supports_voice_cloning = True

    def __init__(self):
        self.calls = []

    def synthesize(self, text: str, voice: str, *, speed: float = 1.0, profile=None):
        self.calls.append({"text": text, "voice": voice, "profile": profile})
        if not profile or not profile.get("ref_audio_path"):
            raise RuntimeError("missing profile")
        return np.ones(2400, dtype=np.float32)

    def health(self):
        return {
            "provider": "qwen3",
            "device": "cuda",
            "gpu_name": "local gpu",
            "supports_voice_cloning": True,
            "service_style": "demo",
            "base_url": "http://localhost:8000",
        }

    def list_voices(self):
        return {"Qwen3 Voice Clone": ["novel-default"]}

    def transcribe_reference_audio(self, audio_bytes: bytes, filename: str):
        return "Reference transcript"


class FakeResponse:
    def __init__(self, *, json_data=None, content=b"", status_code=200, headers=None):
        self._json = json_data or {}
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
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

    def get(self, url):
        if url.endswith("/status"):
            return FakeResponse(json_data={"loaded": True, "model": "Qwen/Qwen3", "speakers": []})
        return FakeResponse()

    def post(self, url, data=None, files=None, json=None):
        self.calls.append({"url": url, "data": data, "files": files, "json": json})
        return FakeResponse(content=make_wav_bytes())


class TestQwenServiceIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        base = Path(self.temp_dir.name)
        self.db_path = base / "app.db"
        self.audio_dir = base / "audio"
        self.profile_dir = base / "profiles"
        self.previous = {
            "DATABASE_BACKEND": os.environ.get("DATABASE_BACKEND"),
            "SQLITE_DB_PATH": os.environ.get("SQLITE_DB_PATH"),
            "AUDIO_DIR": os.environ.get("AUDIO_DIR"),
            "TTS_PROVIDER": os.environ.get("TTS_PROVIDER"),
            "TTS_VOICE_PROFILE_DIR": os.environ.get("TTS_VOICE_PROFILE_DIR"),
            "QWEN_TTS_API_STYLE": os.environ.get("QWEN_TTS_API_STYLE"),
            "QWEN_TTS_BASE_URL": os.environ.get("QWEN_TTS_BASE_URL"),
        }
        os.environ["DATABASE_BACKEND"] = "sqlite"
        os.environ["SQLITE_DB_PATH"] = str(self.db_path)
        os.environ["AUDIO_DIR"] = str(self.audio_dir)
        os.environ["TTS_PROVIDER"] = "qwen3"
        os.environ["TTS_VOICE_PROFILE_DIR"] = str(self.profile_dir)
        os.environ["QWEN_TTS_API_STYLE"] = "demo"
        os.environ["QWEN_TTS_BASE_URL"] = "http://localhost:8000"

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

    def test_qwen3_provider_demo_mode_posts_reference_audio(self):
        provider_module = importlib.import_module("src.api.services.tts_provider")
        profile_path = Path(self.temp_dir.name) / "sample.wav"
        profile_path.write_bytes(make_wav_bytes())

        with patch.object(provider_module.httpx, "Client", FakeHttpxClient):
            provider = provider_module.Qwen3Provider()
            audio = provider.synthesize(
                "Hello there",
                "novel-default",
                profile={
                    "ref_audio_path": str(profile_path),
                    "ref_text": "Hello there",
                    "voice_name": "novel-default",
                    "language": "English",
                },
            )

        self.assertIsInstance(audio, np.ndarray)
        self.assertGreater(len(audio), 0)

    def test_qwen3_provider_parses_demo_sse_audio_chunks(self):
        provider_module = importlib.import_module("src.api.services.tts_provider")
        provider = provider_module.Qwen3Provider()
        wav_b64 = base64.b64encode(make_wav_bytes()).decode("ascii")
        sse_payload = (
            f"data: {json.dumps({'type': 'chunk', 'audio_b64': wav_b64, 'sample_rate': 24000})}\n\n"
            f"data: {json.dumps({'type': 'done'})}\n\n"
        ).encode("utf-8")
        response = FakeResponse(content=sse_payload, headers={"content-type": "text/event-stream"})

        audio = provider._decode_demo_stream(response)
        self.assertIsInstance(audio, np.ndarray)
        self.assertGreater(len(audio), 0)

    def test_qwen3_provider_rejects_custom_voice_model_for_reference_cloning(self):
        provider_module = importlib.import_module("src.api.services.tts_provider")
        provider = provider_module.Qwen3Provider()

        with patch.object(provider, "_get_demo_status", return_value={"model_type": "custom_voice"}):
            with self.assertRaisesRegex(RuntimeError, "CustomVoice model"):
                provider._require_demo_voice_clone_support()

    def test_upload_profile_and_generate_audio_with_qwen_provider(self):
        provider = FakeQwenProvider()
        with patch.object(self.audio, "get_tts_provider", return_value=provider):
            with TestClient(self.main.app) as client:
                response = client.post(
                    "/api/audio/profile/test-novel",
                    files={"audio": ("reference.wav", make_wav_bytes(), "audio/wav")},
                    data={"display_name": "Narrator", "ref_text": ""},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["exists"])
                self.assertEqual(payload["provider"], "qwen3")

                profile = client.get("/api/audio/profile/test-novel")
                self.assertEqual(profile.status_code, 200)
                self.assertTrue(profile.json()["exists"])
                self.assertTrue(profile.json()["supports_voice_cloning"])

                generate = client.post("/api/audio/generate/test-novel/1?voice=novel-default")
                self.assertEqual(generate.status_code, 200)
                self.assertEqual(generate.json()["status"], "queued")

                deleted = client.delete("/api/audio/profile/test-novel")
                self.assertEqual(deleted.status_code, 200)
                self.assertEqual(deleted.json()["status"], "deleted")

                profile_after_delete = client.get("/api/audio/profile/test-novel")
                self.assertEqual(profile_after_delete.status_code, 200)
                self.assertFalse(profile_after_delete.json()["exists"])

        wav_path = self.audio.AUDIO_ROOT / "test-novel" / "Chapter_0001.wav"
        self.assertTrue(wav_path.exists())
        self.assertGreaterEqual(len(provider.calls), 1)
        self.assertTrue(provider.calls[0]["profile"]["ref_audio_path"])


if __name__ == "__main__":
    unittest.main()
