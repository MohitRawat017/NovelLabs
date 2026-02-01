"""
Test Suite: Audio/Segments Database Integration
Run with: python tests/test_audio_db.py
"""

import sqlite3
import json
import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

DB_PATH = BASE_DIR / "data" / "novels.db"
AUDIO_DIR = BASE_DIR / "audio"

# Test results tracker
passed_count = 0
failed_count = 0
errors_list = []


def test_passed(name):
    global passed_count
    passed_count += 1
    print(f"  [PASS] {name}")


def test_failed(name, error):
    global failed_count
    failed_count += 1
    errors_list.append(f"{name}: {error}")
    print(f"  [FAIL] {name}: {error}")


# ==================== DATABASE TESTS ====================

def test_database_exists():
    if DB_PATH.exists():
        test_passed("Database file exists")
        return True
    else:
        test_failed("Database file exists", f"Not found: {DB_PATH}")
        return False


def test_tables_exist():
    required_tables = ["novels", "chapters", "segments", "user_progress", "user_preferences"]
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    missing = set(required_tables) - existing_tables
    if missing:
        test_failed("Required tables exist", f"Missing: {missing}")
        return False
    else:
        test_passed("Required tables exist")
        return True


def test_segments_schema():
    required_columns = ["id", "chapter_id", "segment_index", "text", "audio_url", 
                        "timing_data", "status", "created_at", "last_accessed"]
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(segments)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    
    missing = set(required_columns) - existing_columns
    if missing:
        test_failed("Segments schema correct", f"Missing columns: {missing}")
        return False
    else:
        test_passed("Segments schema correct")
        return True


def test_chapters_have_content():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chapters WHERE content IS NOT NULL AND content != ''")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count > 0:
        test_passed(f"Chapters with content: {count}")
        return True
    else:
        test_failed("Chapters with content", "No chapters have content in DB")
        return False


def test_segments_populated():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM segments")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM segments WHERE status = 'ready'")
    ready = cursor.fetchone()[0]
    conn.close()
    
    if total > 0:
        test_passed(f"Segments populated: {total} total, {ready} ready")
        return True
    else:
        test_failed("Segments populated", "No segments in database")
        return False


def test_segments_have_valid_timing():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT id, timing_data FROM segments WHERE timing_data IS NOT NULL LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        test_failed("Segments have timing data", "No segments with timing_data")
        return False
    
    valid_count = 0
    for row in rows:
        try:
            timing = json.loads(row[1])
            if "start" in timing and "end" in timing:
                valid_count += 1
        except json.JSONDecodeError:
            pass
    
    if valid_count == len(rows):
        test_passed(f"Segments have valid timing JSON ({valid_count}/{len(rows)})")
        return True
    else:
        test_failed("Segments have valid timing", f"Only {valid_count}/{len(rows)} valid")
        return False


def test_foreign_keys_valid():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM segments s
        LEFT JOIN chapters c ON s.chapter_id = c.id
        WHERE c.id IS NULL
    """)
    orphans = cursor.fetchone()[0]
    conn.close()
    
    if orphans == 0:
        test_passed("All segment foreign keys valid")
        return True
    else:
        test_failed("Foreign keys valid", f"{orphans} orphan segments found")
        return False


# ==================== API IMPORT TESTS ====================

def test_audio_module_imports():
    try:
        from src.api.routes import audio
        test_passed("audio.py imports successfully")
        return True
    except Exception as e:
        test_failed("audio.py imports", str(e))
        return False


def test_database_module_imports():
    try:
        from src.api.database import get_db
        test_passed("database.py imports successfully")
        return True
    except Exception as e:
        test_failed("database.py imports", str(e))
        return False


def test_models_import():
    try:
        from src.api.models.models import Novel, Chapter, Segment
        test_passed("SQLAlchemy models import successfully")
        return True
    except Exception as e:
        test_failed("Models import", str(e))
        return False


# ==================== FILESYSTEM TESTS ====================

def test_audio_dir_exists():
    if AUDIO_DIR.exists():
        test_passed("Audio directory exists")
        return True
    else:
        test_failed("Audio directory exists", f"Not found: {AUDIO_DIR}")
        return False


def test_backup_files_exist():
    backup_db = BASE_DIR / "data" / "novels.db.backup"
    backup_audio = BASE_DIR / "src" / "api" / "routes" / "audio.py.backup"
    
    found = []
    if backup_db.exists():
        found.append("novels.db.backup")
    if backup_audio.exists():
        found.append("audio.py.backup")
    
    if len(found) == 2:
        test_passed(f"Backup files exist: {found}")
        return True
    else:
        test_failed("Backup files", f"Found only: {found}")
        return False


# ==================== MAIN ====================

def run_all_tests():
    global passed_count, failed_count, errors_list
    
    print("")
    print("=" * 60)
    print("Audio/Segments Database Integration Tests")
    print("=" * 60)
    
    print("\n[Database Tests]")
    test_database_exists()
    test_tables_exist()
    test_segments_schema()
    test_chapters_have_content()
    test_segments_populated()
    test_segments_have_valid_timing()
    test_foreign_keys_valid()
    
    print("\n[Import Tests]")
    test_audio_module_imports()
    test_database_module_imports()
    test_models_import()
    
    print("\n[Filesystem Tests]")
    test_audio_dir_exists()
    test_backup_files_exist()
    
    print("")
    print("=" * 60)
    print(f"Results: {passed_count} passed, {failed_count} failed")
    print("=" * 60)
    
    if errors_list:
        print("\nFailures:")
        for err in errors_list:
            print(f"  - {err}")
    
    return failed_count == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
