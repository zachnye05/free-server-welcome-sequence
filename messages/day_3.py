# messages/day_3.py
import os
import discord
from discord.ui import View, Button
from typing import Tuple, Optional, List

def build_embed(join_url: str) -> Tuple[List[discord.Embed], Optional[View]]:
    title = "Success stories — real results"
    description = (
        "Members are sharing wins every day — from reselling flips to automation wins. "
        "If you want results, follow the pinned 'How to Win' guide and copy the systems."
    )
    embed = discord.Embed(title=title, description=description)
    banner = os.environ.get("BANNER_DAY_3")
    if banner:
        embed.set_image(url=banner)
    embed.set_footer(text="See the #wins channel in server for the latest posts.")

    view = None
    if join_url:
        view = View(timeout=None)
        view.add_item(Button(label="JOIN NOW", url=join_url))
    return [embed], view
