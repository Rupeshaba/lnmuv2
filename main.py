import uvicorn

import threading

import os

from pathlib import Path



from database.database import init_db, DOWNLOAD_STATUS

from api.api import app as fastapi_app

from telegram_bot.telegram_bot import run_telegram_bot

from config.config import TEMP_REPORTS_DIR



def init_db_background():

    """Download and initialize DB in background after server is up."""

    print("[MAIN] Background DB init started...")

    try:

        init_db()

        print("[MAIN] Background DB init complete.")

    except Exception as e:

        print(f"[MAIN] Background DB init FAILED: {e}")



def start_telegram_bot():

    """Run telegram bot in a background thread."""

    print("[BOT] Initializing Telegram Bot...")

    try:

        run_telegram_bot()

    except Exception as e:

        print(f"[BOT] Telegram bot stopped: {e}")



def main():

    # Create temp reports directory

    Path(TEMP_REPORTS_DIR).mkdir(exist_ok=True)



    # 1. Start DB download in background (non-blocking)

    db_thread = threading.Thread(target=init_db_background, daemon=True)

    db_thread.start()



    # 2. Start Telegram bot in background thread

    bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)

    bot_thread.start()



    # 3. Start FastAPI in main thread — port bind FIRST for Render health check

    port = int(os.environ.get("PORT", 8000))

    print(f"[MAIN] Starting FastAPI on port {port}...")

    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)



    print("[MAIN] Application shutdown.")



if __name__ == "__main__":

    main()

