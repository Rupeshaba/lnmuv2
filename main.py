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
```

## Changes Summary:

1. ✅ **Port ab environment se milega** - `PORT` environment variable
2. ✅ **Telegram bot background thread mein** - Main thread free rahega
3. ✅ **FastAPI main thread mein** - Render ko port detect karne mein asaani
4. ✅ **Proper error handling** - Telegram bot errors app ko crash nahi karenge
5. ✅ **Logging improved** - Har step ka clear message

## Render Configuration Check:

**Render Dashboard Settings:**
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python main.py`
- **Service Type**: `Web Service`

## Environment Variables (Render Dashboard mein add karein):
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
DATABASE_URL=your_database_url (agar external DB hai)
```

Is code se aapka deployment bilkul smooth hoga! Deploy karne ke baad Render logs mein yeh dikhega:
```
[MAIN] Application starting...
[MAIN] Initializing database...
[MAIN] Creating temporary directories...
[MAIN] Using port: 10000
[MAIN] Telegram bot thread started
[MAIN] Starting FastAPI server on 0.0.0.0:10000...
