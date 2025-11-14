# messages/day_6.py
import os
import discord
from discord.ui import View, Button
from typing import Tuple, Optional, List

def build_embed(join_url: str) -> Tuple[List[discord.Embed], Optional[View]]:
    title = "Almost there — don't miss this"
    description = (
        "We usually keep the cohort small to preserve quality. If you’re on the fence, this is a good time to join — "
        "you’ll get immediate access to tools and the private channels."
    )
    embed = discord.Embed(title=title, description=description)
    banner = os.environ.get("BANNER_DAY_6")
    if banner:
        embed.set_image(url=banner)
    embed.set_footer(text="Limited spots help keep the community focused and useful.")

    view = None
    if join_url:
        view = View(timeout=None)
        view.add_item(Button(label="JOIN NOW", url=join_url))
    return [embed], view
