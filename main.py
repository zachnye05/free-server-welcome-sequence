# main.py
import os
import json
import asyncio
import traceback
from datetime import datetime, timedelta, timezone
import importlib
import importlib.util
import logging
from typing import Dict, Optional, Tuple, List, Any
from contextlib import suppress

import discord
from discord.ext import commands, tasks

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("divine-dm-seq")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Accept commands via . or ! and when the bot is mentioned
bot = commands.Bot(command_prefix=commands.when_mentioned_or(".", "!"), intents=intents)

# -- State
queue_state: Dict[str, Dict[str, str]] = {}
registry: Dict[str, Dict[str, str]] = {}
last_send_at: Optional[datetime] = None
pending_checks: set[int] = set()
pending_former_checks: set[int] = set()

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _ensure_storage():
    os.makedirs(os.path.dirname(config.QUEUE_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(config.REGISTRY_FILE), exist_ok=True)

def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        if os.path.getsize(path) == 0:
            return {}
        with open(path, "r") as f:
            data = f.read().strip()
            return {} if not data else json.loads(data)
    except Exception as e:
        log.error(f"Failed to read {path}: {e}. Treating as empty.")
        return {}

def save_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

def save_all():
    save_json(config.QUEUE_FILE, queue_state)
    save_json(config.REGISTRY_FILE, registry)

def _fmt_user(member: discord.abc.User) -> str:
    return f"{member} ({member.id})"

async def log_first(msg: str):
    ch = bot.get_channel(config.LOG_FIRST_CHANNEL_ID)
    if ch:
        with suppress(Exception):
            await ch.send(msg)

async def log_other(msg: str):
    ch = bot.get_channel(config.LOG_OTHER_CHANNEL_ID)
    if ch:
        with suppress(Exception):
            await ch.send(msg)

def has_sequence_before(user_id: int) -> bool:
    return str(user_id) in registry

def mark_started(user_id: int):
    uid = str(user_id)
    if uid not in registry:
        registry[uid] = {"started_at": _now().isoformat(), "completed": False}
        save_json(config.REGISTRY_FILE, registry)

def mark_cancelled(user_id: int, reason: str):
    uid = str(user_id)
    if uid not in registry:
        registry[uid] = {"started_at": _now().isoformat()}
    registry[uid]["completed"] = True
    registry[uid]["cancel_reason"] = reason
    queue_state.pop(uid, None)
    save_all()

def mark_finished(user_id: int):
    uid = str(user_id)
    if uid not in registry:
        registry[uid] = {"started_at": _now().isoformat()}
    registry[uid]["completed"] = True
    registry[uid]["cancel_reason"] = "finished"
    queue_state.pop(uid, None)
    save_all()

def enqueue_first_day(user_id: int):
    queue_state[str(user_id)] = {
        "current_day": "day_1",
        "next_send": _now().isoformat().replace("+00:00", "Z"),
    }
    save_json(config.QUEUE_FILE, queue_state)
    mark_started(user_id)

def schedule_next(user_id: int, current_day: str):
    uid = str(user_id)
    if current_day not in config.DAY_KEYS:
        mark_cancelled(user_id, "internal_error_bad_day")
        return

    idx = config.DAY_KEYS.index(current_day)
    # If we are on the last configured day, mark finished
    if idx >= len(config.DAY_KEYS) - 1:
        mark_finished(user_id)
        return

    next_day = config.DAY_KEYS[idx + 1]
    delay = timedelta(hours=config.DAY_GAP_HOURS)
    next_time = _now() + delay

    queue_state[uid] = {
        "current_day": next_day,
        "next_send": next_time.isoformat().replace("+00:00", "Z"),
    }
    save_json(config.QUEUE_FILE, queue_state)

def is_due(next_send_iso: str) -> bool:
    try:
        nxt = datetime.fromisoformat(next_send_iso.replace("Z", "+00:00"))
        return _now() >= nxt
    except Exception:
        return True

def has_cancel_role(member: discord.Member) -> bool:
    role_ids = {r.id for r in member.roles}
    return (config.ROLE_CANCEL_A in role_ids) or (config.ROLE_CANCEL_B in role_ids)

def has_trigger_role(member: discord.Member) -> bool:
    return any(r.id == config.ROLE_TRIGGER for r in member.roles)

def has_member_role(member: discord.Member) -> bool:
    return any(r.id == config.ROLE_CANCEL_A for r in member.roles)

def has_former_member_role(member: discord.Member) -> bool:
    return any(r.id == config.FORMER_MEMBER_ROLE for r in member.roles)


# -------------------------
# Standardized view for all messages
# -------------------------
def make_standard_view(join_url: Optional[str]):
    """
    Returns a discord.ui.View that contains:
      - a disabled green button labeled "$50M+ Profit" (visual only)
      - a link button labeled "JOIN NOW" that opens join_url
    """
    v = discord.ui.View(timeout=None)
    # Disabled green button (visual)
    try:
        v.add_item(discord.ui.Button(label="$50M+ Profit", style=discord.ButtonStyle.success, disabled=True))
    except Exception:
        pass

    # Link button
    if join_url:
        try:
            v.add_item(discord.ui.Button(label="JOIN NOW", url=join_url, style=discord.ButtonStyle.link))
        except Exception:
            pass
    return v


# -------------------------
# Message module loader + normalizer
# -------------------------
def load_message_module(day_key: str) -> Optional[Any]:
    """
    Returns the imported module or None if it doesn't exist.
    """
    module_name = f"messages.{day_key}"
    if importlib.util.find_spec(module_name) is None:
        return None
    try:
        return importlib.import_module(module_name)
    except Exception as e:
        log.warning(f"Failed importing module {module_name}: {e}")
        return None

def normalize_message_output(mod: Any, join_url: Optional[str]) -> Tuple[List[discord.Embed], Optional[discord.ui.View]]:
    """
    Normalize message module output to (List[Embed], View|None).
    Accepts:
      - build_embed(join_url=...) -> (List[Embed], View|None)
      - get_message(join_url) -> Embed or (Embed, View)
    If returned view is None, make_standard_view(join_url) will be used by the sender.
    """
    # build_embed preferred
    if hasattr(mod, "build_embed"):
        res = mod.build_embed(join_url=join_url)
        if isinstance(res, tuple) and len(res) == 2:
            embeds, view = res
            if not isinstance(embeds, (list, tuple)):
                embeds = [embeds]
            return list(embeds), view
        # if somebody returned just embeds
        if isinstance(res, (list, tuple)):
            return list(res), None

    # fallback to get_message
    if hasattr(mod, "get_message"):
        res = mod.get_message(join_url)
        if isinstance(res, tuple) and len(res) == 2:
            embeds, view = res
            if not isinstance(embeds, (list, tuple)):
                embeds = [embeds]
            return list(embeds), view
        else:
            if not isinstance(res, (list, tuple)):
                return [res], None
            else:
                return list(res), None

    raise RuntimeError("Message module has no `build_embed` or `get_message`.")


# -------------------------
# Sending helpers
# -------------------------
async def send_embeds_with_view(target: discord.abc.Messageable, embeds: List[discord.Embed], view: Optional[discord.ui.View], join_url: Optional[str]=None):
    """
    Sends a list of embeds such that:
      - all embeds except the last are sent without a view
      - the last embed is sent with the provided view; if view is None, main.py will attach a standard view (JOIN NOW)
    """
    if not embeds:
        return

    # send all but last without view
    for e in embeds[:-1]:
        try:
            await target.send(embed=e)
        except Exception as e:
            log.warning(f"Failed to send non-action embed to {target}: {e}")

    # last embed: attach view (or generated standard view)
    last = embeds[-1]
    final_view = view if view is not None else make_standard_view(join_url)
    try:
        if final_view:
            await target.send(embed=last, view=final_view)
        else:
            await target.send(embed=last)
    except Exception as e:
        log.warning(f"Failed to send final embed to {target}: {e}")
        raise


async def send_day(member: discord.Member, day_key: str):
    """
    Send one day's message. If the module is missing, SKIP the day (do not cancel the user's sequence).
    If UTM missing for that day, SKIP the day.
    """
    global last_send_at

    # rate spacing between DMs
    if last_send_at:
        delta = (_now() - last_send_at).total_seconds()
        if delta < config.SEND_SPACING_SECONDS:
            await asyncio.sleep(config.SEND_SPACING_SECONDS - delta)

    # cancel pre-checks
    if has_cancel_role(member):
        mark_cancelled(member.id, "cancel_role_present_pre_send")
        await log_other(f"🛑 Cancelled pre-send for {_fmt_user(member)} — cancel role present.")
        return

    # load module (skip if missing)
    mod = load_message_module(day_key)
    if mod is None:
        await log_other(f"ℹ️ Skipping {day_key} for {_fmt_user(member)} — module not found.")
        return

    # get join_url (skip if missing)
    join_url = config.UTM_LINKS.get(day_key)
    if not join_url:
        await log_other(f"ℹ️ Skipping {day_key} for {_fmt_user(member)} — UTM link missing.")
        return

    # normalize content
    try:
        embeds, view = normalize_message_output(mod, join_url)
    except Exception as e:
        await log_other(f"⚠️ Skipping {day_key} for {_fmt_user(member)} — message build error: `{e}`")
        return

    # send banner/embed sequence: banner(s) first, final embed with view
    try:
        await send_embeds_with_view(member, embeds, view, join_url=join_url)
        last_send_at = _now()
        if day_key == "day_1":
            await log_first(f"✅ Sent **{day_key}** to {_fmt_user(member)}")
        else:
            await log_other(f"✅ Sent **{day_key}** to {_fmt_user(member)}")
    except discord.Forbidden:
        mark_cancelled(member.id, "dm_forbidden")
        await log_other(f"🚫 DM forbidden for {_fmt_user(member)} — sequence cancelled.")
    except Exception as e:
        await log_other(f"⚠️ Failed to send **{day_key}** to {_fmt_user(member)}: `{e}`")


# -------------------------
# Scheduler loop
# -------------------------
@tasks.loop(seconds=10)
async def scheduler_loop():
    try:
        if not bot.is_ready():
            return
        guild = bot.get_guild(config.GUILD_ID)
        if not guild:
            return

        for uid, payload in list(queue_state.items()):
            try:
                day_key = payload.get("current_day")
                next_send = payload.get("next_send", "")
                if not day_key or not is_due(next_send):
                    continue

                member = guild.get_member(int(uid))
                if not member:
                    mark_cancelled(int(uid), "left_guild")
                    await log_other(f"👋 User `{uid}` left guild — sequence cancelled.")
                    continue

                if has_cancel_role(member):
                    mark_cancelled(member.id, "cancel_role_present")
                    await log_other(f"🛑 Cancelled for {_fmt_user(member)} — cancel role present.")
                    continue

                # send day (this function will SKIP missing modules instead of cancelling)
                await send_day(member, day_key)

                # if user still in queue, schedule next
                if str(member.id) in queue_state:
                    prev = day_key
                    schedule_next(member.id, day_key)
                    nxt = queue_state.get(str(member.id))
                    if nxt:
                        target_ch = log_other if prev != "day_1" else log_first
                        await target_ch(
                            f"🗓️ Scheduled **{nxt['current_day']}** for {_fmt_user(member)} at `{nxt['next_send']}`"
                        )
            except Exception as e:
                await log_other(f"⚠️ scheduler_loop user error for uid `{uid}`: `{e}`")
    except Exception as e:
        await log_other(f"❌ scheduler_loop tick error: `{e}`")


@scheduler_loop.error
async def scheduler_loop_error(error):
    await log_other(f"🔁 scheduler_loop crashed: `{error}` — restarting in 5s")
    with suppress(Exception):
        scheduler_loop.cancel()
    await asyncio.sleep(5)
    with suppress(Exception):
        scheduler_loop.start()


# -------------------------
# Boot & events
# -------------------------
@bot.event
async def on_ready():
    global queue_state, registry
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    _ensure_storage()
    queue_state = load_json(config.QUEUE_FILE)
    registry = load_json(config.REGISTRY_FILE)

    # nudge any overdue sends to 5s in the future to process immediately
    for uid, payload in queue_state.items():
        iso = payload.get("next_send")
        if not iso or is_due(iso):
            payload["next_send"] = (_now() + timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    save_json(config.QUEUE_FILE, queue_state)

    if not scheduler_loop.is_running():
        scheduler_loop.start()

    await log_other("🟢 [BOOT] Scheduler started and state restored.")

    guild = bot.get_guild(config.GUILD_ID)
    if guild:
        scheduled = 0
        for m in guild.members:
            if not m.bot and not any(r.id in config.ROLES_TO_CHECK for r in m.roles):
                asyncio.create_task(check_and_assign_role(m))
                scheduled += 1
        if scheduled:
            await log_other(f"🔍 Scheduled fallback role checks for **{scheduled}** member(s) on boot.")


@bot.event
async def on_member_join(member: discord.Member):
    if member.guild.id == config.GUILD_ID and not member.bot:
        await log_other(f"👤 New member joined: **{member.display_name}** (`{member.id}`) — checking roles in 60s")
        asyncio.create_task(check_and_assign_role(member))


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    before_roles = {r.id for r in before.roles}
    after_roles  = {r.id for r in after.roles}

    if (config.ROLE_CANCEL_A in after_roles or config.ROLE_CANCEL_B in after_roles) and str(after.id) in queue_state:
        mark_cancelled(after.id, "cancel_role_added")
        await log_other(f"🛑 Cancelled for {_fmt_user(after)} — cancel role added.")
        return

    if config.ROLE_TRIGGER not in before_roles and config.ROLE_TRIGGER in after_roles:
        if has_sequence_before(after.id):
            await log_other(f"⏭️ Skipped start for {_fmt_user(after)} — sequence previously run.")
            return
        enqueue_first_day(after.id)
        await log_first(f"🧵 Enqueued **day_1** for {_fmt_user(after)} (trigger role added)")
        return

    had_checked = any(r.id in config.ROLES_TO_CHECK for r in before.roles)
    has_checked_now = any(r.id in config.ROLES_TO_CHECK for r in after.roles)
    if had_checked and not has_checked_now:
        await log_other(f"🔄 {after.display_name} (`{after.id}`) lost all checked roles — checking in 60s")
        asyncio.create_task(check_and_assign_role(after))

    if (config.ROLE_CANCEL_A in before_roles) and (config.ROLE_CANCEL_A not in after_roles):
        await log_other(
            f"📉 {after.display_name} (`{after.id}`) lost member role — will mark Former in "
            f"{config.FORMER_MEMBER_DELAY_SECONDS}s if not regained."
        )
        asyncio.create_task(delayed_assign_former_member(after))

    if (config.ROLE_CANCEL_A not in before_roles) and (config.ROLE_CANCEL_A in after_roles):
        if has_former_member_role(after):
            role = after.guild.get_role(config.FORMER_MEMBER_ROLE)
            if role:
                with suppress(Exception):
                    await after.remove_roles(role, reason="Regained member role; remove former-member marker")
                    await log_other(f"🧹 Removed Former Member role from {_fmt_user(after)} (regained member).")


# -------------------------
# Role helpers used earlier
# -------------------------
async def check_and_assign_role(member: discord.Member):
    if member.bot or member.id in pending_checks:
        return
    pending_checks.add(member.id)
    try:
        await asyncio.sleep(60)
        has_any = any(role.id in config.ROLES_TO_CHECK for role in member.roles)
        if not has_any:
            role = member.guild.get_role(config.ROLE_TRIGGER)
            if role is None:
                await log_other(f"❌ Fallback role not found for {_fmt_user(member)}")
                return
            try:
                await member.add_roles(role, reason="No valid roles after 60s")
                await log_other(f"✅ Gave fallback role to **{member.display_name}** (`{member.id}`)")
                if not has_sequence_before(member.id):
                    enqueue_first_day(member.id)
                    await log_first(f"🧵 Enqueued **day_1** for {_fmt_user(member)} (fallback role assigned)")
            except Exception as e:
                await log_other(f"⚠️ Failed to assign role to **{member.display_name}** (`{member.id}`): `{e}`")
    finally:
        pending_checks.discard(member.id)


async def delayed_assign_former_member(member: discord.Member):
    if member.bot or member.id in pending_former_checks:
        return
    pending_former_checks.add(member.id)
    try:
        await asyncio.sleep(config.FORMER_MEMBER_DELAY_SECONDS)
        guild = bot.get_guild(config.GUILD_ID)
        if not guild:
            return
        refreshed = guild.get_member(member.id)
        if not refreshed:
            return
        if has_member_role(refreshed):
            await log_other(f"↩️ {_fmt_user(refreshed)} regained member role during delay — not marking former.")
            return
        if not has_former_member_role(refreshed):
            role = guild.get_role(config.FORMER_MEMBER_ROLE)
            if role:
                try:
                    await refreshed.add_roles(role, reason="Lost member role; mark as former member")
                    await log_other(f"🏷️ Marked **{refreshed.display_name}** as Former Member")
                except Exception as e:
                    await log_other(f"⚠️ Failed to add former-member role: `{e}`")
    finally:
        pending_former_checks.discard(member.id)


# -------------------------
# Admin and test commands
# -------------------------
@bot.command(name="start")
@commands.has_permissions(administrator=True)
async def start_sequence(ctx, member: discord.Member):
    if not has_trigger_role(member):
        await ctx.reply("❗ User does not have the trigger role; sequence only starts after that role is added.")
        return
    if has_sequence_before(member.id):
        await ctx.reply("User already had sequence before; not starting again.")
        return
    enqueue_first_day(member.id)
    await ctx.reply(f"Queued day_1 for {member.mention} now.")
    await log_first(f"🧵 (Admin) Enqueued **day_1** for {_fmt_user(member)}")


@bot.command(name="cancel")
@commands.has_permissions(administrator=True)
async def cancel_sequence(ctx, member: discord.Member):
    if str(member.id) not in queue_state:
        await ctx.reply("User not in active queue.")
        return
    mark_cancelled(member.id, "admin_cancel")
    await ctx.reply(f"Cancelled sequence for {member.mention}.")
    await log_other(f"🛑 (Admin) Cancelled sequence for {_fmt_user(member)}")


@bot.command(name="test")
@commands.has_permissions(administrator=True)
async def test_sequence(ctx, member: discord.Member):
    """
    Admin test: send the configured DAY_KEYS sequence to a particular member (quickly).
    """
    await ctx.reply(f"Starting admin test sequence for {member.mention}...")
    for day_key in config.DAY_KEYS:
        # skip if module missing
        mod = load_message_module(day_key)
        if mod is None:
            await log_other(f"🧪 Skipping test {day_key} — module not found.")
            continue
        join_url = config.UTM_LINKS.get(day_key)
        if not join_url:
            await log_other(f"🧪 Skipping test {day_key} — UTM missing.")
            continue
        try:
            embeds, view = normalize_message_output(mod, join_url)
            await send_embeds_with_view(member, embeds, view, join_url=join_url)
            if day_key == "day_1":
                await log_first(f"🧪 TEST sent **{day_key}** to {_fmt_user(member)}")
            else:
                await log_other(f"🧪 TEST sent **{day_key}** to {_fmt_user(member)}")
        except Exception as e:
            await log_other(f"🧪❌ TEST failed `{day_key}` for {_fmt_user(member)}: `{e}`")
        await asyncio.sleep(1)  # very short spacing for quick admin tests
    await ctx.send(f"✅ Admin test sequence complete for {member.mention}.")


@bot.command(name="testme", aliases=["testdm", "testdmme"])
async def testme_sequence(ctx):
    """
    Non-admin diagnostic test: sends the configured DAY_KEYS sequence in quick succession to the command caller.
    It first tries a plain-text DM to verify basic DM ability, then attempts embed sends and reports any failures in-channel.
    """
    caller = ctx.author
    await ctx.reply("📩 Starting diagnostic test: I'll try a plain DM, then each message. Check your DMs / Message Requests.")

    # plain DM check
    try:
        dm = await caller.create_dm()
        await dm.send("🔎 DM check: this is a plain-text test. If you see this, DMs are allowed.")
    except discord.Forbidden:
        await ctx.send("❌ Could not send a plain DM — your privacy settings likely block DMs from server members.")
        return
    except Exception as e:
        tb = traceback.format_exc()
        log.error(f"testme plain DM failed for {caller} ({caller.id}):\n{tb}")
        await ctx.send(f"⚠️ Unexpected error sending plain DM: `{e}` — check bot logs.")
        return

    for day_key in config.DAY_KEYS:
        mod = load_message_module(day_key)
        if mod is None:
            await ctx.send(f"ℹ️ Skipping `{day_key}`: message module not found.")
            continue
        join_url = config.UTM_LINKS.get(day_key)
        if not join_url:
            await ctx.send(f"ℹ️ Skipping `{day_key}`: UTM link missing.")
            continue

        # try a small plain note first
        try:
            await dm.send(f"TEST (plain) for `{day_key}` — if you see this, DM plain-text sending works.")
        except discord.Forbidden:
            await ctx.send(f"❌ Plain DM for `{day_key}` failed (discord.Forbidden). Privacy settings or blocked bot.")
            return
        except Exception as e:
            tb = traceback.format_exc()
            log.error(f"testme plain per-day DM failed for {caller} ({caller.id}) day {day_key}:\n{tb}")
            await ctx.send(f"⚠️ Plain DM for `{day_key}` error: `{e}` — check logs.")
            return

        await asyncio.sleep(0.5)

        # build and send embeds
        try:
            embeds, view = normalize_message_output(mod, join_url)
        except Exception as e:
            tb = traceback.format_exc()
            log.error(f"testme build_embed error for {caller} ({caller.id}) day {day_key}:\n{tb}")
            await ctx.send(f"⚠️ Failed building embeds for `{day_key}`: `{e}` — skipping embed send.")
            continue

        try:
            await send_embeds_with_view(dm, embeds, view, join_url=join_url)
            await ctx.send(f"✅ Sent embed(s) for `{day_key}` (check DM).")
        except discord.Forbidden:
            await ctx.send(f"❌ Embed send for `{day_key}` failed with discord.Forbidden — privacy/settings or blocked.")
            return
        except Exception as e:
            tb = traceback.format_exc()
            log.error(f"testme embed send error for {caller} ({caller.id}) day {day_key}:\n{tb}")
            await ctx.send(f"⚠️ Embed send for `{day_key}` failed: `{e}` — check bot logs.")
            continue

        await asyncio.sleep(1)

    await ctx.send("✅ Diagnostic test complete. Check your DMs and bot logs for details.")


@bot.command(name="dmcheck")
async def dmcheck(ctx):
    """Diagnostic DM check — reports exception details to channel & logs."""
    user = ctx.author
    try:
        dm = await user.create_dm()
        await dm.send("🔎 DM check: this is a plain-text test. If you see this, DMs are allowed.")
        await ctx.reply("✅ Plain DM sent — check your DMs (Message Requests if not in main list).")
        return
    except Exception as e:
        tb = traceback.format_exc()
        # log full traceback in runtime logs for us to inspect
        log.error(f"dmcheck: failed to send plain DM to {user} ({user.id}):\n{tb}")

        # Send a helpful in-channel reply with sanitized message
        await ctx.reply(f"❌ DM attempt failed: `{e}` — I logged the full traceback to the bot logs.")
        return


@bot.command(name="relocate")
@commands.has_permissions(administrator=True)
async def relocate_sequence(ctx, member: discord.Member, day: str):
    d = day.strip().lower()
    if d.isdigit():
        idx = int(d) - 1
        day_key = config.DAY_KEYS[idx] if 0 <= idx < len(config.DAY_KEYS) else None
    elif d in ("7a", "7b"):
        if f"day_{d}" in config.DAY_KEYS:
            day_key = f"day_{d}"
        else:
            day_key = None
    elif d == "7":
        if len(config.DAY_KEYS) >= 7:
            day_key = config.DAY_KEYS[6]
        else:
            day_key = None
    elif d.startswith("day_") and d in config.DAY_KEYS:
        day_key = d
    else:
        day_key = None

    if not day_key:
        await ctx.reply("Invalid day. Use 1–7, 7a, 7b, 7, or day_1..day_7b.")
        return

    queue_state[str(member.id)] = {
        "current_day": day_key,
        "next_send": (_now() + timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
    }
    save_json(config.QUEUE_FILE, queue_state)
    await ctx.reply(f"Relocated {member.mention} to **{day_key}**, will send in ~5s.")
    await log_other(f"➡️ Relocated {_fmt_user(member)} to **{day_key}**")


# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    if not config.TOKEN:
        raise RuntimeError("TOKEN env var is required")
    bot.run(config.TOKEN)
