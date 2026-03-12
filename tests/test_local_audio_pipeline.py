"""Tests for the local audio generation pipeline using a fake TTS provider."""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


class FakeProvider:
    sample_rate = 24000
    supports_voice_cloning = False

    def synthesize(self, text: str, voice: str, *, speed: float = 1.0, profile=None):
        return np.ones(2400, dtype=np.float32)

    def health(self):
        return {
            "provider": "kokoro",
            "device": "cpu",
            "gpu_name": None,
            "sample_rate": self.sample_rate,
        }

    def list_voices(self):
        return {"American English (Female)": ["af_heart"]}


class TestLocalAudioPipeline(unittest.TestCase):
    def test_run_tts_generation_writes_audio_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            audio_dir = Path(temp_dir) / "audio"
            previous = {
                "DATABASE_BACKEND": os.environ.get("DATABASE_BACKEND"),
                "SQLITE_DB_PATH": os.environ.get("SQLITE_DB_PATH"),
                "AUDIO_DIR": os.environ.get("AUDIO_DIR"),
            }

            os.environ["DATABASE_BACKEND"] = "sqlite"
            os.environ["SQLITE_DB_PATH"] = str(db_path)
            os.environ["AUDIO_DIR"] = str(audio_dir)

            try:
                for module_name in [
                    "src.api.config",
                    "src.api.database",
                    "src.api.routes.audio",
                ]:
                    sys.modules.pop(module_name, None)

                database = importlib.import_module("src.api.database")
                audio = importlib.import_module("src.api.routes.audio")
                database.init_db()

                with database.get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO novels (slug, title, chapter_count, data_path, source_toc_url)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        ("test-novel", "Test Novel", 1, str(Path(temp_dir) / "output"), "https://example.com/novel"),
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

                with patch.object(audio, "get_tts_provider", return_value=FakeProvider()):
                    audio.run_tts_generation(
                        "test-novel",
                        1,
                        "Hello world.\n\nAnother sentence.",
                        "af_heart",
                        "test-novel_1",
                    )

                wav_path = audio_dir / "test-novel" / "Chapter_0001.wav"
                timing_path = audio_dir / "test-novel" / "Chapter_0001_timing.json"
                self.assertTrue(wav_path.exists())
                self.assertTrue(timing_path.exists())

                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    chapter_audio = conn.execute(
                        "SELECT status, audio_url FROM chapter_audio WHERE novel_slug = ? AND chapter_number = ?",
                        ("test-novel", 1),
                    ).fetchone()
                    timing_count = conn.execute(
                        "SELECT COUNT(*) FROM audio_timings WHERE novel_slug = ? AND chapter_number = ?",
                        ("test-novel", 1),
                    ).fetchone()[0]
                finally:
                    conn.close()

                self.assertEqual(chapter_audio["status"], "completed")
                self.assertEqual(chapter_audio["audio_url"], "/audio/test-novel/Chapter_0001.wav")
                self.assertGreaterEqual(timing_count, 1)
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

                for module_name in [
                    "src.api.config",
                    "src.api.database",
                    "src.api.routes.audio",
                ]:
                    sys.modules.pop(module_name, None)


if __name__ == "__main__":
    unittest.main()
