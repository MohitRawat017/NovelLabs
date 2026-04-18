"""
Generate Kokoro Audio for all Novels and Chapters.
===================================================

This script fetches all novels and their chapters from the local API,
and sequentially triggers audio generation for each using the Kokoro TTS engine.

Usage:
    python scripts/generate_all_audio.py
"""

import time
import sys
import argparse
import httpx

# API Configuration
API_URL = "http://localhost:8001/api"
VOICE = "bm_george"  # Kokoro voice 'george'
PROVIDER = "kokoro"

def main():
    parser = argparse.ArgumentParser(description="Generate Kokoro Audio for all Novels and Chapters.")
    parser.add_argument("--slug", type=str, help="Optional slug of a specific novel to process (e.g. the-100th-regression-of-the-max-level-player)")
    args = parser.parse_args()

    print("=" * 60)
    if args.slug:
        print(f"  GENERATE AUDIO FOR NOVEL: {args.slug}")
    else:
        print(f"  GENERATE AUDIO FOR ALL NOVELS")
    print("=" * 60)
    print(f"  Provider: {PROVIDER}")
    print(f"  Voice   : {VOICE}")
    print(f"  API URL : {API_URL}")
    print("=" * 60)

    with httpx.Client(timeout=120) as client:
        # 1. Get all novels
        try:
            resp = client.get(f"{API_URL}/novels")
            resp.raise_for_status()
            novels_payload = resp.json()
            novels = novels_payload if isinstance(novels_payload, list) else novels_payload.get("novels", [])
        except Exception as e:
            print(f"[ERROR] Failed to fetch novels: {e}")
            sys.exit(1)

        if args.slug:
            novels = [n for n in novels if n.get("slug") == args.slug]
            if not novels:
                print(f"[ERROR] Novel with slug '{args.slug}' not found.")
                sys.exit(1)
        
        print(f"\n[INFO] Found {len(novels)} novel(s) to process.")

        for novel in novels:
            slug = novel.get("slug")
            title = novel.get("title")
            
            # 2. Get all chapters for the novel
            try:
                ch_resp = client.get(f"{API_URL}/chapters/novel/{slug}", timeout=180)
                ch_resp.raise_for_status()
                chapters_payload = ch_resp.json()
                chapters = chapters_payload if isinstance(chapters_payload, list) else chapters_payload.get("chapters", [])
            except Exception as e:
                print(f"[WARN] Failed to fetch chapters for {title}: {e}")
                continue
            
            print(f"\n[INFO] Processing '{title}' ({len(chapters)} chapters)...")
            
            for chapter in chapters:
                ch_num = chapter.get("chapter_number")
                
                # Try to trigger generation
                print(f"  -> Generating Chapter {ch_num}...", end="", flush=True)
                try:
                    # Trigger generation
                    gen_resp = client.post(
                        f"{API_URL}/audio/generate/{slug}/{ch_num}",
                        params={"voice": VOICE, "provider": PROVIDER},
                        timeout=120,
                    )
                    
                    if gen_resp.status_code in (200, 202):
                        resp_data = gen_resp.json()
                        if resp_data.get("status") == "exists":
                            print(" [SKIPPED] Already generated.")
                            continue
                    else:
                        print(f" [ERROR] {gen_resp.status_code}: {gen_resp.text}")
                        continue
                    
                    # Wait for completion to avoid overloading the backend
                    while True:
                        time.sleep(2)  # Check every 2 seconds
                        status_resp = client.get(f"{API_URL}/audio/status/{slug}/{ch_num}")
                        if status_resp.status_code == 200:
                            status_data = status_resp.json()
                            status = status_data.get("job_status")
                            
                            if status == "completed":
                                print(f" [OK] Done.")
                                break
                            elif status == "failed" or status == "cancelled":
                                msg = status_data.get("message", "Unknown error")
                                print(f" [FAILED] {msg}")
                                break
                            elif status == "generating":
                                # we could print a progress dot here
                                print(".", end="", flush=True)
                        else:
                            print(f" [API ERROR] Could not check status. Code: {status_resp.status_code}")
                            break
                            
                except Exception as e:
                    print(f" [EXCEPTION] {e}")

    print("\n[DONE] Generation process complete.")

if __name__ == "__main__":
    main()
