import discord

BANNER_URL = "https://media.discordapp.net/attachments/1436108078612484189/1436115777265598555/image.png"

def get_message(join_url: str):
    embed = discord.Embed(
        title="WALMART SELLING MACBOOKS FOR $23<a:PartyBear:774254653197647892>",
        description=(
            "Walmart is marking down Macbook Airs as low as **$23** at select stores.\n\n"
            "Our software lets Divine members check **all stores within 50 miles** of their home "
            "to instantly see whether their stores have the deal.\n\n"
            "Want access?👇"
        ),
        color=0x5865F2
    )

    embed.set_image(url=BANNER_URL)

    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="CLAIM YOUR FREE WEEK NOW",
        url=join_url,
        style=discord.ButtonStyle.link
    ))

    return embed, view
