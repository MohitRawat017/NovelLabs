"""
TTS Integration Test Suite
Tests connectivity between Render Backend and Lightning AI TTS Service

Run with: python tests/test_tts_integration.py

Environment Variables Required:
- DATABASE_URL: PostgreSQL connection string
- TTS_SERVICE_URL: Lightning AI TTS service URL (optional, defaults to localhost:8002)
"""

import os
import sys
import time
import httpx
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Configuration
API_URL = os.getenv("API_URL", "https://novellabs.onrender.com/api")
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://localhost:8002")

# Test results tracker
passed_count = 0
failed_count = 0
errors_list = []


def test_passed(name, details=""):
    global passed_count
    passed_count += 1
    print(f"  ✅ {name}" + (f" - {details}" if details else ""))


def test_failed(name, error):
    global failed_count
    failed_count += 1
    errors_list.append(f"{name}: {error}")
    print(f"  ❌ {name}: {error}")


def test_skipped(name, reason):
    print(f"  ⏭️  {name}: {reason}")


# ==================== BACKEND API TESTS ====================

def test_backend_health():
    """Test if Render backend is reachable"""
    print("\n📡 Testing Backend (Render) Connection...")
    
    # Try the root endpoint first (without /api)
    base_url = API_URL.replace("/api", "")
    
    try:
        response = httpx.get(f"{base_url}/", timeout=30)  # Longer timeout for cold start
        if response.status_code == 200:
            test_passed("Backend health check", f"Status: {response.status_code}")
            return True
        else:
            # Try the /api endpoint
            response = httpx.get(f"{API_URL}/health", timeout=10)
            if response.status_code == 200:
                test_passed("Backend health check", f"Status: {response.status_code}")
                return True
            test_failed("Backend health check", f"Status: {response.status_code}")
            return False
    except httpx.ConnectError:
        test_failed("Backend health check", f"Cannot connect to {API_URL}")
        return False
    except httpx.ReadTimeout:
        test_failed("Backend health check", "Request timed out (Render may be waking up)")
        print("    💡 Try again in 30-60 seconds")
        return False
    except Exception as e:
        test_failed("Backend health check", str(e))
        return False


def test_backend_novels():
    """Test if novels endpoint works"""
    try:
        response = httpx.get(f"{API_URL}/novels", timeout=10)
        if response.status_code == 200:
            data = response.json()
            count = data.get("total", len(data.get("novels", [])))
            test_passed("Backend novels endpoint", f"Found {count} novels")
            return True
        else:
            test_failed("Backend novels endpoint", f"Status: {response.status_code}")
            return False
    except Exception as e:
        test_failed("Backend novels endpoint", str(e))
        return False


