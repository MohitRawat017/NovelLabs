"""
Database cleanup and deduplication script
Merges duplicate novels and cleans up the database
"""
import sqlite3
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "novels.db"


def normalize_slug(name: str) -> str:
    """Standard slug generation - must be used consistently everywhere"""
    slug = name.lower().replace(' ', '-')
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    return slug


def clean_duplicates():
    """Remove duplicate novels, keeping the one with most chapters"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("[INFO] Checking for duplicate novels...")
    
    # Get all novels
    cursor.execute("SELECT id, slug, title, chapter_count FROM novels ORDER BY slug")
    novels = cursor.fetchall()
    
    # Group by normalized slug
    slug_groups = {}
    for novel in novels:
        normalized = normalize_slug(novel['slug'])
        if normalized not in slug_groups:
            slug_groups[normalized] = []
        slug_groups[normalized].append(dict(novel))
    
    deleted_count = 0
    merged_count = 0
    
    for normalized_slug, group in slug_groups.items():
        if len(group) <= 1:
            continue
        
        print(f"\n[DUPE] Found {len(group)} entries for '{normalized_slug}':")
        for n in group:
            print(f"       - id={n['id']}, slug='{n['slug']}', chapters={n['chapter_count']}")
        
        # Keep the one with most chapters (or lowest id as tiebreaker)
        group.sort(key=lambda x: (-x['chapter_count'], x['id']))
        keep = group[0]
        remove = group[1:]
        
        print(f"       Keeping id={keep['id']} (slug='{keep['slug']}', {keep['chapter_count']} chapters)")
        
        for r in remove:
            # First, reassign chapters to the kept novel
            cursor.execute(
                "UPDATE chapters SET novel_id = ? WHERE novel_id = ?",
                (keep['id'], r['id'])
            )
            moved = cursor.rowcount
            if moved > 0:
                print(f"       Moved {moved} chapters from id={r['id']} to id={keep['id']}")
                merged_count += moved
            
            # Delete the duplicate novel
            cursor.execute("DELETE FROM novels WHERE id = ?", (r['id'],))
            print(f"       Deleted novel id={r['id']} (slug='{r['slug']}')")
            deleted_count += 1
        
        # Update the kept novel slug to normalized version
        cursor.execute(
            "UPDATE novels SET slug = ? WHERE id = ?",
            (normalized_slug, keep['id'])
        )
        
        # Recalculate chapter count
        cursor.execute(
            "SELECT COUNT(*) FROM chapters WHERE novel_id = ?",
            (keep['id'],)
        )
        new_count = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE novels SET chapter_count = ? WHERE id = ?",
            (new_count, keep['id'])
        )
        print(f"       Updated chapter count to {new_count}")
    
    conn.commit()
    
    # Final count
    cursor.execute("SELECT COUNT(*) FROM novels")
    final_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT slug, title, chapter_count FROM novels ORDER BY title")
    final_novels = cursor.fetchall()
    
    conn.close()
    
    print(f"\n[DONE] Cleanup complete!")
    print(f"       - Deleted {deleted_count} duplicate novels")
    print(f"       - Merged {merged_count} chapters")
    print(f"       - Final novel count: {final_count}")
    print(f"\n[NOVELS] Current novels in database:")
    for n in final_novels:
        print(f"         - {n['title']}: {n['chapter_count']} chapters (slug: {n['slug']})")


if __name__ == "__main__":
    print("=" * 60)
    print("Database Cleanup & Deduplication Script")
    print("=" * 60)
    clean_duplicates()
