import discord
from typing import Tuple, List, Optional

BANNER_URL = "https://cdn.discordapp.com/attachments/1435678774921269432/1440814266021187765/image.png"
IMAGE_URL = "https://cdn.discordapp.com/attachments/1436108078612484189/1436115777265598555/image.png"

def build_embed(join_url: str) -> Tuple[List[discord.Embed], Optional[discord.ui.View]]:
    # --- Embed 1: Banner only ---
    banner_embed = discord.Embed(color=0x2b2d31)  # neutral dark color
    banner_embed.set_image(url=BANNER_URL)

    # --- Embed 2: Main message ---
    main_embed = discord.Embed(
        title="WALMART SELLING MACBOOKS FOR $23<a:PartyBear:774254653197647892>",
        description=(
            "Walmart is marking down Macbook Airs as low as **$23** at select stores.\n\n"
            "Our software lets Divine members check *all* stores within 50 miles of their home for the deal.\n\n"
            "Want access?👇\n\n"
            f"[**CLAIM YOUR FREE WEEK NOW**]({join_url})"
        ),
        color=0x5865F2
    )

    main_embed.set_image(url=IMAGE_URL)

    return [banner_embed, main_embed], None
