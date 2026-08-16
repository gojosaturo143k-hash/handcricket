import os
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
# RENDER AUTO-START TRICK FOR TELEGRAM BOT
# ==========================================
def start_telegram_bot():
    try:
        # Yahan bot.py ko import kar rahe hain
        import bot 
        
        # bot.py ke andar jo bot object hai, usko run kar rahe hain
        if hasattr(bot, 'bot'):
            logging.info("Starting Telegram Bot from alive.py...")
            bot.bot.run()
    except Exception as e:
        logging.error(f"Failed to start Telegram bot: {e}")

# Jab Gunicorn is file ko load karega, tab ye code automatically ek alag thread mein bot start kar dega
bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
bot_thread.start()
