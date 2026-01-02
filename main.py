import uvicorn
import asyncio
import os
from pathlib import Path

from database.database import init_db
from api.api import app as fastapi_app
from telegram_bot.telegram_bot import get_bot_application
from config.config import TEMP_REPORTS_DIR

async def run_both():
    """Run both FastAPI and Telegram bot concurrently"""
    print("[MAIN] Starting both services...")
    
    # Get Telegram bot application
    bot_app = get_bot_application()
    
    # Start bot initialization
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    print("[BOT] Telegram bot started successfully")
    
    # Configure uvicorn
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    # Run FastAPI server
    await server.serve()

def main():
    print("[MAIN] Application starting...")
    
    # 1. Initialize DB (download if not exists, create indexes)
    print("[MAIN] Initializing database...")
    init_db()

    # 2. Create temp reports directory
    print("[MAIN] Creating temporary directories...")
    Path(TEMP_REPORTS_DIR).mkdir(exist_ok=True)

    # 3. Get port from environment
    port = int(os.environ.get("PORT", 8000))
    print(f"[MAIN] Using port: {port}")

    # 4. Run both services in async mode
    print(f"[MAIN] Starting services...")
    try:
        asyncio.run(run_both())
    except KeyboardInterrupt:
        print("[MAIN] Shutting down...")

if __name__ == "__main__":
    main()
