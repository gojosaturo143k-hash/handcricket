import asyncio

# Image URLs for different events (replace with your own URLs)
# Supported: out, duck, 1, 2, 3, 4, 5, 6
IMAGE_URLS = {
    "out": "",    # Wicket/OUT image
    "duck": "",   # Duck (0 runs out) image
    "1": "",      # 1 run image
    "2": "",      # 2 runs image
    "3": "",      # 3 runs image
    "4": "",      # 4 runs (boundary) image
    "5": "",      # 5 runs image
    "6": "",      # 6 runs (six) image
}

# Cache file_id after first successful upload to avoid re-uploading
_file_id_cache = {}


async def send_image_with_caption(client, chat_id, image_type, caption):
    """
    Send an image with caption text.
    image_type can be: "out", "duck", "1", "2", "3", "4", "5", "6"
    If image URL is empty or sending fails, just sends the caption as text.
    """
    url = IMAGE_URLS.get(str(image_type), "")
    
    # If no URL set, just send text
    if not url:
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
            # First time - send by URL
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
    except Exception:
        # Image failed - fallback to text
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
