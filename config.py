import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
PORT = int(os.environ.get("PORT", "8080"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
AFK_TIMEOUT = 80
MAX_SAME_BALL_PER_OVER = 2
BALLS_PER_OVER = 6
