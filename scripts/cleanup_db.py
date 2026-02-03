"""
Database Cleanup Script - Remove Content Bloat

This script removes chapter content from the database to reduce storage.
Content will be read from filesystem (content_path) when needed.

BEFORE running:
- Backup your database
- Ensure content_path is set correctly for all chapters

AFTER running:
- Database size should drop by ~90%
- Chapters will still work (content read from files)

Usage:
    python cleanup_content_bloat.py
"""

import os
import httpx
from typing import Optional

# Configuration
API_URL = os.getenv("API_URL", "https://novellabs.onrender.com/api")


def get_database_stats(client: httpx.Client):
    """Get current database statistics"""
    try:
        # Get novels count
        response = client.get(f"{API_URL}/novels?limit=1")
        if response.status_code == 200:
            data = response.json()
            total_novels = data.get('total', 0)
            print(f"[STAT] Total novels: {total_novels}")
            return total_novels
        else:
            print(f"[ERROR] Failed to get stats: {response.status_code}")
            return 0
    except Exception as e:
        print(f"[ERROR] Exception getting stats: {e}")
        return 0


def create_cleanup_endpoint_request():
    """
    Creates a request to a cleanup endpoint (needs to be implemented in API)
    
    This would run on the server:
    UPDATE chapters SET content = NULL WHERE content IS NOT NULL;
    """
    print("\n[INFO] Database cleanup needs to be done server-side")
    print("[INFO] Please add this endpoint to your API:\n")
    
    print("```python")
    print("# In src/api/routes/admin.py or chapters.py")
    print("")
    print("@router.post('/admin/cleanup-content')")
    print("async def cleanup_chapter_content():")
    print('    """Remove chapter content from DB to save space"""')
    print("    with get_db() as conn:")
    print("        cursor = conn.cursor()")
    print("        ")
    print("        # Get stats before")
    print("        cursor.execute('SELECT COUNT(*) FROM chapters WHERE content IS NOT NULL')")
    print("        before_count = cursor.fetchone()[0]")
    print("        ")
    print("        # Clear content column")
    print("        cursor.execute('UPDATE chapters SET content = NULL WHERE content IS NOT NULL')")
    print("        affected = cursor.rowcount")
    print("        ")
    print("        conn.commit()")
    print("        ")
    print("        return {")
    print("            'message': 'Content cleanup complete',")
    print("            'chapters_cleaned': affected,")
    print("            'before': before_count")
    print("        }")
    print("```")
    print()
    print("[NEXT] After adding this endpoint, run:")
    print(f"       curl -X POST {API_URL}/admin/cleanup-content")


def analyze_bloat(client: httpx.Client):
    """Analyze how much bloat exists"""
    print("\n" + "="*60)
    print("DATABASE BLOAT ANALYSIS")
    print("="*60)
    
    try:
        # Get all novels
        response = client.get(f"{API_URL}/novels?limit=100")
        if response.status_code != 200:
            print(f"[ERROR] Failed to get novels: {response.status_code}")
            return
        
        data = response.json()
        novels = data.get('novels', [])
        
        total_chapters = 0
        for novel in novels:
            chapter_count = novel.get('chapter_count', 0)
            total_chapters += chapter_count
            print(f"[NOVEL] {novel['title']}: {chapter_count} chapters")
        
        # Estimate bloat
        avg_chapter_size_kb = 10  # Conservative estimate
        bloat_mb = (total_chapters * avg_chapter_size_kb) / 1024
        
        print(f"\n[ESTIMATE] Total chapters: {total_chapters}")
        print(f"[ESTIMATE] Average chapter size: {avg_chapter_size_kb} KB")
        print(f"[ESTIMATE] Estimated content bloat: {bloat_mb:.1f} MB")
        print(f"[ESTIMATE] After cleanup: ~{(total_chapters * 0.2 / 1024):.1f} MB (metadata only)")
        print(f"[SAVING] Expected savings: {bloat_mb:.1f} MB ({(bloat_mb / (bloat_mb + 1) * 100):.1f}%)")
        
    except Exception as e:
        print(f"[ERROR] Analysis failed: {e}")


def main():
    print("="*60)
    print("DATABASE CONTENT BLOAT CLEANUP")
    print("="*60)
    print()
    print("This script helps you remove chapter content from database")
    print("to save storage space (~90% reduction expected)")
    print()
    
    with httpx.Client(timeout=30) as client:
        # Get stats
        total_novels = get_database_stats(client)
        
        if total_novels == 0:
            print("[ERROR] No novels found or API unreachable")
            return
        
        # Analyze bloat
        analyze_bloat(client)
        
        # Show instructions for cleanup
        create_cleanup_endpoint_request()


if __name__ == "__main__":
    main()