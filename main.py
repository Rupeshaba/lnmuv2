import uvicorn
import threading
import os
from pathlib import Path
import shutil

from database.database import init_db, download_db, DOWNLOAD_STATUS
from api.api import app as fastapi_app
from telegram_bot.telegram_bot import run_telegram_bot
from config.config import TEMP_REPORTS_DIR

def start_fastapi():
    print("[MAIN] Starting FastAPI application...")
    # Use a try-except block to gracefully handle uvicorn shutdown if needed
    try:
        uvicorn.run(fastapi_app, host="0.0.0.0", port=8000)
    except Exception as e:
        print(f"[MAIN] FastAPI server stopped: {e}")

def main():
    # 1. Initialize DB (download if not exists, create indexes)
    print("[MAIN] Initializing database...")
    init_db()

    # Create temp reports directory if it doesn't exist
    Path(TEMP_REPORTS_DIR).mkdir(exist_ok=True)

    # 2. Start FastAPI in a separate thread
    fastapi_thread = threading.Thread(target=start_fastapi, daemon=True)
    fastapi_thread.start()

    # 3. Start Telegram bot in the main thread (blocking call)
    run_telegram_bot()

    print("[MAIN] Application shutdown.")

if __name__ == "__main__":
    main()
