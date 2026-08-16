import os
import asyncio
import threading
import logging
from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is online!", 200

@app.route('/health')
def health():
    return "Healthy", 200

# ==========================================
# FIXED ASYNC EVENT LOOP FOR TELEGRAM BOT
# ==========================================
def start_telegram_bot():
    try:
        import bot 
        
        # Python 3.10+ ke liye naya event loop banayein
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        logging.info("Starting Telegram Bot safely in background thread...")
        
        # Bot ko naye loop mein run karein
        loop.run_until_complete(bot.bot.start())
        loop.run_forever()
        
    except Exception as e:
        logging.error(f"Failed to start Telegram bot: {e}")

# Jab Gunicorn load karega, tab background mein bot start hoga
bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
bot_thread.start()
