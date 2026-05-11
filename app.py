from flask import Flask
import threading
import os
from dotenv import load_dotenv

load_dotenv()

from bot import run_bot

app = Flask(__name__)

@app.route('/')
def home():
    return "Nexus Selling Bot is Online!"

def start_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # Flask runs in a background daemon thread (no asyncio needed)
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # Bot runs on the MAIN thread — required for asyncio event loop on Python 3.10+
    run_bot()