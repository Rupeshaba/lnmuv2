import sqlite3
import requests
import os
import threading
import time
from pathlib import Path

from config.config import DB_PATH, DB_FILE, DROPBOX_DIRECT_URL, TABLES, SEARCH_COLS, GOOGLE_DRIVE_FILE_ID

# Global status for download progress
DOWNLOAD_STATUS = {
    "download_state": "Not started",
    "download_percent": 0.0,
    "download_done_bytes": 0,
    "download_total_bytes": None,
}

download_lock = threading.Lock()
abort_download = threading.Event()

def human_bytes(n):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


def _apply_pragmas(con):
    """Apply performance PRAGMAs to a SQLite connection."""
    con.execute("PRAGMA journal_mode=WAL")       # Concurrent reads, faster writes
    con.execute("PRAGMA synchronous=NORMAL")      # Safe but faster than FULL
    con.execute("PRAGMA cache_size=-64000")       # 64MB page cache in RAM
    con.execute("PRAGMA temp_store=MEMORY")       # Temp tables in RAM
    con.execute("PRAGMA mmap_size=268435456")     # 256MB memory-mapped I/O
    con.execute("PRAGMA optimize")                # Let SQLite auto-optimize query planner


def download_db():
    with download_lock:
        if os.path.exists(DB_PATH):
            DOWNLOAD_STATUS["download_state"] = "Already downloaded"
            DOWNLOAD_STATUS["download_percent"] = 100.0
            DOWNLOAD_STATUS["download_done_bytes"] = os.path.getsize(DB_PATH)
            return True

        try:
            abort_download.clear()
            DOWNLOAD_STATUS["download_state"] = "Starting..."
            print("[DB] Starting DB download from Google Drive...")

            session = requests.Session()

            URL = "https://drive.usercontent.google.com/download?id=1OSlOI7bOvTKzq2d834TOtzm-tehk7fS9&export=download&authuser=0&confirm=t&uuid=decc832e-c20d-4e06-b9ff-743331113eac&at=ANTm3cy-sPLO_CVWUrnkuFuSetki%3A1767356217931"
            params = {"id": GOOGLE_DRIVE_FILE_ID}

            response = session.get(URL, stream=True)
            token = None

            # 🔐 Google Drive confirmation token (large file)
            for k, v in response.cookies.items():
                if k.startswith("download_warning"):
                    token = v

            if token:
                params["confirm"] = token
                response = session.get(URL, params=params, stream=True)

            response.raise_for_status()

            total = response.headers.get("Content-Length")
            if total:
                total = int(total)
                DOWNLOAD_STATUS["download_total_bytes"] = total

            done = 0
            chunk_size = 1024 * 1024  # 1MB

            with open(DB_PATH + ".part", "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if abort_download.is_set():
                        print("[DB] Download aborted")
                        return False

                    if chunk:
                        f.write(chunk)
                        done += len(chunk)

                        DOWNLOAD_STATUS["download_done_bytes"] = done
                        if total:
                            DOWNLOAD_STATUS["download_percent"] = round(
                                (done / total) * 100, 2
                            )

            os.replace(DB_PATH + ".part", DB_PATH)

            DOWNLOAD_STATUS["download_state"] = "Download complete"
            print("[DB] Google Drive DB download complete.")
            return True

        except Exception as e:
            print(f"[DB] Download ERROR: {e}")
            DOWNLOAD_STATUS["download_state"] = f"Failed: {e}"
            return False


def download_dbdropbox():
    with download_lock:
        if os.path.exists(DB_PATH):
            try:
                con = sqlite3.connect(DB_PATH)
                con.execute("SELECT 1")
                con.close()
                DOWNLOAD_STATUS["download_state"] = "Already downloaded"
                DOWNLOAD_STATUS["download_percent"] = 100.0
                DOWNLOAD_STATUS["download_done_bytes"] = os.path.getsize(DB_PATH)
                print("[DB] Database already exists and is valid.")
                return True
            except sqlite3.DatabaseError:
                print("[DB] Existing file is corrupted. Re-downloading...")
                os.remove(DB_PATH)

        try:
            abort_download.clear()
            DOWNLOAD_STATUS["download_state"] = "Starting..."
            print("[DB] Starting DB download from Dropbox...")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            with requests.get(DROPBOX_DIRECT_URL, stream=True, timeout=60, headers=headers) as r:
                r.raise_for_status()

                content_type = r.headers.get('Content-Type', '')
                print(f"[DB] Content-Type: {content_type}")

                total = r.headers.get("Content-Length")
                if total:
                    total = int(total)
                    DOWNLOAD_STATUS["download_total_bytes"] = total
                    print(f"[DB] Download size: {human_bytes(total)}")

                done = 0
                chunk_size = 1024 * 1024  # 1MB chunks

                with open(DB_PATH + ".part", "wb") as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if abort_download.is_set():
                            print("[DB] Download aborted")
                            return False

                        if chunk:
                            f.write(chunk)
                            done += len(chunk)

                            DOWNLOAD_STATUS["download_done_bytes"] = done
                            if total:
                                percent = round((done / total) * 100, 2)
                                DOWNLOAD_STATUS["download_percent"] = percent
                                if percent % 10 == 0:
                                    print(f"[DB] Download progress: {percent}%")

                os.replace(DB_PATH + ".part", DB_PATH)

            try:
                con = sqlite3.connect(DB_PATH)
                con.execute("SELECT 1")
                con.close()
                print("[DB] Download complete and verified.")
                DOWNLOAD_STATUS["download_state"] = "Download complete"
                return True
            except sqlite3.DatabaseError as e:
                print(f"[DB] Downloaded file is not a valid SQLite database: {e}")
                os.remove(DB_PATH)
                DOWNLOAD_STATUS["download_state"] = f"Failed: Invalid database file"
                return False

        except Exception as e:
            print(f"[DB] Download ERROR: {e}")
            DOWNLOAD_STATUS["download_state"] = f"Failed: {e}"
            if os.path.exists(DB_PATH + ".part"):
                os.remove(DB_PATH + ".part")
            return False


def create_indexes():
    if not os.path.exists(DB_PATH):
        print("[DB] Database file not found. Skipping index creation.")
        return

    try:
        con = sqlite3.connect(DB_PATH)
        _apply_pragmas(con)
        cur = con.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        print(f"[DB] Found tables: {tables}")

        for t in TABLES:
            if t not in tables:
                print(f"[DB] Table {t} not found in database, skipping...")
                continue

            for c in SEARCH_COLS:
                try:
                    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_{c} ON {t}({c})")
                except Exception as e:
                    print(f"[DB] Error creating index idx_{t}_{c} on table {t}: {e}")

        for t in TABLES:
            if t not in tables:
                continue

            for col, label in [
                ("allotedcollege", "allotedcollege"),
                ("major", "major"),
                ("allotedhonours", "allotedhonours"),
                ("cname", "cname"),
            ]:
                try:
                    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_{label} ON {t}({col})")
                except Exception as e:
                    print(f"[DB] Error creating {label} index: {e}")

            # Composite indexes for common filter combos
            for cols, label in [
                ("allotedcollege, major", "college_major"),
                ("allotedcollege, allotedhonours", "college_honours"),
                ("allotedcollege, allotedcourse", "college_course"),
                ("allotedcollege, allotedcourse, major", "college_course_major"),
            ]:
                try:
                    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_{label} ON {t}({cols})")
                except Exception as e:
                    print(f"[DB] Error creating composite {label} index: {e}")

        con.commit()
        con.close()
        print("[DB] Indexes created successfully.")

    except Exception as e:
        print(f"[DB] Error in create_indexes: {e}")


def execute_query(query, params=(), fetch_one=False):
    """Execute a query and return results. Opens a fresh connection per call (thread-safe)."""
    if not os.path.exists(DB_PATH):
        return [] if not fetch_one else None

    try:
        con = sqlite3.connect(DB_PATH, check_same_thread=False)
        con.row_factory = sqlite3.Row
        _apply_pragmas(con)
        cur = con.cursor()
        cur.execute(query, params)
        if fetch_one:
            row = cur.fetchone()
            return dict(row) if row else None
        else:
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"[DB] Error executing query: {e}")
        return [] if not fetch_one else None
    finally:
        con.close()


def get_tables():
    return TABLES


def init_db():
    Path(os.path.dirname(DB_PATH)).mkdir(parents=True, exist_ok=True)

    if not os.path.exists(DB_PATH):
        print("[DB] Database not found. Starting download...")

        success = download_db()
        if not success or not os.path.exists(DB_PATH):
            raise RuntimeError("Database download failed. Cannot start app.")

    print("[DB] Database ready.")
    create_indexes()
