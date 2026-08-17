import asyncio

# Image URLs for different events (will be sent with caption)
# Replace these with your own image URLs (Telegraph, Imgur, etc.)
IMAGE_URLS = {
    "toss": "https://i.imgur.com/JqYTdYn.png",
    "out": "https://i.imgur.com/6X5LmVj.png",
    "six": "https://i.imgur.com/8KqVxVH.png",
    "four": "https://i.imgur.com/4CxYlQz.png",
    "duck": "https://i.imgur.com/KjQZwXc.png",
    "win": "https://i.imgur.com/Y8gLz5t.png",
    "start": "https://i.imgur.com/mQvKxNJ.png",
}

# Cache file_id after first successful upload to avoid re-uploading
_file_id_cache = {}


async def send_image_with_caption(client, chat_id, image_type, caption):
    """
    Send an image with caption text.
    If image sending fails, falls back to sending just the caption as text.
    Returns the sent message or None.
    """
    url = IMAGE_URLS.get(image_type)
    
    if not url:
        # No URL for this type, just send caption
        if caption:
            try:
                from pyrogram.enums import ParseMode
                return await client.send_message(chat_id, caption, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                try:
                    return await client.send_message(chat_id, caption)
                except Exception:
                    pass
        return None

    try:
        from pyrogram.enums import ParseMode
        
        # Try cached file_id first (faster, no re-upload)
        if image_type in _file_id_cache:
            msg = await client.send_photo(
                chat_id=chat_id,
                photo=_file_id_cache[image_type],
                caption=caption or "",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            # First time - send by URL, Telegram will download & cache it
            msg = await client.send_photo(
                chat_id=chat_id,
                photo=url,
                caption=caption or "",
                parse_mode=ParseMode.MARKDOWN,
            )
            # Cache the file_id for future use
            if msg and msg.photo:
                _file_id_cache[image_type] = msg.photo.file_id
        return msg
    except Exception as e:
        # Image failed (URL broken, network issue, etc.)
        # Fallback: just send the caption as a text message
        if caption:
            try:
                from pyrogram.enums import ParseMode
                return await client.send_message(chat_id, caption, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                try:
                    return await client.send_message(chat_id, caption)
                except Exception:
                    pass
        return None
