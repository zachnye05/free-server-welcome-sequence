# config.py
import os

# Discord
TOKEN = os.environ.get("TOKEN")
GUILD_ID = int(os.environ.get("GUILD_ID", "123456789012345678"))

# Roles
ROLE_TRIGGER   = int(os.environ.get("ROLE_TRIGGER", "1222877651438407731"))
ROLE_CANCEL_A  = int(os.environ.get("ROLE_CANCEL_A", "876569612085518376"))
ROLE_CANCEL_B  = int(os.environ.get("ROLE_CANCEL_B", "1158658514458263592"))

FORMER_MEMBER_ROLE = int(os.environ.get("FORMER_MEMBER_ROLE", "1021886425530109994"))
FORMER_MEMBER_DELAY_SECONDS = int(os.environ.get("FORMER_MEMBER_DELAY_SECONDS", "60"))

ROLES_TO_CHECK = {
    ROLE_TRIGGER,
    ROLE_CANCEL_A,
    ROLE_CANCEL_B,
    876598078092754985,
    883907048255942736,
    876588092927115284,
    1337919015992954881,
    1299919622685986817,
    1221889762575781908,
    1224748748920328384,
}

LOG_FIRST_CHANNEL_ID = int(os.environ.get("LOG_FIRST_CHANNEL_ID", "1144408172757536768"))
LOG_OTHER_CHANNEL_ID = int(os.environ.get("LOG_OTHER_CHANNEL_ID", "1358977007030898719"))

# Timing
SEND_SPACING_SECONDS = float(os.environ.get("SEND_SPACING_SECONDS", "30"))
DAY_GAP_HOURS = int(os.environ.get("DAY_GAP_HOURS", "24"))

# Storage
QUEUE_FILE = os.environ.get("QUEUE_FILE", "storage/queue.json")
REGISTRY_FILE = os.environ.get("REGISTRY_FILE", "storage/registry.json")

# Message order – now ONLY 7 days, with day_7a as final
DAY_KEYS = ["day_1","day_2","day_3","day_4","day_5","day_6","day_7a"]

# Links – no day_7b
UTM_LINKS = {
    "day_1":  os.environ.get("LINK_DAY_1",  "https://your-divine-link.com/?utm_source=discord&utm_campaign=dm_day_1"),
    "day_2":  os.environ.get("LINK_DAY_2",  "https://your-divine-link.com/?utm_source=discord&utm_campaign=dm_day_2"),
    "day_3":  os.environ.get("LINK_DAY_3",  "https://your-divine-link.com/?utm_source=discord&utm_campaign=dm_day_3"),
    "day_4":  os.environ.get("LINK_DAY_4",  "https://your-divine-link.com/?utm_source=discord&utm_campaign=dm_day_4"),
    "day_5":  os.environ.get("LINK_DAY_5",  "https://your-divine-link.com/?utm_source=discord&utm_campaign=dm_day_5"),
    "day_6":  os.environ.get("LINK_DAY_6",  "https://your-divine-link.com/?utm_source=discord&utm_campaign=dm_day_6"),
    "day_7a": os.environ.get("LINK_DAY_7A", "https://your-divine-link.com/?utm_source=discord&utm_campaign=dm_day_7a"),
}

