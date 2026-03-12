"""
Local API + TTS smoke checks.

Run after starting the backend locally:
    python tests/test_tts_integration.py
Optional full generation:
    python tests/test_tts_integration.py --full --slug renegade-immortal --chapter 1
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

API_URL = "http://localhost:8001/api"

passed_count = 0
failed_count = 0
errors_list: list[str] = []


def test_passed(name: str, details: str = ""):
    global passed_count
    passed_count += 1
    print(f"  PASS {name}" + (f" - {details}" if details else ""))


def test_failed(name: str, error: str):
    global failed_count
    failed_count += 1
    errors_list.append(f"{name}: {error}")
    print(f"  FAIL {name}: {error}")


def test_skipped(name: str, reason: str):
    print(f"  SKIP {name}: {reason}")


def get_json(path: str, timeout: int = 15):
    response = httpx.get(f"{API_URL}{path}", timeout=timeout)
    response.raise_for_status()
    return response.json()


def post_json(path: str, timeout: int = 30):
    response = httpx.post(f"{API_URL}{path}", timeout=timeout)
    response.raise_for_status()
    return response.json()


def test_backend_health() -> bool:
    try:
        data = get_json("/health", timeout=10)
        test_passed("Backend health", str(data))
        return True
    except Exception as exc:
        test_failed("Backend health", str(exc))
        return False


def test_tts_health() -> bool:
    try:
        data = get_json("/audio/health", timeout=20)
        if data.get("tts_available"):
            test_passed("Local TTS health", f"device={data.get('device')}")
            return True
        test_failed("Local TTS health", data.get("error", "TTS unavailable"))
        return False
    except Exception as exc:
        test_failed("Local TTS health", str(exc))
        return False


def test_tts_voices() -> bool:
    try:
        data = get_json("/audio/voices")
        total = sum(len(group) for group in data.values())
        test_passed("Voice list", f"{total} voices")
        return True
    except Exception as exc:
        test_failed("Voice list", str(exc))
        return False


def test_novel_listing() -> list[dict]:
    try:
        data = get_json("/novels")
        novels = data.get("novels", [])
        test_passed("Novel listing", f"{len(novels)} novels")
        return novels
    except Exception as exc:
        test_failed("Novel listing", str(exc))
        return []


def test_audio_status(slug: str, chapter: int) -> bool:
    try:
        data = get_json(f"/audio/status/{slug}/{chapter}")
        test_passed("Audio status", f"status={data.get('status')}")
        return True
    except Exception as exc:
        test_failed("Audio status", str(exc))
        return False


def test_full_audio_generation(slug: str, chapter: int) -> bool:
    try:
        data = post_json(f"/audio/generate/{slug}/{chapter}?voice=af_heart")
        test_passed("Generation trigger", data.get("status", "ok"))
    except Exception as exc:
        test_failed("Generation trigger", str(exc))
        return False

    for _ in range(60):
        time.sleep(5)
        try:
            status = get_json(f"/audio/status/{slug}/{chapter}")
        except Exception as exc:
            test_failed("Generation polling", str(exc))
            return False

        if status.get("status") == "completed":
            test_passed("Full audio generation", f"duration={status.get('duration')}")
            return True
        if status.get("status") == "failed":
            test_failed("Full audio generation", status.get("error", "unknown error"))
            return False

    test_failed("Full audio generation", "timed out")
    return False


def print_summary():
    print("\n" + "=" * 50)
    print(f"SUMMARY: {passed_count} passed, {failed_count} failed")
    if errors_list:
        for error in errors_list:
            print(f"  - {error}")
    print("=" * 50)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--slug")
    parser.add_argument("--chapter", type=int, default=1)
    args = parser.parse_args()

    backend_ok = test_backend_health()
    if not backend_ok:
        print_summary()
        return 1

    tts_ok = test_tts_health()
    test_tts_voices()
    novels = test_novel_listing()

    slug = args.slug or (novels[0]["slug"] if novels else None)
    if not slug:
        test_skipped("Audio status", "no local novels found")
        print_summary()
        return 0 if tts_ok else 1

    test_audio_status(slug, args.chapter)

    if args.full:
        test_full_audio_generation(slug, args.chapter)
    else:
        test_skipped("Full audio generation", "run with --full to synthesize a chapter")

    print_summary()
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
