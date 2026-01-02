import uvicorn
import threading
import os
from pathlib import Path

from database.database import init_db
from api.api import app as fastapi_app
from telegram_bot.telegram_bot import run_telegram_bot
from config.config import TEMP_REPORTS_DIR


def start_telegram_bot():
    print("[MAIN] Starting Telegram bot...")
    run_telegram_bot()


def main():
    print("[MAIN] Initializing database...")
    init_db()

    Path(TEMP_REPORTS_DIR).mkdir(exist_ok=True)

    # 🔥 Telegram bot in background thread
    bot_thread = threading.Thread(
        target=start_telegram_bot,
        daemon=True
    )
    bot_thread.start()

    # 🔥 FastAPI MUST be in main thread (Render rule)
    port = int(os.environ.get("PORT", 10000))

    print(f"[MAIN] Starting FastAPI on port {port}")

    uvicorn.run(
        fastapi_app,
        host="0.0.0.0",
        port=port
    )


if __name__ == "__main__":
    main()
