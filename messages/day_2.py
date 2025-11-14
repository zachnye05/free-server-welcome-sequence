# messages/day_2.py
import os
import discord
from discord.ui import View, Button
from typing import Tuple, Optional, List

def build_embed(join_url: str) -> Tuple[List[discord.Embed], Optional[View]]:
    title = "Quick reminder — don’t miss this"
    description = (
        "Hey — just checking in. If you haven’t yet, grab the free resources and check the most popular threads. "
        "Lots of wins get posted daily."
    )
    embed = discord.Embed(title=title, description=description)
    banner = os.environ.get("BANNER_DAY_2")
    if banner:
        embed.set_image(url=banner)
    embed.set_footer(text="Small actions compound — start today.")

    view = None
    if join_url:
        view = View(timeout=None)
        view.add_item(Button(label="JOIN NOW", url=join_url))
    return [embed], view
