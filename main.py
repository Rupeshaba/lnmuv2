import uvicorn
import asyncio
import os
from pathlib import Path
import threading

from database.database import init_db, download_db, DOWNLOAD_STATUS
from api.api import app as fastapi_app
from telegram_bot.telegram_bot import run_telegram_bot
from config.config import TEMP_REPORTS_DIR

def start_telegram_bot_thread():
    """Start Telegram bot in a separate thread with its own event loop"""
    print("[MAIN] Starting Telegram bot in background thread...")
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the bot
        run_telegram_bot()
    except Exception as e:
        print(f"[MAIN] Telegram bot error: {e}")
        import traceback
        traceback.print_exc()

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

    # 4. Start Telegram bot in a separate daemon thread
    telegram_thread = threading.Thread(target=start_telegram_bot_thread, daemon=True)
    telegram_thread.start()
    print("[MAIN] Telegram bot thread started")

    # 5. Start FastAPI in the main thread (blocking call)
    print(f"[MAIN] Starting FastAPI server on 0.0.0.0:{port}...")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)

    print("[MAIN] Application shutdown.")

if __name__ == "__main__":
    main()
