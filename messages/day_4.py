# messages/day_4.py
import os
import discord
from discord.ui import View, Button
from typing import Tuple, Optional, List

def build_embed(join_url: str) -> Tuple[List[discord.Embed], Optional[View]]:
    title = "How we help — inside the group"
    description = (
        "We provide step-by-step checklists, tools, and weekly live breakdowns. "
        "If you like actionable systems instead of noise, this will fit."
    )
    embed = discord.Embed(title=title, description=description)
    banner = os.environ.get("BANNER_DAY_4")
    if banner:
        embed.set_image(url=banner)
    embed.set_footer(text="Pro tip: join a channel that matches your niche — start small.")

    view = None
    if join_url:
        view = View(timeout=None)
        view.add_item(Button(label="JOIN NOW", url=join_url))
    return [embed], view
