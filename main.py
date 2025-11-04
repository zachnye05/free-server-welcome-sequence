# main.py
import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
import importlib
import logging
from typing import Dict, Optional
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

bot = commands.Bot(command_prefix=".", intents=intents)

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
    if current_day == "day_7b":
        mark_finished(user_id)
        return

    idx = config.DAY_KEYS.index(current_day)
    next_day = config.DAY_KEYS[idx + 1]
    delay = timedelta(minutes=config.DAY7B_DELAY_MIN) if next_day == "day_7b" else timedelta(hours=config.DAY_GAP_HOURS)
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

async def send_day(member: discord.Member, day_key: str):
    global last_send_at

    if last_send_at:
        delta = (_now() - last_send_at).total_seconds()
        if delta < config.SEND_SPACING_SECONDS:
            await asyncio.sleep(config.SEND_SPACING_SECONDS - delta)

    if has_cancel_role(member):
        mark_cancelled(member.id, "cancel_role_present_pre_send")
        await log_other(f"🛑 Cancelled pre-send for {_fmt_user(member)} — cancel role present.")
        return

    try:
        mod = importlib.import_module(f"messages.{day_key}")
    except Exception as e:
        mark_cancelled(member.id, "missing_message_module")
        await log_other(f"❌ Import error `{day_key}` for {_fmt_user(member)}: `{e}`. Sequence cancelled.")
        return

    join_url = config.UTM_LINKS.get(day_key)
    if not join_url:
        mark_cancelled(member.id, "missing_utm")
        await log_other(f"❌ Missing UTM for `{day_key}` on {_fmt_user(member)}. Sequence cancelled.")
        return

    try:
        embeds, view = mod.build_embed(join_url=join_url)
    except Exception as e:
        mark_cancelled(member.id, "embed_build_error")
        await log_other(f"❌ build_embed error `{day_key}` for {_fmt_user(member)}: `{e}`. Sequence cancelled.")
        return

    try:
        await member.send(embeds=embeds, view=view)
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

                await send_day(member, day_key)

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

@bot.event
async def on_ready():
    global queue_state, registry
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    _ensure_storage()
    queue_state = load_json(config.QUEUE_FILE)
    registry = load_json(config.REGISTRY_FILE)

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

# admin commands are identical to your original but pointing at our helpers

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
    await ctx.reply(f"Starting test sequence for {member.mention}...")
    for day_key in config.DAY_KEYS:
        try:
            mod = importlib.import_module(f"messages.{day_key}")
            join_url = config.UTM_LINKS[day_key]
            embeds, view = mod.build_embed(join_url=join_url)
            await member.send(embeds=embeds, view=view)
            if day_key == "day_1":
                await log_first(f"🧪 TEST sent **{day_key}** to {_fmt_user(member)}")
            else:
                await log_other(f"🧪 TEST sent **{day_key}** to {_fmt_user(member)}")
        except Exception as e:
            await log_other(f"🧪❌ TEST failed `{day_key}` for {_fmt_user(member)}: `{e}`")
        await asyncio.sleep(10)
    await ctx.send(f"✅ Test sequence complete for {member.mention}.")

@bot.command(name="relocate")
@commands.has_permissions(administrator=True)
async def relocate_sequence(ctx, member: discord.Member, day: str):
    d = day.strip().lower()
    if d.isdigit():
        idx = int(d) - 1
        day_key = config.DAY_KEYS[idx] if 0 <= idx < len(config.DAY_KEYS) else None
    elif d in {"7a", "7b"}:
        day_key = f"day_{d}"
    elif d.startswith("day_") and d in config.DAY_KEYS:
        day_key = d
    else:
        day_key = None

    if not day_key:
        await ctx.reply("Invalid day. Use 1–6, 7a, 7b, or day_1..day_7b.")
        return

    queue_state[str(member.id)] = {
        "current_day": day_key,
        "next_send": (_now() + timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
    }
    save_json(config.QUEUE_FILE, queue_state)
    await ctx.reply(f"Relocated {member.mention} to **{day_key}**, will send in ~5s.")
    await log_other(f"➡️ Relocated {_fmt_user(member)} to **{day_key}**")

if __name__ == "__main__":
    if not config.TOKEN:
        raise RuntimeError("TOKEN env var is required")
    bot.run(config.TOKEN)
