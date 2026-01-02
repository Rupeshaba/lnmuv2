import sqlite3
import requests
import os
import threading
import time
from pathlib import Path

from config.config import DB_PATH, DB_FILE, DROPBOX_DIRECT_URL, TABLES, SEARCH_COLS

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
            print("[DB] Starting DB download from Dropbox...")

            with requests.get(DROPBOX_DIRECT_URL, stream=True, timeout=60) as r:
                r.raise_for_status()

                total = r.headers.get("Content-Length")
                if total:
                    total = int(total)
                    DOWNLOAD_STATUS["download_total_bytes"] = total

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
                                DOWNLOAD_STATUS["download_percent"] = round((done / total) * 100, 2)

                os.replace(DB_PATH + ".part", DB_PATH)

            print("[DB] Download complete.")
            DOWNLOAD_STATUS["download_state"] = "Download complete"
            return True

        except Exception as e:
            print(f"[DB] Download ERROR: {e}")
            DOWNLOAD_STATUS["download_state"] = f"Failed: {e}"
            return False

def create_indexes():
    if not os.path.exists(DB_PATH):
        print("[DB] Database file not found. Skipping index creation.")
        return

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    # Create standard search column indexes
    for t in TABLES:
        for c in SEARCH_COLS:
            try:
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_{c} ON {t}({c})")
            except Exception as e:
                print(f"[DB] Error creating index idx_{t}_{c} on table {t}: {e}")
    
    # Create optimized indexes for college and major searches
    for t in TABLES:
        try:
            # Index on allotedcollege for fast college filtering
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_allotedcollege ON {t}(allotedcollege)")
        except:
            pass
        
        try:
            # Index on major for fast honours/major filtering
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_major ON {t}(major)")
        except:
            pass
        
        try:
            # Index on allotedhonours as fallback
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_allotedhonours ON {t}(allotedhonours)")
        except:
            pass
        
        try:
            # Composite index: college + major for fast combined filtering
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_college_major ON {t}(allotedcollege, major)")
        except:
            pass
        
        try:
            # Composite index: college + honours for fallback
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_college_honours ON {t}(allotedcollege, allotedhonours)")
        except:
            pass
        
        try:
            # Index on cname for fast name searches
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_cname ON {t}(cname)")
        except:
            pass
    
    con.commit()
    con.close()
    print("[DB] Indexes OK.")

def execute_query(query, params=(), fetch_one=False):
    if not os.path.exists(DB_PATH):
        return [] if not fetch_one else None

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    try:
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
        download_db()
    else:
        print("[DB] Database already exists.")
    create_indexes()