def test_backend_chapter_content():
    """Test if chapter content can be fetched"""
    try:
        # Try to get chapter 1 of any novel
        novels_resp = httpx.get(f"{API_URL}/novels", timeout=10)
        if novels_resp.status_code != 200:
            test_skipped("Backend chapter content", "No novels available")
            return False
        
        novels = novels_resp.json().get("novels", [])
        if not novels:
            test_skipped("Backend chapter content", "No novels in database")
            return False
        
        slug = novels[0]["slug"]
        response = httpx.get(f"{API_URL}/chapters/novel/{slug}/1", timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            has_content = bool(data.get("content"))
            test_passed("Backend chapter content", f"Chapter has content: {has_content}")
            return has_content
        else:
            test_failed("Backend chapter content", f"Status: {response.status_code}")
            return False
    except Exception as e:
        test_failed("Backend chapter content", str(e))
        return False


# ==================== TTS SERVICE TESTS ====================

def test_tts_health():
    """Test if Lightning AI TTS service is reachable"""
    print("\n🎤 Testing TTS Service (Lightning AI) Connection...")
    
    try:
        response = httpx.get(f"{TTS_SERVICE_URL}/", timeout=30)
        if response.status_code == 200:
            data = response.json()
            model_loaded = data.get("model_loaded", False)
            gpu_available = data.get("gpu_available", False)
            test_passed("TTS health check", f"Model loaded: {model_loaded}, GPU: {gpu_available}")
            return model_loaded
        else:
            test_failed("TTS health check", f"Status: {response.status_code}")
            return False
    except httpx.ConnectError:
        test_failed("TTS health check", f"Cannot connect to {TTS_SERVICE_URL}")
        print(f"    💡 Make sure TTS service is running at {TTS_SERVICE_URL}")
        return False
    except httpx.ReadTimeout:
        test_failed("TTS health check", "Request timed out (model may still be loading)")
        return False
    except Exception as e:
        test_failed("TTS health check", str(e))
        return False


def test_tts_voices():
    """Test if TTS voices endpoint works"""
    try:
        response = httpx.get(f"{TTS_SERVICE_URL}/voices", timeout=10)
        if response.status_code == 200:
            voices = response.json()
            total = sum(len(v) for v in voices.values())
            test_passed("TTS voices endpoint", f"Found {total} voices")
            return True
        else:
            test_failed("TTS voices endpoint", f"Status: {response.status_code}")
            return False
    except Exception as e:
        test_failed("TTS voices endpoint", str(e))
        return False


def test_tts_synthesize():
    """Test TTS synthesis (requires model to be loaded)"""
    try:
        payload = {
            "text": "Hello, this is a test of the text to speech system.",
            "voice": "af_heart",
            "segment_id": "test_segment_001"
        }
        
        print("    ⏳ Synthesizing test audio (may take 10-30s)...")
        response = httpx.post(
            f"{TTS_SERVICE_URL}/synthesize",
            json=payload,
            timeout=60  # Longer timeout for synthesis
        )
        
        if response.status_code == 200:
            data = response.json()
            audio_url = data.get("audio_url", "")
            duration = data.get("duration", 0)
            test_passed("TTS synthesize endpoint", f"Duration: {duration:.2f}s, URL: {audio_url[:50]}...")
            return audio_url
        else:
            error = response.json().get("detail", response.text)
            test_failed("TTS synthesize endpoint", f"Status: {response.status_code}, Error: {error}")
            return None
    except httpx.ReadTimeout:
        test_failed("TTS synthesize endpoint", "Request timed out (synthesis may be slow)")
        return None
    except Exception as e:
        test_failed("TTS synthesize endpoint", str(e))
        return None


def test_audio_url_accessible(audio_url: str):
    """Test if generated audio URL is accessible"""
    if not audio_url:
        test_skipped("Audio URL accessible", "No audio URL to test")
        return False
    
    try:
        response = httpx.head(audio_url, timeout=10, follow_redirects=True)
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            test_passed("Audio URL accessible", f"Content-Type: {content_type}")
            return True
        else:
            test_failed("Audio URL accessible", f"Status: {response.status_code}")
            return False
    except Exception as e:
        test_failed("Audio URL accessible", str(e))
        return False


# ==================== INTEGRATION TESTS ====================

def test_backend_calls_tts():
    """Test if backend can call TTS service through its API"""
    print("\n🔗 Testing Backend ↔ TTS Integration...")
    
    try:
        # Get voices through backend (which proxies to TTS)
        response = httpx.get(f"{API_URL}/audio/voices", timeout=15)
        if response.status_code == 200:
            voices = response.json()
            total = sum(len(v) for v in voices.values())
            test_passed("Backend → TTS voices proxy", f"Found {total} voices")
            return True
        else:
            test_failed("Backend → TTS voices proxy", f"Status: {response.status_code}")
            return False
    except Exception as e:
        test_failed("Backend → TTS voices proxy", str(e))
        return False


def test_audio_status_endpoint():
    """Test audio status endpoint"""
    try:
        # Check status for a chapter
        novels_resp = httpx.get(f"{API_URL}/novels", timeout=10)
        if novels_resp.status_code != 200:
            test_skipped("Audio status endpoint", "No novels available")
            return False
        
        novels = novels_resp.json().get("novels", [])
        if not novels:
            test_skipped("Audio status endpoint", "No novels in database")
            return False
        
        slug = novels[0]["slug"]
        response = httpx.get(f"{API_URL}/audio/status/{slug}/1", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            exists = data.get("exists", False)
            generating = data.get("generating", False)
            test_passed("Audio status endpoint", f"Exists: {exists}, Generating: {generating}")
            return True
        elif response.status_code == 404:
            test_passed("Audio status endpoint", "Chapter not found (expected)")
            return True
        else:
            test_failed("Audio status endpoint", f"Status: {response.status_code}")
            return False
    except Exception as e:
        test_failed("Audio status endpoint", str(e))
        return False


# ==================== MAIN ====================

def print_summary():
    print("\n" + "=" * 60)
    print(f"📊 TEST SUMMARY: {passed_count} passed, {failed_count} failed")
    print("=" * 60)
    
    if errors_list:
        print("\n❌ Failures:")
        for error in errors_list:
            print(f"   • {error}")
    
    if failed_count == 0:
        print("\n🎉 All tests passed! Backend and TTS service are connected properly.")
    else:
        print("\n💡 Tips:")
        print("   • Make sure TTS_SERVICE_URL is set correctly")
        print("   • Check if Lightning AI service is running")
        print("   • Verify R2 credentials are configured on TTS service")


def main():
    print("=" * 60)
    print("  TTS INTEGRATION TEST SUITE")
    print("=" * 60)
    print(f"\nBackend URL:     {API_URL}")
    print(f"TTS Service URL: {TTS_SERVICE_URL}")
    
    # Backend tests
    backend_ok = test_backend_health()
    if backend_ok:
        test_backend_novels()
        test_backend_chapter_content()
    
    # TTS service tests
    tts_ok = test_tts_health()
    if tts_ok:
        test_tts_voices()
        audio_url = test_tts_synthesize()
        if audio_url:
            test_audio_url_accessible(audio_url)
    
    # Integration tests
    if backend_ok:
        test_backend_calls_tts()
        test_audio_status_endpoint()
    
    print_summary()
    
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
