from flask import Flask
import threading
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Online!"

def run_telegram_bot():
    import admin_bot

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port),
        daemon=True
    )
    flask_thread.start()

    run_telegram_bot()
