# messages/day_7a.py
import os
import discord
from discord.ui import View, Button
from typing import Tuple, Optional, List

def build_embed(join_url: str) -> Tuple[List[discord.Embed], Optional[View]]:
    title = "RESELLING SECRETS 50% OFF FLASH SALE"
    description = (
        "We're dropping some memberships for 50% off TODAY ONLY. We only sell a small number of spots — "
        "if you've been thinking about joining, this is the time.\n\n"
        "Use code **RS50** at checkout."
    )
    embed = discord.Embed(title=title, description=description)
    # optional footer banner (example earlier had an image); config via env variable:
    banner = os.environ.get("BANNER_DAY_7A")
    if banner:
        embed.set_image(url=banner)
    embed.set_footer(text="Limited quantity. First-come, first-served.")

    view = None
    if join_url:
        view = View(timeout=None)
        view.add_item(Button(label="JOIN THE GROUP NOW", url=join_url))
    return [embed], view
