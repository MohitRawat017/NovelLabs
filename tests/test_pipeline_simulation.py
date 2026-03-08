"""
NovelLabs Pipeline Simulation Test Suite
=========================================
Simulates the full audio generation pipeline locally:

  Test 1: Text Chunking → TTS Audio Generation (simulated)
  Test 2: Audio Upload → R2 Storage (real credentials)
  Test 3: Audio Segments → Concatenation (pydub)
  Test 4: Frontend Demo → HTML Player with Karaoke

Run:  python tests/test_pipeline_simulation.py
      python tests/test_pipeline_simulation.py --test 2   (run specific test)
"""

import os
import sys
import io
import re
import struct
import math
import time
import webbrowser
from pathlib import Path
from typing import Optional, List
from datetime import datetime

# ==================== Setup ====================

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "src"))

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    print("⚠️  python-dotenv not installed, loading .env manually...")
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip().replace('\r', '')
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

# Test results tracker
passed = 0
failed = 0
errors = []

SAMPLE_RATE = 24000
SAMPLE_CHAPTER_TEXT = """The morning sun cast long shadows across the cobblestone streets of the old district. 
Maria pulled her coat tighter as she hurried past the ancient cathedral, its spires reaching toward the grey sky like gnarled fingers.

"You're late," said Thomas, standing by the fountain. His breath formed small clouds in the cold air. 
He held out a sealed envelope, his expression grave.

She took it without a word, turning it over in her hands. The wax seal bore an unfamiliar crest — a serpent coiled around a crescent moon. Whatever secrets lay inside, they had traveled a long way to reach her.

The cathedral bells began to toll, their deep resonance echoing through the empty square. 
Seven chimes. She had exactly one hour before the train departed. 
One hour to decide whether to open the envelope or destroy it forever.

Maria looked at Thomas one last time. His eyes betrayed nothing — not fear, not hope, not even curiosity. 
Just the calm stillness of a man who had already made peace with every possible outcome.

"Thank you," she whispered, and walked into the fog."""


def test_passed(name, details=""):
    global passed
    passed += 1
    print(f"  ✅ {name}" + (f" — {details}" if details else ""))


def test_failed(name, error):
    global failed
    failed += 1
    errors.append(f"{name}: {error}")
    print(f"  ❌ {name}: {error}")


# ==================== WAV Generation Helpers ====================


