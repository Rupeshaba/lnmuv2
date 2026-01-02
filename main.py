import os
import threading
from flask import Flask, jsonify

from database.database import init_db
from telegram_bot.telegram_bot import run_telegram_bot

app = Flask(__name__)


def start_telegram_bot():
    print("[BOT] Telegram bot starting...")
    run_telegram_bot()


@app.route("/")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("[MAIN] Initializing database...")
    init_db()

    # 🔥 Telegram bot background me
    bot_thread = threading.Thread(
        target=start_telegram_bot,
        daemon=True
    )
    bot_thread.start()

    # 🔥 Render compatible port
    port = int(os.environ.get("PORT", 10000))
    print(f"[MAIN] Flask running on port {port}")

    app.run(
        host="0.0.0.0",
        port=port
    )
