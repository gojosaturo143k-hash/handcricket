import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")

AFK_TIMEOUT = 80
BALLS_PER_OVER = 6
MAX_CONSECUTIVE_DELIVERIES = 2
MAX_DELIVERIES_PER_OVER = 3
VALID_SHOTS = {"1", "2", "3", "4", "5", "6"}