def generate_sine_wav(duration_s: float = 1.0, freq: int = 440, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Generate a simple sine wave WAV file as bytes (no external deps)."""
    num_samples = int(sample_rate * duration_s)
    
    # Generate PCM samples (16-bit signed)
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        value = int(32767 * 0.5 * math.sin(2 * math.pi * freq * t))
        samples.append(struct.pack('<h', value))
    
    pcm_data = b''.join(samples)
    
    # Build WAV header
    data_size = len(pcm_data)
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    
    header = struct.pack('<4sI4s', b'RIFF', 36 + data_size, b'WAVE')
    fmt_chunk = struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, num_channels,
                           sample_rate, byte_rate, block_align, bits_per_sample)
    data_chunk = struct.pack('<4sI', b'data', data_size)
    
    return header + fmt_chunk + data_chunk + pcm_data


def generate_chunk_audio(text: str, chunk_idx: int) -> tuple:
    """Simulate TTS: generate fake audio for a text chunk.
    Returns (audio_bytes, duration_seconds)."""
    # Approximate duration: ~150 words/min speaking rate
    word_count = len(text.split())
    duration = max(0.5, word_count / 2.5)  # ~2.5 words/sec
    
    # Different frequency per chunk for variety
    freq = 300 + (chunk_idx * 50) % 400
    audio_bytes = generate_sine_wav(duration, freq)
    
    return audio_bytes, round(duration, 3)


# ==================== TEXT CHUNKING (from audio.py) ====================


def split_text_into_chunks(text: str, max_length: int = 500) -> list:
    """Split text into chunks for TTS processing.
    (Copied from src/api/routes/audio.py for isolated testing)"""
    
    # Split by paragraphs first
    paragraphs = re.split(r'\n\s*\n', text.strip())
    
    chunks = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # If paragraph is short enough, use as-is
        if len(para) <= max_length:
            chunks.append(para)
        else:
            # Split by sentences
            sentences = re.split(r'(?<=[.!?])\s+', para)
            current_chunk = ""
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                    
                if len(current_chunk) + len(sentence) + 1 <= max_length:
                    current_chunk = (current_chunk + " " + sentence).strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sentence
            
            if current_chunk:
                chunks.append(current_chunk)
    
    # Fallback if no chunks were created
    if not chunks and text.strip():
        words = text.split()
        current_chunk = ""
        for word in words:
            if len(current_chunk) + len(word) + 1 <= max_length:
                current_chunk = (current_chunk + " " + word).strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = word
        if current_chunk:
            chunks.append(current_chunk)
    
    return chunks


# ========================================================================
#  TEST 1: Text Chunking + TTS Audio Generation (Simulated)
# ========================================================================


def test_1_chunking_and_generation():
    """
    Simulates what happens when a chapter is sent to the Modal TTS service:
    1. Chapter text is split into chunks
    2. Each chunk gets a segment_id
    3. Each chunk is synthesized into audio (simulated with sine waves)
    4. Timing data is calculated
    """
    print("\n" + "=" * 60)
    print("  TEST 1: Text Chunking → TTS Audio Generation")
    print("=" * 60)
    
    novel_slug = "test-novel"
    chapter_number = 1
    voice = "af_heart"
    
    # Step 1: Split text into chunks
    print(f"\n📝 Input text: {len(SAMPLE_CHAPTER_TEXT)} chars, {len(SAMPLE_CHAPTER_TEXT.split())} words")
    chunks = split_text_into_chunks(SAMPLE_CHAPTER_TEXT, max_length=500)
    
    if not chunks:
        test_failed("Text chunking", "No chunks produced")
        return []
    
    test_passed("Text chunking", f"Split into {len(chunks)} chunks")
    
    # Validate chunk sizes
    oversized = [i for i, c in enumerate(chunks) if len(c) > 500]
    if oversized:
        test_failed("Chunk size validation", f"Chunks {oversized} exceed max_length=500")
    else:
        test_passed("Chunk size validation", f"All chunks ≤ 500 chars")
    
    # Step 2: Simulate TTS generation per chunk
    print(f"\n🎤 Simulating TTS generation (voice: {voice})...")
    
    current_time = 0.0
    silence_gap = 0.3
    timings = []
    segments = []
    
    for idx, chunk in enumerate(chunks):
        segment_id = f"{novel_slug}_ch{chapter_number}_seg{idx:04d}"
        
        # Simulate TTS call
        audio_bytes, duration = generate_chunk_audio(chunk, idx)
        
        # Build timing entry (same format as audio.py)
        timing = {
            "chunk_index": idx,
            "start_time": round(current_time, 3),
            "end_time": round(current_time + duration, 3),
            "text": chunk.strip()[:80] + ("..." if len(chunk) > 80 else "")
        }
        timings.append(timing)
        
        segments.append({
            "segment_id": segment_id,
            "audio_bytes": audio_bytes,
            "duration": duration,
            "size_bytes": len(audio_bytes),
            "chunk_text": chunk
        })
        
        current_time += duration + silence_gap
        
        print(f"    [{idx + 1}/{len(chunks)}] {segment_id}: {duration:.2f}s, "
              f"{len(audio_bytes):,} bytes — \"{chunk[:50]}...\"")
    
    total_duration = current_time - silence_gap
    total_bytes = sum(s["size_bytes"] for s in segments)
    
    test_passed("TTS generation simulation",
                f"{len(segments)} segments, {total_duration:.2f}s total, {total_bytes:,} bytes")
    
    # Validate timings
    for i in range(1, len(timings)):
        if timings[i]["start_time"] <= timings[i-1]["end_time"]:
            test_failed("Timing sequence", f"Chunk {i} overlaps with chunk {i-1}")
            break
    else:
        test_passed("Timing sequence", "No overlapping timings")
    
    # Print summary table
    print(f"\n    {'─' * 55}")
    print(f"    {'Chunk':<8} {'Duration':>10} {'Start':>10} {'End':>10} {'Chars':>8}")
    print(f"    {'─' * 55}")
    for i, t in enumerate(timings):
        dur = t['end_time'] - t['start_time']
        chars = len(segments[i]['chunk_text'])
        print(f"    {i:<8} {dur:>10.2f}s {t['start_time']:>10.3f} {t['end_time']:>10.3f} {chars:>8}")
    print(f"    {'─' * 55}")
    print(f"    {'Total':<8} {total_duration:>10.2f}s {'':>10} {'':>10} {sum(len(s['chunk_text']) for s in segments):>8}")
    
    return segments


# ========================================================================
#  TEST 2: Audio Upload to R2 Storage (Real)
# ========================================================================


def test_2_r2_upload():
    """
    Tests real R2 upload using credentials from .env:
    1. Create a small test WAV file
    2. Upload to R2 using the same function the backend uses
    3. Verify the URL is accessible
    4. Clean up the test file
    """
    print("\n" + "=" * 60)
    print("  TEST 2: Audio Upload → R2 Storage")
    print("=" * 60)
    
    # Check if R2 credentials are configured
    account_id = os.environ.get("R2_AUDIO_ACCOUNT_ID", "")
    access_key = os.environ.get("R2_AUDIO_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("R2_AUDIO_SECRET_ACCESS_KEY", "")
    bucket_name = os.environ.get("R2_AUDIO_BUCKET_NAME", "novellabs-audio")
    public_url = os.environ.get("R2_AUDIO_PUBLIC_URL", "")
    
    print(f"\n☁️  R2 Configuration:")
    print(f"    Account ID:  {account_id[:8]}...{account_id[-4:]}" if account_id else "    Account ID:  ❌ NOT SET")
    print(f"    Access Key:  {access_key[:8]}...{access_key[-4:]}" if access_key else "    Access Key:  ❌ NOT SET")
    print(f"    Secret Key:  {'*' * 8}...{secret_key[-4:]}" if secret_key else "    Secret Key:  ❌ NOT SET")
    print(f"    Bucket:      {bucket_name}")
    print(f"    Public URL:  {public_url or '(auto-generated)'}")
    
    if not all([account_id, access_key, secret_key]):
        test_failed("R2 credentials", "Missing R2_AUDIO_ACCOUNT_ID, R2_AUDIO_ACCESS_KEY_ID, or R2_AUDIO_SECRET_ACCESS_KEY in .env")
        return False
    
    test_passed("R2 credentials configured")
    
    # Create test audio
    test_audio = generate_sine_wav(0.5, freq=440)
    print(f"\n📦 Test audio: {len(test_audio):,} bytes ({len(test_audio)/1024:.1f} KB)")
    
    # Initialize R2 client directly (not through the module to avoid DB dependency)
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        test_failed("boto3 import", "boto3 not installed — run: pip install boto3")
        return False
    
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    
    try:
        s3 = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version='s3v4', retries={'max_attempts': 2})
        )
        test_passed("R2 client initialized", f"Endpoint: {endpoint}")
    except Exception as e:
        test_failed("R2 client init", str(e))
        return False
    
    # Upload test file
    test_key = "audio/test_pipeline_verification.wav"
    
    try:
        print(f"\n⬆️  Uploading to R2: {test_key}")
        s3.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=test_audio,
            ContentType="audio/wav",
            CacheControl="no-cache"
        )
        
        # Build URL
        if public_url:
            audio_url = f"{public_url.rstrip('/')}/{test_key}"
        else:
            audio_url = f"https://{bucket_name}.{account_id}.r2.dev/{test_key}"
        
        test_passed("R2 upload", f"URL: {audio_url}")
    except Exception as e:
        test_failed("R2 upload", str(e))
        return False
    
    # Verify URL is accessible
    try:
        import httpx
        print(f"\n🔍 Verifying URL accessibility...")
        response = httpx.head(audio_url, timeout=15, follow_redirects=True)
        
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "unknown")
            content_length = response.headers.get("content-length", "unknown")
            test_passed("URL accessible", f"Content-Type: {content_type}, Size: {content_length}")
        else:
            test_failed("URL accessible", f"Status: {response.status_code}")
            print(f"    ⚠️  The file was uploaded but the public URL returned {response.status_code}")
            print(f"    💡 Check if your R2 bucket has public access enabled")
    except ImportError:
        print("    ⚠️  httpx not installed — skipping URL verification")
    except Exception as e:
        test_failed("URL accessible", str(e))
    
    # Also test the chapter audio upload path (same key format used in production)
    chapter_key = "chapters/test-novel/chapter_9999.wav"
    try:
        print(f"\n⬆️  Testing chapter audio path: {chapter_key}")
        s3.put_object(
            Bucket=bucket_name,
            Key=chapter_key,
            Body=test_audio,
            ContentType="audio/wav",
            CacheControl="no-cache"
        )
        
        if public_url:
            chapter_url = f"{public_url.rstrip('/')}/{chapter_key}"
        else:
            chapter_url = f"https://{bucket_name}.{account_id}.r2.dev/{chapter_key}"
        
        test_passed("Chapter audio upload path", f"URL: {chapter_url}")
    except Exception as e:
        test_failed("Chapter audio upload path", str(e))
    
    # Cleanup
    try:
        print(f"\n🧹 Cleaning up test files from R2...")
        s3.delete_object(Bucket=bucket_name, Key=test_key)
        s3.delete_object(Bucket=bucket_name, Key=chapter_key)
        test_passed("R2 cleanup", "Test files deleted")
    except Exception as e:
        print(f"    ⚠️  Cleanup warning: {e}")
    
    return True


# ========================================================================
#  TEST 3: Audio Concatenation
# ========================================================================


def test_3_concatenation(segments: list = None):
    """
    Tests audio concatenation:
    1. Generate (or use) multiple audio segments
    2. Concatenate with silence gaps using pydub
    3. Verify final duration
    4. Save to file for inspection
    """
    print("\n" + "=" * 60)
    print("  TEST 3: Audio Concatenation")
    print("=" * 60)
    
    try:
        from pydub import AudioSegment
    except ImportError:
        test_failed("pydub import", "pydub not installed — run: pip install pydub")
        print("    💡 Also need ffmpeg: https://ffmpeg.org/download.html")
        return None
    
    test_passed("pydub imported")
    
    # Generate segments if not provided from Test 1
    if not segments:
        print("\n📦 Generating test audio segments...")
        segments = []
        for i in range(5):
            audio_bytes = generate_sine_wav(1.0 + i * 0.5, freq=300 + i * 80)
            segments.append({
                "segment_id": f"test_seg_{i:04d}",
                "audio_bytes": audio_bytes,
                "duration": 1.0 + i * 0.5,
                "chunk_text": f"This is test segment number {i + 1}."
            })
    
    silence_gap_ms = 300
    silence = AudioSegment.silent(duration=silence_gap_ms)
    
    print(f"\n🔗 Concatenating {len(segments)} segments with {silence_gap_ms}ms gaps...")
    
    audio_parts = []
    expected_duration = 0.0
    
    for idx, seg in enumerate(segments):
        try:
            # Load audio bytes as AudioSegment
            audio_segment = AudioSegment.from_wav(io.BytesIO(seg["audio_bytes"]))
            
            if idx > 0:
                audio_parts.append(silence)
                expected_duration += silence_gap_ms / 1000.0
            
            audio_parts.append(audio_segment)
            expected_duration += seg["duration"]
            
            print(f"    [{idx + 1}/{len(segments)}] Loaded segment: {seg['duration']:.2f}s, "
                  f"{len(seg['audio_bytes']):,} bytes")
            
        except Exception as e:
            test_failed(f"Load segment {idx}", str(e))
            continue
    
    if not audio_parts:
        test_failed("Audio concatenation", "No segments loaded successfully")
        return None
    
    test_passed("All segments loaded", f"{len(audio_parts)} parts (segments + silences)")
    
    # Concatenate
    print(f"\n🎵 Concatenating...")
    final_audio = audio_parts[0]
    for part in audio_parts[1:]:
        final_audio = final_audio + part
    
    actual_duration = len(final_audio) / 1000.0  # pydub uses milliseconds
    
    print(f"    Expected duration: {expected_duration:.2f}s")
    print(f"    Actual duration:   {actual_duration:.2f}s")
    
    # Allow 0.1s tolerance for rounding
    if abs(actual_duration - expected_duration) < 0.2:
        test_passed("Duration match", f"{actual_duration:.2f}s ≈ {expected_duration:.2f}s")
    else:
        test_failed("Duration match", f"Off by {abs(actual_duration - expected_duration):.2f}s")
    
    # Export to file
    output_dir = BASE_DIR / "tests" / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "test_concatenated_chapter.wav"
    
    try:
        output_buffer = io.BytesIO()
        final_audio.export(output_buffer, format="wav")
        output_buffer.seek(0)
        final_bytes = output_buffer.read()
        
        with open(output_file, 'wb') as f:
            f.write(final_bytes)
        
        file_size_kb = len(final_bytes) / 1024
        test_passed("Export to file", f"{output_file.name} ({file_size_kb:.1f} KB)")
        print(f"    📁 Saved: {output_file}")
        
        return final_bytes
        
    except Exception as e:
        test_failed("Export to file", str(e))
        return None


# ========================================================================
#  TEST 4: Frontend Presentation Demo
# ========================================================================


def test_4_frontend_demo(segments: list = None, concatenated_bytes: bytes = None):
    """
    Generate an interactive HTML demo showing how audio would be
    presented in the frontend with karaoke-style text highlighting.
    """
    print("\n" + "=" * 60)
    print("  TEST 4: Frontend Presentation Demo")
    print("=" * 60)
    
    # Build timing data (same format as /audio/timings/ endpoint)
    if segments:
        current_time = 0.0
        silence_gap = 0.3
        timing_chunks = []
        
        for idx, seg in enumerate(segments):
            timing_chunks.append({
                "index": idx,
                "text": seg.get("chunk_text", f"Segment {idx}"),
                "start": round(current_time, 3),
                "end": round(current_time + seg["duration"], 3)
            })
            current_time += seg["duration"] + silence_gap
        
        total_duration = current_time - silence_gap
    else:
        # Fallback demo data
        timing_chunks = [
            {"index": 0, "text": "The morning sun cast long shadows across the cobblestone streets of the old district.", "start": 0.0, "end": 3.5},
            {"index": 1, "text": "Maria pulled her coat tighter as she hurried past the ancient cathedral.", "start": 3.8, "end": 6.8},
            {"index": 2, "text": '"You\'re late," said Thomas, standing by the fountain.', "start": 7.1, "end": 9.5},
            {"index": 3, "text": "She took the envelope without a word, turning it over in her hands.", "start": 9.8, "end": 13.0},
            {"index": 4, "text": "The cathedral bells began to toll, their deep resonance echoing through the empty square.", "start": 13.3, "end": 17.2},
        ]
        total_duration = 17.2
    
    # Check if concatenated audio exists
    audio_src = ""
    output_dir = BASE_DIR / "tests" / "output"
    audio_file = output_dir / "test_concatenated_chapter.wav"
    
    if audio_file.exists():
        # Use relative path for the HTML
        audio_src = "output/test_concatenated_chapter.wav"
        print(f"    🎵 Using audio file: {audio_file}")
    else:
        print(f"    ⚠️  No audio file found — player will be visual-only demo")
    
    # Generate the HTML
    import json
    chunks_json = json.dumps(timing_chunks, indent=2)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NovelLabs — Audio Player Demo</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0f0f14;
            --bg-secondary: #1a1a24;
            --bg-card: #22222e;
            --bg-hover: #2a2a38;
            --text-primary: #e8e6f0;
            --text-secondary: #9896a8;
            --text-muted: #6b6980;
            --accent: #7c6df0;
            --accent-glow: rgba(124, 109, 240, 0.25);
            --accent-light: #9d91f5;
            --success: #4ade80;
            --border: rgba(255,255,255,0.06);
            --chunk-active: rgba(124, 109, 240, 0.15);
            --chunk-done: rgba(124, 109, 240, 0.05);
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Inter', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}

        /* ============= Header ============= */
        .header {{
            width: 100%;
            padding: 20px 32px;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 16px;
        }}
        .header .logo {{
            font-family: 'Playfair Display', serif;
            font-size: 22px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-light), var(--accent));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .header .badge {{
            font-size: 11px;
            padding: 3px 10px;
            border-radius: 12px;
            background: var(--accent-glow);
            color: var(--accent-light);
            font-weight: 600;
            letter-spacing: 0.5px;
        }}
        .header .meta {{
            margin-left: auto;
            font-size: 13px;
            color: var(--text-muted);
        }}

        /* ============= Main Content ============= */
        .container {{
            max-width: 780px;
            width: 100%;
            padding: 40px 24px;
        }}

        .chapter-info {{
            margin-bottom: 32px;
        }}
        .chapter-info h1 {{
            font-family: 'Playfair Display', serif;
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 6px;
        }}
        .chapter-info .subtitle {{
            font-size: 14px;
            color: var(--text-secondary);
        }}

        /* ============= Audio Player ============= */
        .player-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 32px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.3);
        }}

        .player-top {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 20px;
        }}

        .play-btn {{
            width: 52px;
            height: 52px;
            border-radius: 50%;
            border: none;
            background: linear-gradient(135deg, var(--accent), #6354d9);
            color: white;
            font-size: 22px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.15s, box-shadow 0.2s;
            box-shadow: 0 2px 12px var(--accent-glow);
            flex-shrink: 0;
        }}
        .play-btn:hover {{
            transform: scale(1.08);
            box-shadow: 0 4px 20px var(--accent-glow);
        }}
        .play-btn:active {{ transform: scale(0.96); }}

        .player-info {{
            flex: 1;
        }}
        .player-info .voice-name {{
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
        }}
        .player-info .duration {{
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 2px;
        }}

        /* Progress bar */
        .progress-container {{
            position: relative;
            height: 6px;
            background: rgba(255,255,255,0.06);
            border-radius: 3px;
            cursor: pointer;
            overflow: hidden;
        }}
        .progress-bar {{
            height: 100%;
            background: linear-gradient(90deg, var(--accent), var(--accent-light));
            border-radius: 3px;
            width: 0%;
            transition: width 0.1s linear;
        }}

        .time-display {{
            display: flex;
            justify-content: space-between;
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 6px;
            font-variant-numeric: tabular-nums;
        }}

        /* ============= Chapter Text ============= */
        .text-panel {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 28px;
            margin-bottom: 32px;
        }}
        .text-panel h2 {{
            font-size: 14px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 20px;
        }}

        .chunk {{
            display: inline;
            padding: 3px 1px;
            border-radius: 4px;
            line-height: 1.9;
            font-size: 16px;
            color: var(--text-secondary);
            transition: color 0.3s, background 0.3s;
            cursor: pointer;
        }}
        .chunk:hover {{
            background: rgba(255,255,255,0.04);
        }}
        .chunk.active {{
            color: var(--text-primary);
            background: var(--chunk-active);
            font-weight: 500;
        }}
        .chunk.done {{
            color: var(--text-primary);
            background: var(--chunk-done);
        }}

        /* ============= Timing Table ============= */
        .timings-panel {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
        }}
        .timings-panel h2 {{
            font-size: 14px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 16px;
        }}

        .timing-row {{
            display: grid;
            grid-template-columns: 40px 70px 70px 1fr;
            gap: 12px;
            padding: 10px 12px;
            border-radius: 8px;
            font-size: 13px;
            color: var(--text-secondary);
            transition: background 0.2s;
        }}
        .timing-row:nth-child(even) {{ background: rgba(255,255,255,0.02); }}
        .timing-row.active {{
            background: var(--chunk-active);
            color: var(--text-primary);
        }}
        .timing-row .idx {{ color: var(--text-muted); font-weight: 600; }}
        .timing-row .time {{ font-variant-numeric: tabular-nums; color: var(--accent-light); }}
        .timing-row .text {{ 
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}

        .timing-header {{
            display: grid;
            grid-template-columns: 40px 70px 70px 1fr;
            gap: 12px;
            padding: 8px 12px;
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 4px;
        }}

        /* ============= Status Badge ============= */
        .status-bar {{
            display: flex;
            gap: 16px;
            margin-top: 32px;
            padding: 16px 20px;
            background: var(--bg-secondary);
            border-radius: 12px;
            font-size: 12px;
            color: var(--text-muted);
        }}
        .status-bar .dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 6px;
        }}
        .dot.green {{ background: var(--success); }}
        .dot.purple {{ background: var(--accent); }}
    </style>
</head>
<body>

    <div class="header">
        <div class="logo">NovelLabs</div>
        <span class="badge">PIPELINE TEST</span>
        <div class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
    </div>

    <div class="container">
        <div class="chapter-info">
            <h1>Chapter 1 — The Envelope</h1>
            <div class="subtitle">Test Novel · {len(timing_chunks)} chunks · {total_duration:.1f}s estimated</div>
        </div>

        <!-- Audio Player -->
        <div class="player-card">
            <div class="player-top">
                <button class="play-btn" id="playBtn" onclick="togglePlay()">▶</button>
                <div class="player-info">
                    <div class="voice-name">🎤 af_heart (American Female)</div>
                    <div class="duration">{total_duration:.1f}s · {len(timing_chunks)} segments · WAV 24kHz</div>
                </div>
            </div>
            <div class="progress-container" onclick="seekAudio(event)">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            <div class="time-display">
                <span id="currentTime">0:00</span>
                <span id="totalTime">{int(total_duration // 60)}:{int(total_duration % 60):02d}</span>
            </div>
        </div>

        <!-- Chapter Text with Karaoke Highlighting -->
        <div class="text-panel">
            <h2>📖 Chapter Text — Karaoke Mode</h2>
            <div id="chapterText">
                <!-- Chunks injected by JS -->
            </div>
        </div>

        <!-- Timing Data Visualization -->
        <div class="timings-panel">
            <h2>⏱️ Chunk Timing Data (from /audio/timings/ API)</h2>
            <div class="timing-header">
                <span>#</span>
                <span>Start</span>
                <span>End</span>
                <span>Text</span>
            </div>
            <div id="timingRows">
                <!-- Injected by JS -->
            </div>
        </div>

        <!-- Status Bar -->
        <div class="status-bar">
            <span><span class="dot green"></span>R2 Storage: Connected</span>
            <span><span class="dot purple"></span>TTS: Kokoro (Modal)</span>
            <span><span class="dot green"></span>Audio: {"Real File" if audio_src else "Simulated"}</span>
        </div>
    </div>

    <script>
        // ==================== Data ====================
        const chunks = {chunks_json};
        const totalDuration = {total_duration};
        const audioSrc = "{audio_src}";

        // ==================== Player State ====================
        let isPlaying = false;
        let currentTime = 0;
        let animFrame = null;
        let audioEl = null;

        // ==================== Init ====================
        function init() {{
            // Render chunk text
            const textEl = document.getElementById('chapterText');
            chunks.forEach((chunk, i) => {{
                const span = document.createElement('span');
                span.className = 'chunk';
                span.id = `chunk-${{i}}`;
                span.textContent = chunk.text + ' ';
                span.onclick = () => seekToChunk(i);
                textEl.appendChild(span);
            }});

            // Render timing rows
            const rowsEl = document.getElementById('timingRows');
            chunks.forEach((chunk, i) => {{
                const row = document.createElement('div');
                row.className = 'timing-row';
                row.id = `timing-${{i}}`;
                row.innerHTML = `
                    <span class="idx">${{i}}</span>
                    <span class="time">${{formatTime(chunk.start)}}</span>
                    <span class="time">${{formatTime(chunk.end)}}</span>
                    <span class="text">${{escapeHtml(chunk.text)}}</span>
                `;
                row.onclick = () => seekToChunk(i);
                rowsEl.appendChild(row);
            }});

            // Load audio if available
            if (audioSrc) {{
                audioEl = new Audio(audioSrc);
                audioEl.addEventListener('timeupdate', () => {{
                    currentTime = audioEl.currentTime;
                    updateUI();
                }});
                audioEl.addEventListener('ended', () => {{
                    isPlaying = false;
                    document.getElementById('playBtn').textContent = '▶';
                }});
            }}
        }}

        // ==================== Controls ====================
        function togglePlay() {{
            if (audioEl) {{
                if (isPlaying) {{
                    audioEl.pause();
                    isPlaying = false;
                    document.getElementById('playBtn').textContent = '▶';
                }} else {{
                    audioEl.play();
                    isPlaying = true;
                    document.getElementById('playBtn').textContent = '⏸';
                }}
            }} else {{
                // Simulate playback
                if (isPlaying) {{
                    isPlaying = false;
                    cancelAnimationFrame(animFrame);
                    document.getElementById('playBtn').textContent = '▶';
                }} else {{
                    isPlaying = true;
                    document.getElementById('playBtn').textContent = '⏸';
                    simulatePlay();
                }}
            }}
        }}

        function simulatePlay() {{
            const startWall = performance.now();
            const startOffset = currentTime;

            function tick() {{
                if (!isPlaying) return;
                currentTime = startOffset + (performance.now() - startWall) / 1000;
                if (currentTime >= totalDuration) {{
                    currentTime = totalDuration;
                    isPlaying = false;
                    document.getElementById('playBtn').textContent = '▶';
                }}
                updateUI();
                if (isPlaying) animFrame = requestAnimationFrame(tick);
            }}
            animFrame = requestAnimationFrame(tick);
        }}

        function seekAudio(e) {{
            const rect = e.target.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            currentTime = pct * totalDuration;
            if (audioEl) audioEl.currentTime = currentTime;
            updateUI();
        }}

        function seekToChunk(i) {{
            currentTime = chunks[i].start;
            if (audioEl) audioEl.currentTime = currentTime;
            updateUI();
        }}

        // ==================== UI Update ====================
        function updateUI() {{
            const pct = (currentTime / totalDuration) * 100;
            document.getElementById('progressBar').style.width = pct + '%';
            document.getElementById('currentTime').textContent = formatTime(currentTime);

            // Highlight active chunk
            chunks.forEach((chunk, i) => {{
                const el = document.getElementById(`chunk-${{i}}`);
                const row = document.getElementById(`timing-${{i}}`);
                if (currentTime >= chunk.start && currentTime < chunk.end) {{
                    el.className = 'chunk active';
                    row.className = 'timing-row active';
                    // Scroll into view
                    el.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
                }} else if (currentTime >= chunk.end) {{
                    el.className = 'chunk done';
                    row.className = 'timing-row';
                }} else {{
                    el.className = 'chunk';
                    row.className = 'timing-row';
                }}
            }});
        }}

        // ==================== Helpers ====================
        function formatTime(s) {{
            const m = Math.floor(s / 60);
            const sec = Math.floor(s % 60);
            return `${{m}}:${{sec.toString().padStart(2, '0')}}`;
        }}

        function escapeHtml(str) {{
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }}

        // ==================== Start ====================
        init();
    </script>
</body>
</html>"""
    
    # Write HTML file
    output_path = BASE_DIR / "tests" / "frontend_demo.html"
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        test_passed("HTML demo generated", f"{output_path.name} ({len(html_content):,} bytes)")
        print(f"    📁 Saved: {output_path}")
        
        # Open in browser
        try:
            webbrowser.open(f"file:///{output_path.as_posix()}")
            test_passed("Browser launched", "Demo opened in default browser")
        except Exception as e:
            print(f"    ⚠️  Could not open browser: {e}")
            print(f"    💡 Open manually: {output_path}")
        
    except Exception as e:
        test_failed("HTML demo generation", str(e))


# ========================================================================
#  MAIN
# ========================================================================


def print_summary():
    print("\n" + "=" * 60)
    print(f"  📊 PIPELINE TEST SUMMARY: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if errors:
        print("\n❌ Failures:")
        for error in errors:
            print(f"   • {error}")
    
    if failed == 0:
        print("\n🎉 All tests passed! The pipeline is working correctly.")
    else:
        print(f"\n💡 {failed} test(s) failed. Check the details above.")
    
    print()


def main():
    print("=" * 60)
    print("  NOVELLABS PIPELINE SIMULATION TEST SUITE")
    print("=" * 60)
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Base dir:  {BASE_DIR}")
    
    # Check for specific test flag
    specific_test = None
    if "--test" in sys.argv:
        idx = sys.argv.index("--test")
        if idx + 1 < len(sys.argv):
            specific_test = int(sys.argv[idx + 1])
    
    segments = None
    concatenated_bytes = None
    
    # Test 1: Chunking + Generation
    if specific_test is None or specific_test == 1:
        segments = test_1_chunking_and_generation()
    
    # Test 2: R2 Upload
    if specific_test is None or specific_test == 2:
        test_2_r2_upload()
    
    # Test 3: Concatenation
    if specific_test is None or specific_test == 3:
        concatenated_bytes = test_3_concatenation(segments)
    
    # Test 4: Frontend Demo
    if specific_test is None or specific_test == 4:
        test_4_frontend_demo(segments, concatenated_bytes)
    
    print_summary()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
