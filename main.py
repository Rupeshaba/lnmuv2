import uvicorn
import asyncio
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI

from database.database import init_db, DOWNLOAD_STATUS
from api.api import app as _api_routes
from config.config import TEMP_REPORTS_DIR, BOT_TOKEN
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters
)
from telegram_bot.telegram_bot import (
    start_command, search_command, message_handler, callback_handler
)


def _build_telegram_app():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))
    return application


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    Path(TEMP_REPORTS_DIR).mkdir(exist_ok=True)

    # 1. DB download as a proper asyncio background task
    async def init_db_async():
        print("[MAIN] Background DB init started...")
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, init_db)
            print("[MAIN] Background DB init complete.")
        except Exception as e:
            print(f"[MAIN] Background DB init FAILED: {e}")

    db_task = asyncio.create_task(init_db_async())

    # 2. Start Telegram bot in the SAME event loop as uvicorn — no threads
    print("[BOT] Initializing Telegram Bot...")
    telegram_app = _build_telegram_app()
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    print("[BOT] Bot Running (Polling Mode)...")

    yield  # ── app is live ───────────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────
    print("[BOT] Stopping Telegram Bot...")
    await telegram_app.updater.stop()
    await telegram_app.stop()
    await telegram_app.shutdown()
    db_task.cancel()
    print("[MAIN] Application shutdown.")


# Attach lifespan + copy all routes from the existing api app
app = FastAPI(
    title="LNMU Search API",
    description="API for searching student data and generating reports",
    version="1.0.0",
    lifespan=lifespan,
)
for route in _api_routes.routes:
    app.routes.append(route)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"[MAIN] Starting FastAPI on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
