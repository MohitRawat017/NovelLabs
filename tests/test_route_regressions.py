from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


MODULES_TO_RESET = [
    "src.api",
    "src.api.config",
    "src.api.database",
    "src.api.routes",
    "src.api.routes.audio",
    "src.api.routes.chapters",
    "src.api.routes.novels",
    "src.api.routes.scraper",
    "src.api.main",
]


def reset_modules():
    for module_name in MODULES_TO_RESET:
        sys.modules.pop(module_name, None)


class TestRouteRegressions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        base = Path(self.temp_dir.name)
        self.db_path = base / "app.db"
        self.audio_dir = base / "audio"
        self.previous = {
            "NOVELLABS_ENV_FILE": os.environ.get("NOVELLABS_ENV_FILE"),
            "DATABASE_BACKEND": os.environ.get("DATABASE_BACKEND"),
            "SQLITE_DB_PATH": os.environ.get("SQLITE_DB_PATH"),
            "AUDIO_DIR": os.environ.get("AUDIO_DIR"),
            "SCRAPER_ENABLED": os.environ.get("SCRAPER_ENABLED"),
            "TTS_PROVIDER": os.environ.get("TTS_PROVIDER"),
        }

        self.env_path = base / ".env"
        self.env_path.write_text(
            "\n".join(
                [
                    "DATABASE_BACKEND=sqlite",
                    f"SQLITE_DB_PATH={self.db_path}",
                    f"AUDIO_DIR={self.audio_dir}",
                    "SCRAPER_ENABLED=false",
                    "TTS_PROVIDER=kokoro",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        os.environ["NOVELLABS_ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_BACKEND"] = "sqlite"
        os.environ["SQLITE_DB_PATH"] = str(self.db_path)
        os.environ["AUDIO_DIR"] = str(self.audio_dir)
        os.environ["SCRAPER_ENABLED"] = "false"
        os.environ["TTS_PROVIDER"] = "kokoro"

        reset_modules()
        self.database = importlib.import_module("src.api.database")
        self.main = importlib.import_module("src.api.main")
        self.database.init_db()

        with self.database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO novels (slug, title, chapter_count, data_path, source_toc_url)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "route-regression-novel",
                    "Route Regression Novel",
                    1,
                    str(base / "output" / "route-regression-novel"),
                    "https://novelhi.com/s/index/Route-Regression-Novel",
                ),
            )
            cursor.execute("SELECT id FROM novels WHERE slug = ?", ("route-regression-novel",))
            self.novel_id = cursor.fetchone()["id"]

    def tearDown(self):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_modules()

    def test_novels_endpoint_returns_payload(self):
        with TestClient(self.main.app) as client:
            response = client.get("/api/novels")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("novels", payload)
        self.assertIn("total", payload)
        self.assertIsInstance(payload["novels"], list)
        self.assertIsInstance(payload["total"], int)

    def test_localhost_preflight_is_allowed_in_sqlite_mode(self):
        with TestClient(self.main.app) as client:
            response = client.options(
                "/api/novels",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5173")
    def test_dynamic_localhost_port_preflight_is_allowed_in_sqlite_mode(self):
        with TestClient(self.main.app) as client:
            response = client.options(
                "/api/novels",
                headers={
                    "Origin": "http://localhost:5174",
                    "Access-Control-Request-Method": "GET",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5174")

    def test_scraper_jobs_returns_503_when_disabled(self):
        with TestClient(self.main.app) as client:
            response = client.get("/api/scraper/jobs")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "scraper_disabled")

    def test_scraper_start_returns_503_when_disabled(self):
        with TestClient(self.main.app) as client:
            response = client.post(
                "/api/scraper/start",
                json={
                    "toc_url": "https://novelhi.com/s/index/Route-Regression-Novel",
                    "start_chapter": 1,
                    "end_chapter": 1,
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "scraper_disabled")

    def test_update_novel_returns_503_when_scraper_disabled(self):
        with TestClient(self.main.app) as client:
            response = client.post("/api/novels/route-regression-novel/update")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "scraper_disabled")

    def test_audio_status_prefers_existing_audio_file_over_stale_generating_row(self):
        audio_dir = self.audio_dir / "route-regression-novel"
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / "Chapter_0001.wav").write_bytes(b"RIFFstub")

        with self.database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chapter_audio (novel_slug, chapter_number, provider, voice, status, audio_url, duration, progress, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    "route-regression-novel",
                    1,
                    "kokoro",
                    "af_heart",
                    "generating",
                    None,
                    None,
                    42.0,
                ),
            )

        with TestClient(self.main.app) as client:
            response = client.get("/api/audio/status/route-regression-novel/1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["exists"])
        self.assertFalse(payload["generating"])
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["audio_url"], "/audio/route-regression-novel/Chapter_0001.wav")

    def test_audio_status_returns_live_chunk_progress(self):
        audio_module = importlib.import_module("src.api.routes.audio")
        audio_module.tts_jobs["route-regression-novel_1"] = {
            "status": "generating",
            "progress": 37.5,
            "message": "Synthesizing chunk 3 of 8",
            "current_chunk": 3,
            "completed_chunks": 2,
            "total_chunks": 8,
            "started_at": "2026-03-12T00:00:00",
            "updated_at": "2026-03-12T00:00:10",
            "started_monotonic": 1.0,
        }

        with TestClient(self.main.app) as client:
            response = client.get("/api/audio/status/route-regression-novel/1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["generating"])
        self.assertEqual(payload["current_chunk"], 3)
        self.assertEqual(payload["completed_chunks"], 2)
        self.assertEqual(payload["total_chunks"], 8)
        self.assertEqual(payload["message"], "Synthesizing chunk 3 of 8")
        self.assertEqual(payload["progress"], 37.5)
        self.assertIn("estimated_remaining_seconds", payload)

    def test_audio_status_prefers_live_job_progress_over_stale_db_progress(self):
        audio_module = importlib.import_module("src.api.routes.audio")
        audio_module.tts_jobs["route-regression-novel_1"] = {
            "status": "generating",
            "progress": 63.0,
            "message": "Processed 5 of 8 chunks",
            "current_chunk": 6,
            "completed_chunks": 5,
            "total_chunks": 8,
            "started_at": "2026-03-12T00:00:00",
            "updated_at": "2026-03-12T00:00:20",
            "started_monotonic": 1.0,
            "current_chunk_started_monotonic": None,
        }

        with self.database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chapter_audio (novel_slug, chapter_number, provider, voice, status, audio_url, duration, progress, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    "route-regression-novel",
                    1,
                    "kokoro",
                    "af_heart",
                    "generating",
                    None,
                    None,
                    10.0,
                ),
            )

        with TestClient(self.main.app) as client:
            response = client.get("/api/audio/status/route-regression-novel/1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "generating")
        self.assertEqual(payload["progress"], 63.0)
        self.assertEqual(payload["completed_chunks"], 5)

    def test_audio_status_hides_stale_restart_failure_error(self):
        with self.database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chapter_audio (novel_slug, chapter_number, provider, voice, status, audio_url, duration, progress, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    "route-regression-novel",
                    8,
                    "kokoro",
                    "af_heart",
                    "failed",
                    None,
                    None,
                    55.0,
                    "Server restarted while generation was in progress",
                ),
            )

        with TestClient(self.main.app) as client:
            response = client.get("/api/audio/status/route-regression-novel/8")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["exists"])
        self.assertFalse(payload["generating"])
        self.assertEqual(payload["status"], "cancelled")
        self.assertEqual(payload["progress"], 0)
        self.assertIsNone(payload["error"])

    def test_chapter_list_includes_audio_provider_metadata(self):
        with self.database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chapters (novel_id, chapter_number, title, content_path, word_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.novel_id,
                    7,
                    "Chapter 7",
                    str(Path(self.temp_dir.name) / "output" / "chapter_7.txt"),
                    1200,
                ),
            )
            cursor.execute(
                """
                INSERT INTO chapter_audio (novel_slug, chapter_number, provider, voice, status, audio_url, duration, progress, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    "route-regression-novel",
                    7,
                    "qwen3",
                    "novel-default",
                    "completed",
                    "/audio/route-regression-novel/Chapter_0007.wav",
                    12.4,
                    100.0,
                ),
            )

        with TestClient(self.main.app) as client:
            response = client.get("/api/chapters/novel/route-regression-novel")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        chapter = payload["chapters"][0]
        self.assertTrue(chapter["has_audio"])
        self.assertEqual(chapter["audio_provider"], "qwen3")
        self.assertEqual(chapter["audio_status"], "completed")

    def test_audio_jobs_endpoint_returns_live_progress(self):
        with self.database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chapters (novel_id, chapter_number, title, content_path, word_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.novel_id,
                    3,
                    "A Loud Chapter",
                    str(Path(self.temp_dir.name) / "output" / "chapter_3.txt"),
                    800,
                ),
            )
            cursor.execute(
                """
                INSERT INTO chapter_audio (novel_slug, chapter_number, provider, voice, status, audio_url, duration, progress, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    "route-regression-novel",
                    3,
                    "kokoro",
                    "af_heart",
                    "generating",
                    None,
                    None,
                    11.0,
                ),
            )

        audio_module = importlib.import_module("src.api.routes.audio")
        audio_module.tts_jobs["route-regression-novel_3"] = {
            "status": "generating",
            "progress": 58.5,
            "message": "Processed 4 of 7 chunks",
            "current_chunk": 5,
            "completed_chunks": 4,
            "total_chunks": 7,
            "started_at": "2026-03-12T00:00:00",
            "updated_at": "2026-03-12T00:00:15",
            "started_monotonic": 1.0,
        }

        with TestClient(self.main.app) as client:
            response = client.get("/api/audio/jobs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        job = payload["jobs"][0]
        self.assertEqual(job["novel_slug"], "route-regression-novel")
        self.assertEqual(job["chapter_number"], 3)
        self.assertEqual(job["chapter_title"], "A Loud Chapter")
        self.assertEqual(job["progress"], 58.5)
        self.assertEqual(job["completed_chunks"], 4)
        self.assertEqual(job["total_chunks"], 7)
        self.assertEqual(job["status"], "generating")

    def test_audio_pause_and_resume_routes_update_live_job_and_db(self):
        audio_module = importlib.import_module("src.api.routes.audio")
        audio_module.tts_jobs["route-regression-novel_1"] = {
            "status": "generating",
            "provider": "kokoro",
            "voice": "af_heart",
            "progress": 44.5,
            "message": "Synthesizing chunk 2 of 5",
            "current_chunk": 2,
            "completed_chunks": 1,
            "total_chunks": 5,
            "started_at": "2026-03-12T00:00:00",
            "updated_at": "2026-03-12T00:00:05",
            "started_monotonic": 1.0,
        }

        with TestClient(self.main.app) as client:
            pause_response = client.post("/api/audio/pause/route-regression-novel/1")

            self.assertEqual(pause_response.status_code, 200)
            self.assertEqual(pause_response.json()["status"], "paused")
            self.assertEqual(audio_module.tts_jobs["route-regression-novel_1"]["status"], "paused")

            resume_response = client.post("/api/audio/resume/route-regression-novel/1")

        self.assertEqual(resume_response.status_code, 200)
        self.assertEqual(resume_response.json()["status"], "generating")
        self.assertEqual(audio_module.tts_jobs["route-regression-novel_1"]["status"], "generating")

        with self.database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT status, progress, provider, voice
                FROM chapter_audio
                WHERE novel_slug = ? AND chapter_number = ?
                """,
                ("route-regression-novel", 1),
            )
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "generating")
        self.assertEqual(row["provider"], "kokoro")
        self.assertEqual(row["voice"], "af_heart")
        self.assertGreaterEqual(float(row["progress"]), 44.5)

    def test_audio_cancel_route_marks_stale_db_job_cancelled(self):
        with self.database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chapter_audio (novel_slug, chapter_number, provider, voice, status, audio_url, duration, progress, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    "route-regression-novel",
                    9,
                    "kokoro",
                    "af_heart",
                    "pending",
                    None,
                    None,
                    31.0,
                ),
            )

        with TestClient(self.main.app) as client:
            response = client.post("/api/audio/cancel/route-regression-novel/9")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")

        with self.database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT status, error, progress
                FROM chapter_audio
                WHERE novel_slug = ? AND chapter_number = ?
                """,
                ("route-regression-novel", 9),
            )
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "cancelled")
        self.assertEqual(row["error"], "Cancelled by user")
        self.assertGreaterEqual(float(row["progress"]), 31.0)

    def test_audio_pause_route_returns_404_without_live_job(self):
        with TestClient(self.main.app) as client:
            response = client.post("/api/audio/pause/route-regression-novel/77")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Live audio job not found", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
