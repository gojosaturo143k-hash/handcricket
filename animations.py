import asyncio

# Image URLs for different events (replace with your own URLs)
# Supported: out, duck, 1, 2, 3, 4, 5, 6
IMAGE_URLS = {
    "out": "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_k6k9i5k6k9i5k6k9.png",    # Wicket/OUT image
    "duck": "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_dimv5jdimv5jdimv.png",   # Duck (0 runs out) image
    "1": "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/ChatGPT%20Image%20Aug%2016,%202026,%2004_38_39%20PM.png",      # 1 run image
    "2": "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_xhez2oxhez2oxhez.png",      # 2 runs image
    "3": "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_wtt32ewtt32ewtt3.png",      # 3 runs image
    "4": "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_8te7tv8te7tv8te7.png",      # 4 runs (boundary) image
    "5": "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_depbnndepbnndepb.png",      # 5 runs image
    "6": "https://lhcrcxfpkyniyvaldefr.supabase.co/storage/v1/object/public/cricketbot/Gemini_Generated_Image_knb74cknb74cknb7.png",      # 6 runs (six) image
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
