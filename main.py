import uvicorn
import threading
import os
from pathlib import Path
import shutil

from database.database import init_db, download_db, DOWNLOAD_STATUS
from api.api import app as fastapi_app
from telegram_bot.telegram_bot import run_telegram_bot
from config.config import TEMP_REPORTS_DIR

def start_telegram_bot():
    """Start Telegram bot in background thread"""
    print("[MAIN] Starting Telegram bot...")
    try:
        run_telegram_bot()
    except Exception as e:
        print(f"[MAIN] Telegram bot error: {e}")

def main():
    print("[MAIN] Application starting...")
    
    # 1. Initialize DB (download if not exists, create indexes)
    print("[MAIN] Initializing database...")
    init_db()

    # 2. Create temp reports directory if it doesn't exist
    print("[MAIN] Creating temporary directories...")
    Path(TEMP_REPORTS_DIR).mkdir(exist_ok=True)

    # 3. Get port from environment (Render automatically sets this)
    port = int(os.environ.get("PORT", 8000))
    print(f"[MAIN] Using port: {port}")

    # 4. Start Telegram bot in a separate background thread
    telegram_thread = threading.Thread(target=start_telegram_bot, daemon=True)
    telegram_thread.start()
    print("[MAIN] Telegram bot thread started")

    # 5. Start FastAPI in the main thread (blocking call)
    # This ensures Render can detect the open port
    print(f"[MAIN] Starting FastAPI server on 0.0.0.0:{port}...")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)

    print("[MAIN] Application shutdown.")

if __name__ == "__main__":
    main()
