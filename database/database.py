import sqlite3
import requests
import os
import threading
import time
from pathlib import Path

from config.config import DB_PATH, DB_FILE, DROPBOX_DIRECT_URL, TABLES, SEARCH_COLS,GOOGLE_DRIVE_FILE_ID

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
            print("[DB] Starting DB download from Google Drive...")

            session = requests.Session()

            URL = "https://docs.google.com/uc?export=download"
            params = {"id": GOOGLE_DRIVE_FILE_ID}

            response = session.get(URL, params=params, stream=True)
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
            # Verify it's a valid SQLite database
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

            # Add headers to ensure proper download
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            with requests.get(DROPBOX_DIRECT_URL, stream=True, timeout=60, headers=headers) as r:
                r.raise_for_status()

                # Check if response is actually a database file
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
                                if percent % 10 == 0:  # Log every 10%
                                    print(f"[DB] Download progress: {percent}%")

                os.replace(DB_PATH + ".part", DB_PATH)

            # Verify the downloaded file is a valid SQLite database
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
            # Clean up partial download
            if os.path.exists(DB_PATH + ".part"):
                os.remove(DB_PATH + ".part")
            return False

def create_indexes():
    if not os.path.exists(DB_PATH):
        print("[DB] Database file not found. Skipping index creation.")
        return

    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        
        # Verify database is readable
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        print(f"[DB] Found tables: {tables}")
        
        # Create standard search column indexes
        for t in TABLES:
            if t not in tables:
                print(f"[DB] Table {t} not found in database, skipping...")
                continue
                
            for c in SEARCH_COLS:
                try:
                    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_{c} ON {t}({c})")
                except Exception as e:
                    print(f"[DB] Error creating index idx_{t}_{c} on table {t}: {e}")
        
        # Create optimized indexes for college and major searches
        for t in TABLES:
            if t not in tables:
                continue
                
            try:
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_allotedcollege ON {t}(allotedcollege)")
            except Exception as e:
                print(f"[DB] Error creating college index: {e}")
            
            try:
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_major ON {t}(major)")
            except Exception as e:
                print(f"[DB] Error creating major index: {e}")
            
            try:
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_allotedhonours ON {t}(allotedhonours)")
            except Exception as e:
                print(f"[DB] Error creating honours index: {e}")
            
            try:
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_college_major ON {t}(allotedcollege, major)")
            except Exception as e:
                print(f"[DB] Error creating composite college_major index: {e}")
            
            try:
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_college_honours ON {t}(allotedcollege, allotedhonours)")
            except Exception as e:
                print(f"[DB] Error creating composite college_honours index: {e}")
            
            try:
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_cname ON {t}(cname)")
            except Exception as e:
                print(f"[DB] Error creating name index: {e}")
        
        con.commit()
        con.close()
        print("[DB] Indexes created successfully.")
        
    except Exception as e:
        print(f"[DB] Error in create_indexes: {e}")

def execute_query(query, params=(), fetch_one=False):
    if not os.path.exists(DB_PATH):
        return [] if not fetch_one else None

    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
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
        if not success:
            print("[DB] Failed to download database. Retrying in 5 seconds...")
            time.sleep(5)
            download_db()
    else:
        print("[DB] Database already exists.")
    create_indexes()


