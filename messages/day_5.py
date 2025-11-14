# messages/day_5.py
import os
import discord
from discord.ui import View, Button
from typing import Tuple, Optional, List

def build_embed(join_url: str) -> Tuple[List[discord.Embed], Optional[View]]:
    title = "Got questions? We got answers"
    description = (
        "Common questions: Do I need money to start? How long until I see results? "
        "Short answer: you can start with minimal cash and small, consistent actions build momentum."
    )
    embed = discord.Embed(title=title, description=description)
    banner = os.environ.get("BANNER_DAY_5")
    if banner:
        embed.set_image(url=banner)
    embed.set_footer(text="Reply here if you want a quick tip based on your situation.")

    view = None
    if join_url:
        view = View(timeout=None)
        view.add_item(Button(label="JOIN NOW", url=join_url))
    return [embed], view
