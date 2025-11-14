from discord import Embed

BANNER_URL = "https://media.discordapp.net/attachments/1436108078612484189/1436115777265598555/image.png?ex=691851cb&is=6917004b&hm=6ceb6eaef75db74a83845ed98f3e26c4bb336353afa3202258b959690ad22350&=&format=webp&quality=lossless&width=2507&height=630"

def get_message(join_url: str):
    """
    Returns the embed and content for Day 1 of the DM sequence.
    """

    embed = Embed(
        title="Welcome to Divine Lite <a:Rocket:1171087916739600434>",
        description=(
            "You just joined our free server where we post tons of money-making info, completely free.\n\n"
            "Want to learn how we're helping hundreds of people make **thousands per month?** <:Evilrondo:1171087745356140746>\n\n"
            "Here's what you get access to in our main group 👇\n\n"
            "<a:fireball:778225346393931816> 50+ reselling coaches and experts\n"
            "<a:fireball:778225346393931816> Software to check your stores for thousands of clearance deals\n"
            "<a:fireball:778225346393931816> Alerts for **all** profitable flips\n"
            "<a:fireball:778225346393931816> Free auto checkout (we bot drops for you)\n"
            "...and much more\n\n"
            "If you want full access, you can claim a free week in the group below 😉\n\n"
            f"[**CLAIM YOUR FREE WEEK NOW**]({join_url})"
        ),
        color=0x5865F2
    )

    # Add your banner image at the top
    embed.set_image(url=BANNER_URL)

    return embed
