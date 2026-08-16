import os
import logging
from pyrogram import Client

logger = logging.getLogger(__name__)

# ==========================================
# APNE URLS YAHAN DAALO
# ==========================================
# Neeche 'YOUR_URL' ki jagah apne actual GIF/Image ke links daal do.
# Example: "https://telegra.ph/file/abc123.gif"
RESULT_ANIMATIONS = {
    1: "YOUR_URL_FOR_1_GIF",
    2: "YOUR_URL_FOR_2_GIF",
    3: "YOUR_URL_FOR_3_GIF",
    4: "YOUR_URL_FOR_4_GIF",
    5: "YOUR_URL_FOR_5_GIF",
    6: "YOUR_URL_FOR_6_GIF",
    "OUT": "YOUR_URL_FOR_OUT_GIF",
    "DUCK": "YOUR_URL_FOR_DUCK_GIF",
}

# Cache to save Telegram file_ids after first send (makes it blazing fast)
file_id_cache = {}

async def send_animation(client: Client, chat_id: int, key, reply_to_message_id=None):
    url = RESULT_ANIMATIONS.get(key)
    
    # Agar URL 'YOUR_URL...' jaisa hai (matlab user ne change nahi kiya), toh sirf text bhejo
    if not url or "YOUR_URL" in url:
        logger.warning(f"Animation URL not set for key {key}. Skipping.")
        return None

    file_id = file_id_cache.get(key)
    
    try:
        # Agar pehle se Telegram server pe save hai (cache), toh direct bhejo
        if file_id:
            return await client.send_animation(
                chat_id=chat_id, 
                animation=file_id, 
                reply_to_message_id=reply_to_message_id
            )
        else:
            # Pehli baar URL se bhej rahe hain
            msg = await client.send_animation(
                chat_id=chat_id, 
                animation=url,  # Pyrogram automatically handles URLs
                reply_to_message_id=reply_to_message_id
            )
            # Response se file_id nikal ke cache mein save kar lo
            if msg and msg.animation and msg.animation.file_id:
                file_id_cache[key] = msg.animation.file_id
            return msg
    except Exception as e:
        logger.error(f"Failed to send animation for {key}: {e}")
        return None
