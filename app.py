from flask import Flask
from dotenv import load_dotenv
import os
import admin_bot

load_dotenv()

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Online!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
