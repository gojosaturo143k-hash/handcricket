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
    1: "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/ChatGPT%20Image%20Aug%2016,%202026,%2004_38_39%20PM.png",
    2: "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_xhez2oxhez2oxhez.png",
    3: "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_wtt32ewtt32ewtt3.png",
    4: "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_8te7tv8te7tv8te7.png",
    5: "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_depbnndepbnndepb.png",
    6: "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_knb74cknb74cknb7.png",
    "OUT": "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_k6k9i5k6k9i5k6k9.png",
    "DUCK": "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_dimv5jdimv5jdimv.png",
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
