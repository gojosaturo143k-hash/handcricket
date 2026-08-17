import asyncio

GIF_URLS = {
    "toss": "https://telegra.ph/file/a4116640c5765c25b0c85.gif",
    "out": "https://telegra.ph/file/b3d3e3f1a0c2d4e5f6a7.gif",
    "six": "https://telegra.ph/file/c4d5e6f7a8b9c0d1e2f3.gif",
    "four": "https://telegra.ph/file/d5e6f7a8b9c0d1e2f3a4.gif",
    "duck": "https://telegra.ph/file/e6f7a8b9c0d1e2f3a4b5.gif",
    "win": "https://telegra.ph/file/f7a8b9c0d1e2f3a4b5c6.gif",
    "start": "https://telegra.ph/file/a8b9c0d1e2f3a4b5c6d7.gif",
}

_file_id_cache = {}


async def send_gif(client, chat_id, gif_type, caption=None):
    """Send a GIF by URL, caching file_id after first upload."""
    url = GIF_URLS.get(gif_type)
    if not url:
        return None

    try:
        if gif_type in _file_id_cache:
            msg = await client.send_animation(
                chat_id=chat_id,
                animation=_file_id_cache[gif_type],
                caption=caption or "",
            )
        else:
            msg = await client.send_animation(
                chat_id=chat_id,
                animation=url,
                caption=caption or "",
            )
            if msg and msg.animation:
                _file_id_cache[gif_type] = msg.animation.file_id
        return msg
    except Exception:
        # If GIF fails, just send the caption as text
        if caption:
            try:
                return await client.send_message(chat_id, caption)
            except Exception:
                pass
        return None
