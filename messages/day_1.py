# messages/day_1.py
import os
import discord
from discord.ui import View, Button
from typing import Tuple, Optional, List

def build_embed(join_url: str) -> Tuple[List[discord.Embed], Optional[View]]:
    title = "Welcome — here's where to start"
    description = (
        "Thanks for joining — we’re excited to have you. "
        "Start here: join the community, introduce yourself, and check the pinned guides."
    )
    embed = discord.Embed(title=title, description=description)
    banner = os.environ.get("BANNER_DAY_1")
    if banner:
        embed.set_image(url=banner)
    embed.set_footer(text="Want help? Reply to this DM or visit the support channel.")

    view = None
    if join_url:
        view = View(timeout=None)
        view.add_item(Button(label="JOIN NOW", url=join_url))
    return [embed], view
