import os
import asyncio
import threading
import logging
import random
from flask import Flask
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, API_ID, API_HASH, AFK_TIMEOUT, VALID_SHOTS, BALLS_PER_OVER
from database import init_db, get_db
from game import Match, MatchState, get_match_by_group, get_lobby_by_group, get_commentary
from animations import send_animation
from rules import SLEDGES, RULES_TEXT

# ==========================================
# LOGGING & DATABASE INIT
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
init_db()

# ==========================================
# IN-MEMORY STATE & HELPERS
# ==========================================
match_flow_state = {}
end_confirmations = {}

def get_mention(user):
    name = user.first_name or "Player"
    if user.username:
        return f"@{user.username}"
    return f"[{name}](tg://user?id={user.id})"

def get_display_name(user):
    return user.first_name or "Player"

def get_mention_by_id(client, chat_id, user_id):
    return f"[Player](tg://user?id={user.id})"

def cancel_timer(match_id):
    if match_id in match_flow_state and match_flow_state[match_id].get("timer_task"):
        match_flow_state[match_id]["timer_task"].cancel()
        match_flow_state[match_id]["timer_task"] = None

def set_timer(match_id, task):
    cancel_timer(match_id)
    if match_id not in match_flow_state:
        match_flow_state[match_id] = {}
    match_flow_state[match_id]["timer_task"] = task

def get_match_lang(match_id):
    return match_flow_state.get(match_id, {}).get("lang", "eng")

# ==========================================
# PYROGRAM CLIENT INITIALIZATION
# ==========================================
bot = Client(
    "hand_cricket_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==========================================
# MAIN MENU & NAVIGATION
# ==========================================
@bot.on_message(filters.command("start") & filters.private)
async def start_private(client, message):
    text = """🏏 **FRIENDS HAND CRICKET**

Play hand cricket with your friends in groups!

⚠️ **Important:** You must /start the bot here to receive **private bowling instructions** during matches.

Add me to a group and use /startcricket to begin!"""
    await message.reply(text)

@bot.on_message(filters.command("start") & filters.group)
async def start_group(client, message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Solo Mode", callback_data="menu_solo"),
         InlineKeyboardButton("👥 Team Mode", callback_data="menu_team")],
        [InlineKeyboardButton("📊 Profile", callback_data="menu_profile"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_lead")],
        [InlineKeyboardButton("📜 Rules", callback_data="menu_rules")]
    ])
    await message.reply("🏏 FRIENDS HAND CRICKET\n\nPlay hand cricket with your friends!", reply_markup=kb)

@bot.on_callback_query(filters.regex(r"^menu_"))
async def menu_handler(client, callback):
    data = callback.data.split("_")[1]
    if data == "solo":
        await callback.answer("Use /startcricket in the group to start a Solo match!", show_alert=True)
    elif data == "team":
        await callback.answer("Use /startcricket in the group to start a Team match!", show_alert=True)
    elif data == "profile":
        user = callback.from_user
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE telegram_id = ?", (user.id,)).fetchone()
        text = f"📊 **Profile: {get_mention(user)}**\n\nMatches: {u['matches'] if u else 0}\nWins: {u['wins'] if u else 0}\nRuns: {u['runs'] if u else 0}\nWickets: {u['wickets'] if u else 0}"
        await callback.message.edit(text)
    elif data == "lead":
        db = get_db()
        top = db.execute("SELECT * FROM users ORDER BY runs DESC LIMIT 5").fetchall()
        text = "🏆 **Leaderboard (Top Runs)**\n\n"
        for i, u in enumerate(top, 1):
            text += f"{i}. {get_display_name(u)} — {u['runs']} runs\n"
        await callback.message.edit(text if top else "No stats yet!")
    elif data == "rules":
        await callback.message.edit(RULES_TEXT)

# ==========================================
# MATCH CREATION & LOBBY
# ==========================================
@bot.on_message(filters.command("startcricket") & filters.group)
async def start_cricket(client, message):
    chat_id = message.chat.id
    if get_lobby_by_group(chat_id) or get_match_by_group(chat_id):
        await message.reply("⚠️ A match is already active or in the lobby in this group.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Solo Mode", callback_data="create_solo"),
         InlineKeyboardButton("👥 Team Mode", callback_data="create_team")]
    ])
    await message.reply("Select Game Mode:", reply_markup=kb)

@bot.on_callback_query(filters.regex(r"^create_"))
async def create_match(client, callback):
    if callback.message.chat.type not in [ChatType.SUPERGROUP, ChatType.GROUP]:
        await callback.answer("Matches can only be created in groups!", show_alert=True)
        return
    mode = "solo" if "solo" in callback.data else "team"
    chat_id = callback.message.chat.id
    user = callback.from_user
    
    m = Match()
    m.create(chat_id, mode, user.id)
    match_flow_state[m.match_id] = {"timer_task": None, "batter_waiting": False, "bowler_waiting": False, "auto_start_task": None, "lang": "eng"}
    
    if mode == "solo":
        text = f"🏏 **SOLO LOBBY**\n\nHost: {get_mention(user)}\n\nPlayers:\n1. {get_display_name(user)}\n\nPlayers can join using:\n`/joinsolo`\n\nHost can force start with:\n`/forcestart`"
        await callback.message.edit(text)
        async def auto_start():
            await asyncio.sleep(60)
            active_match = Match(m.match_id)
            db_match = active_match.get()
            if db_match and db_match['status'] == MatchState.LOBBY:
                players = active_match.get_players()
                if len(players) >= 2:
                    await client.send_message(chat_id, "⏳ 60 seconds passed. Auto-starting match!")
                    await begin_solo_match(client, chat_id, m.match_id)
        match_flow_state[m.match_id]["auto_start_task"] = asyncio.create_task(auto_start())
    else:
        text = f"🏟️ **TEAM MATCH LOBBY**\n\nHost: {get_mention(user)}\n\n🔵 TEAM A\nEmpty\n\n🔴 TEAM B\nEmpty\n\nPlayers can join using:\n`/join_team_a`\n`/join_team_b`\n\nHost starts with `/forcestart`"
        await callback.message.edit(text)

# ==========================================
# JOINING COMMANDS
# ==========================================
@bot.on_message(filters.command("joinsolo") & filters.group)
async def join_solo(client, message):
    lobby = get_lobby_by_group(message.chat.id)
    if not lobby or lobby['mode'] != 'solo': return await message.reply("❌ No active Solo lobby.")
    m = Match(lobby['match_id'])
    if m.add_player(message.from_user.id):
        await message.reply(f"✅ {get_display_name(message.from_user)} joined!")
        players = m.get_players()
        text = "🏏 **SOLO LOBBY**\n\nPlayers:\n" + "\n".join([f"{i+1}. {get_display_name(p)}" for i, p in enumerate(players)])
        await message.reply(text)
    else: await message.reply("⚠️ You already joined.")

@bot.on_message(filters.command("join_team_a") & filters.group)
async def join_ta(client, message):
    lobby = get_lobby_by_group(message.chat.id)
    if not lobby or lobby['mode'] != 'team': return await message.reply("❌ No active Team lobby.")
    m = Match(lobby['match_id'])
    if m.add_player(message.from_user.id, 'a'):
        await message.reply(f"✅ {get_display_name(message.from_user)} joined Team A!")
        await show_team_lobby(client, message.chat.id, m)

@bot.on_message(filters.command("join_team_b") & filters.group)
async def join_tb(client, message):
    lobby = get_lobby_by_group(message.chat.id)
    if not lobby or lobby['mode'] != 'team': return await message.reply("❌ No active Team lobby.")
    m = Match(lobby['match_id'])
    if m.add_player(message.from_user.id, 'b'):
        await message.reply(f"✅ {get_display_name(message.from_user)} joined Team B!")
        await show_team_lobby(client, message.chat.id, m)

async def show_team_lobby(client, chat_id, m):
    team_a = m.get_players('a')
    team_b = m.get_players('b')
    a_text = "\n".join([f"{i+1}. {get_display_name(p)}" for i, p in enumerate(team_a)]) or "Empty"
    b_text = "\n".join([f"{i+1}. {get_display_name(p)}" for i, p in enumerate(team_b)]) or "Empty"
    text = f"🏟️ **TEAM MATCH LOBBY**\n\n🔵 TEAM A\n{a_text}\n\n🔴 TEAM B\n{b_text}\n\nHost starts with `/forcestart`"
    await client.send_message(chat_id, text)

# ==========================================
# FORCE START & MATCH INIT
# ==========================================
@bot.on_message(filters.command("forcestart") & filters.group)
async def force_start(client, message):
    lobby = get_lobby_by_group(message.chat.id)
    if not lobby: return await message.reply("❌ No active lobby.")
    if lobby['host_id'] != message.from_user.id: return await message.reply("⚠️ Only host can force start.")
    m = Match(lobby['match_id'])
    players = m.get_players()
    if lobby['mode'] == 'solo':
        if len(players) < 2: return await message.reply("⚠️ Need at least 2 players.")
        if m.match_id in match_flow_state and match_flow_state[m.match_id].get("auto_start_task"):
            match_flow_state[m.match_id]["auto_start_task"].cancel()
        await begin_solo_match(client, message.chat.id, m.match_id)
    else:
        team_a = m.get_players('a')
        team_b = m.get_players('b')
        if len(team_a) < 1 or len(team_b) < 1: return await message.reply("⚠️ Both teams need at least 1 player.")
        await begin_team_match(client, message.chat.id, m.match_id)

# ==========================================
# SOLO MODE LOGIC
# ==========================================
async def begin_solo_match(client, chat_id, match_id):
    m = Match(match_id)
    m.update_state(MatchState.INNINGS)
    players = m.get_players()
    db = get_db()
    for p in players:
        db.execute("INSERT OR IGNORE INTO users (telegram_id, username, display_name, matches) VALUES (?, ?, ?, 1)", (p['telegram_id'], "", get_display_name(p)))
        db.commit()
    text = "🏏 **SOLO MATCH STARTED!**\n\n" + "\n".join([f"{i+1}. {get_display_name(p)}" for i, p in enumerate(players)]) + "\n\nEach player will bat. Others will bowl."
    await client.send_message(chat_id, text)
    await setup_next_solo_batter(client, chat_id, match_id, players, 0)

async def setup_next_solo_batter(client, chat_id, match_id, players, index):
    if index >= len(players):
        await end_solo_match(client, chat_id, match_id); return
    m = Match(match_id)
    batter = players[index]
    m.set_batter(batter['telegram_id'])
    m.update_state(MatchState.BATTER_WAITING)
    
    match_flow_state[match_id].update({
        "current_solo_index": index, "current_over": 1, "current_ball": 1,
        "batter_waiting": True, "bowler_waiting": False, "innings_runs": 0, "bowler_rotation_index": 0
    })
    over = match_flow_state[match_id]["current_over"]
    ball = match_flow_state[match_id]["current_ball"]
    text = f"🏏 **{get_mention_by_id(client, chat_id, batter['telegram_id'])} IS BATTING**\n\nOver: {over}\nBall: {ball}\n\nSend your shot (1–6)."
    msg = await client.send_message(chat_id, text)
    
    async def batter_timeout():
        await asyncio.sleep(AFK_TIMEOUT)
        if match_flow_state.get(match_id, {}).get("batter_waiting"):
            await client.send_message(chat_id, "⏰ BATTER TIMEOUT!\n\n🎯 OUT!")
            m.record_delivery(1, over, ball, batter['telegram_id'], 0, 0, 0, 0, 1)
            await send_animation(client, chat_id, "OUT", msg.id)
            await setup_next_solo_batter(client, chat_id, match_id, players, index + 1)
    set_timer(match_id, asyncio.create_task(batter_timeout()))

async def handle_solo_batter_input(client, chat_id, match_id, user_id, choice):
    m = Match(match_id)
    batter = m.get_current_batter()
    if not batter or batter['telegram_id'] != user_id or not match_flow_state.get(match_id, {}).get("batter_waiting"): return False
    cancel_timer(match_id)
    match_flow_state[match_id]["batter_waiting"] = False
    
    players = m.get_players()
    bowlers = [p for p in players if p['telegram_id'] != user_id]
    if not bowlers: return False
    rot_idx = match_flow_state[match_id].get("bowler_rotation_index", 0) % len(bowlers)
    bowler = bowlers[rot_idx]
    match_flow_state[match_id]["current_bowler_id"] = bowler['telegram_id']
    match_flow_state[match_id]["batter_choice"] = int(choice)
    
    m.set_bowler(bowler['telegram_id'])
    m.update_state(MatchState.BOWLER_WAITING)
    match_flow_state[match_id]["bowler_waiting"] = True
    
    over = match_flow_state[match_id]["current_over"]
    ball = match_flow_state[match_id]["current_ball"]
    try:
        await client.send_message(bowler['telegram_id'], f"🎯 **YOUR TURN TO BOWL**\n\n🏏 Batter: {get_mention_by_id(client, chat_id, user_id)}\n📊 Over: {over}\n🎯 Ball: {ball}\n\nSend your delivery (1–6).")
    except Exception:
        await client.send_message(chat_id, f"🎯 {get_mention_by_id(client, chat_id, bowler['telegram_id'])}, it's your turn to bowl!\n\nYou haven't started the bot in private yet.\nPlease open the bot and send /start first.\n\n⏳ You have {AFK_TIMEOUT} seconds.")
    
    async def bowler_timeout():
        await asyncio.sleep(AFK_TIMEOUT)
        if match_flow_state.get(match_id, {}).get("bowler_waiting"):
            match_flow_state[match_id]["bowler_waiting"] = False
            await client.send_message(chat_id, "⏰ BOWLER TIMEOUT!\n\n+6 runs awarded to the batting side.")
            match_flow_state[match_id]["innings_runs"] += 6
            m.record_delivery(1, over, ball, user_id, bowler['telegram_id'], int(choice), 0, 6, 0)
            await proceed_solo_next_ball(client, chat_id, match_id)
    set_timer(match_id, asyncio.create_task(bowler_timeout()))
    return True

async def handle_solo_bowler_input(client, match_id, user_id, choice):
    m = Match(match_id)
    bowler = m.get_current_bowler()
    if not bowler or bowler['telegram_id'] != user_id or not match_flow_state.get(match_id, {}).get("bowler_waiting"): return False
    over = match_flow_state[match_id]["current_over"]
    is_valid, reason = m.is_delivery_valid(user_id, int(choice), over, 1)
    if not is_valid:
        await client.send_message(user_id, f"⚠️ You cannot bowl {choice} right now.\n\nReason: {choice} {reason}\n\nPlease send another number.")
        return False
    cancel_timer(match_id)
    match_flow_state[match_id]["bowler_waiting"] = False
    batter = m.get_current_batter()
    b_choice = match_flow_state[match_id]["batter_choice"]
    bw_choice = int(choice)
    m.update_state(MatchState.RESOLVE_BALL)
    db_match = m.get()
    await resolve_solo_ball(client, db_match['chat_id'], match_id, batter, bowler, b_choice, bw_choice)
    return True

async def resolve_solo_ball(client, chat_id, match_id, batter, bowler, b_choice, bw_choice):
    m = Match(match_id)
    over = match_flow_state[match_id]["current_over"]
    ball = match_flow_state[match_id]["current_ball"]
    is_out = (b_choice == bw_choice)
    runs = 0 if is_out else b_choice
    m.record_delivery(1, over, ball, batter['telegram_id'], bowler['telegram_id'], b_choice, bw_choice, runs, 1 if is_out else 0)
    
    if not is_out:
        match_flow_state[match_id]["innings_runs"] += runs
        lang = get_match_lang(match_id)
        comm = get_commentary(lang, "six" if runs == 6 else "four" if runs == 4 else "single", batter['username'])
        text = f"🏏 **BALL RESULT**\n\n👤 {get_mention_by_id(client, chat_id, batter['telegram_id'])} → {b_choice}\n🎯 {get_mention_by_id(client, chat_id, bowler['telegram_id'])} → {bw_choice}\n\n{comm}\n**+{runs} RUNS**"
        msg = await client.send_message(chat_id, text)
        await send_animation(client, chat_id, runs, msg.id)
    else:
        is_duck = (m.db.execute("SELECT runs FROM match_players WHERE match_id=? AND telegram_id=?", (match_id, batter['telegram_id'])).fetchone()['runs'] == 0)
        text = f"🎯 **OUT!**\n\n👤 {get_mention_by_id(client, chat_id, batter['telegram_id'])} → {b_choice}\n🎯 {get_mention_by_id(client, chat_id, bowler['telegram_id'])} → {bw_choice}"
        msg = await client.send_message(chat_id, text)
        await send_animation(client, chat_id, "DUCK" if is_duck else "OUT", msg.id)
    await proceed_solo_next_ball(client, chat_id, match_id, is_out)

async def proceed_solo_next_ball(client, chat_id, match_id, is_out=False):
    m = Match(match_id)
    players = m.get_players()
    current_idx = match_flow_state[match_id]["current_solo_index"]
    if is_out:
        await setup_next_solo_batter(client, chat_id, match_id, players, current_idx + 1); return
    b_choice = match_flow_state[match_id]["batter_choice"]
    if b_choice in [1, 3, 5]:
        await client.send_message(chat_id, "🏃 Odd runs! Strike rotates to next player.")
        await setup_next_solo_batter(client, chat_id, match_id, players, current_idx + 1); return
    over = match_flow_state[match_id]["current_over"]
    ball = match_flow_state[match_id]["current_ball"]
    if ball >= BALLS_PER_OVER:
        await client.send_message(chat_id, "🛑 Over complete! Next player's turn.")
        await setup_next_solo_batter(client, chat_id, match_id, players, current_idx + 1); return

    match_flow_state[match_id]["current_ball"] += 1
    match_flow_state[match_id]["bowler_rotation_index"] += 1
    batter = m.get_current_batter()
    over = match_flow_state[match_id]["current_over"]
    ball = match_flow_state[match_id]["current_ball"]
    m.update_state(MatchState.BATTER_WAITING)
    match_flow_state[match_id]["batter_waiting"] = True
    text = f"🏏 Score: {match_flow_state[match_id]['innings_runs']}\nOver: {over}.{ball}\n\n{get_mention_by_id(client, chat_id, batter['telegram_id'])} is batting.\n\nSend your shot (1–6)."
    msg = await client.send_message(chat_id, text)
    
    async def batter_timeout():
        await asyncio.sleep(AFK_TIMEOUT)
        if match_flow_state.get(match_id, {}).get("batter_waiting"):
            await client.send_message(chat_id, "⏰ BATTER TIMEOUT!\n\n🎯 OUT!")
            m.record_delivery(1, over, ball, batter['telegram_id'], 0, 0, 0, 0, 1)
            await send_animation(client, chat_id, "OUT", msg.id)
            await setup_next_solo_batter(client, chat_id, match_id, players, current_idx + 1)
    set_timer(match_id, asyncio.create_task(batter_timeout()))

async def end_solo_match(client, chat_id, match_id):
    m = Match(match_id)
    m.update_state(MatchState.RESULT)
    players = m.get_players()
    sorted_players = sorted(players, key=lambda p: p['runs'], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 **SOLO MATCH ENDED!**\n\n"
    for i, p in enumerate(sorted_players):
        medal = medals[i] if i < 3 else "🏏"
        text += f"{medal} {get_display_name(p)} — {p['runs']} runs\n"
    await client.send_message(chat_id, text)

# ==========================================
# TEAM MODE LOGIC
# ==========================================
async def begin_team_match(client, chat_id, match_id):
    m = Match(match_id)
    m.update_state(MatchState.SETUP)
    cap_a = m.get_players('a')[0]
    cap_b = m.get_players('b')[0]
    m.db.execute("UPDATE matches SET toss_winner = ? WHERE match_id = ?", (cap_a['telegram_id'], match_id))
    m.db.commit()
    text = f"🏛️ **TEAMS FINALIZED**\n\n🔵 TEAM A (Captain: {get_mention_by_id(client, chat_id, cap_a['telegram_id'])})\n"
    for p in m.get_players('a'): text += f"  {p['join_order']}. {get_display_name(p)}\n"
    text += f"\n🔴 TEAM B (Captain: {get_mention_by_id(client, chat_id, cap_b['telegram_id'])})\n"
    for p in m.get_players('b'): text += f"  {p['join_order']}. {get_display_name(p)}\n"
    text += f"\n🪙 Toss won by {get_mention_by_id(client, chat_id, cap_a['telegram_id'])}!\n\nCaptain, choose:\n`/bat` or `/field`"
    await client.send_message(chat_id, text)

@bot.on_message(filters.command(["bat", "field"]) & filters.group)
async def toss_choice(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    db_m = m.get()
    if db_m['status'] != MatchState.SETUP: return
    cap_a = m.get_players('a')[0]
    if message.from_user.id != cap_a['telegram_id']: return await message.reply("⚠️ Only Team A captain can choose.")
    choice = message.command[0].lower()
    m.db.execute("UPDATE matches SET toss_choice = ? WHERE match_id = ?", (choice, active['match_id']))
    m.db.commit()
    if choice == "bat":
        await client.send_message(message.chat.id, "🔵 Team A chooses to BAT!\n🔴 Team B will bowl.")
        m.update_state(MatchState.INNINGS)
        await prompt_team_batting(client, message.chat.id, active['match_id'])
    else:
        await client.send_message(message.chat.id, "🔵 Team A chooses to FIELD!\n🔴 Team B will bat.")
        m.update_state(MatchState.INNINGS)
        m.db.execute("UPDATE matches SET current_innings = 2 WHERE match_id = ?", (active['match_id'],))
        m.db.commit()
        await prompt_team_batting(client, message.chat.id, active['match_id'])

async def prompt_team_batting(client, chat_id, match_id):
    await client.send_message(chat_id, "Captain/Host, send the batting player number:\n`/batting 1`")

@bot.on_message(filters.command("batting") & filters.group)
async def set_batter_cmd(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    db_m = m.get()
    if db_m['status'] not in [MatchState.INNINGS, MatchState.NEXT_BATTER]: return
    try: num = int(message.command[1])
    except (IndexError, ValueError): return await message.reply("⚠️ Usage: /batting <number>")
    batting_team = 'a' if db_m['current_innings'] == 1 else 'b'
    players = m.get_players(batting_team)
    if num < 1 or num > len(players): return await message.reply(f"⚠️ Invalid number. Choose 1-{len(players)}.")
    batter = players[num-1]
    if batter['is_out']: return await message.reply("⚠️ This player is already out!")
    m.set_batter(batter['telegram_id'])
    m.update_state(MatchState.BATTER_WAITING)
    
    if active['match_id'] not in match_flow_state or match_flow_state[active['match_id']].get("is_super_over") != True:
        match_flow_state[active['match_id']].update({
            "timer_task": None, "batter_waiting": True, "bowler_waiting": False,
            "current_over": 1, "current_ball": 1, "innings_runs": 0, "wickets": 0, "is_super_over": False
        })
        
    match_flow_state[active['match_id']]["batter_waiting"] = True
    text = f"🏏 **{get_mention_by_id(client, chat_id, batter['telegram_id'])} IS BATTING**\n\nOver: {match_flow_state[active['match_id']]['current_over']}\nBall: {match_flow_state[active['match_id']]['current_ball']}\n\nSend your shot (1–6)."
    msg = await client.send_message(chat_id, text)
    
    async def batter_timeout():
        await asyncio.sleep(AFK_TIMEOUT)
        if match_flow_state.get(active['match_id'], {}).get("batter_waiting"):
            await client.send_message(chat_id, "⏰ BATTER TIMEOUT!\n\n🎯 OUT!")
            m.record_delivery(db_m['current_innings'], 1, 1, batter['telegram_id'], 0, 0, 0, 0, 1)
            await send_animation(client, chat_id, "OUT", msg.id)
            match_flow_state[active['match_id']]["wickets"] += 1
            await proceed_team_next_ball(client, chat_id, active['match_id'], is_out=True)
    set_timer(active['match_id'], asyncio.create_task(batter_timeout()))

@bot.on_message(filters.command("bowling") & filters.group)
async def set_bowler_cmd(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    db_m = m.get()
    if db_m['status'] != MatchState.BOWLER_WAITING: return await message.reply("⚠️ Wait for batter to play first.")
    try: num = int(message.command[1])
    except (IndexError, ValueError): return await message.reply("⚠️ Usage: /bowling <number>")
    bowling_team = 'b' if db_m['current_innings'] == 1 else 'a'
    players = m.get_players(bowling_team)
    if num < 1 or num > len(players): return await message.reply(f"⚠️ Invalid number. Choose 1-{len(players)}.")
    bowler = players[num-1]
    m.set_bowler(bowler['telegram_id'])
    match_id = active['match_id']
    chat_id = message.chat.id
    over = match_flow_state[match_id]["current_over"]
    ball = match_flow_state[match_id]["current_ball"]
    
    try:
        await client.send_message(bowler['telegram_id'], f"🎯 **YOUR TURN TO BOWL**\n\n🏏 Batter: {get_mention_by_id(client, chat_id, m.get_current_batter()['telegram_id'])}\n📊 Over: {over}\n🎯 Ball: {ball}\n\nSend your delivery (1–6).")
    except Exception:
        await client.send_message(chat_id, f"🎯 {get_mention_by_id(client, chat_id, bowler['telegram_id'])}, it's your turn to bowl!\n\nYou haven't started the bot in private yet.\nPlease open the bot and send /start first.\n\n⏳ You have {AFK_TIMEOUT} seconds.")
    
    match_flow_state[match_id]["bowler_waiting"] = True
    async def bowler_timeout():
        await asyncio.sleep(AFK_TIMEOUT)
        if match_flow_state.get(match_id, {}).get("bowler_waiting"):
            match_flow_state[match_id]["bowler_waiting"] = False
            await client.send_message(chat_id, "⏰ BOWLER TIMEOUT!\n\n+6 runs awarded.")
            match_flow_state[match_id]["innings_runs"] += 6
            await proceed_team_next_ball(client, chat_id, match_id)
    set_timer(match_id, asyncio.create_task(bowler_timeout()))

async def handle_team_batter_input(client, chat_id, match_id, user_id, choice):
    m = Match(match_id)
    batter = m.get_current_batter()
    if not batter or batter['telegram_id'] != user_id or not match_flow_state.get(match_id, {}).get("batter_waiting"): return False
    cancel_timer(match_id)
    match_flow_state[match_id]["batter_waiting"] = False
    match_flow_state[match_id]["batter_choice"] = int(choice)
    m.update_state(MatchState.BOWLER_WAITING)
    await client.send_message(chat_id, "Captain/Host, select the bowler:\n`/bowling 1`")
    return True

async def handle_team_bowler_input(client, match_id, user_id, choice):
    m = Match(match_id)
    bowler = m.get_current_bowler()
    if not bowler or bowler['telegram_id'] != user_id or not match_flow_state.get(match_id, {}).get("bowler_waiting"): return False
    db_m = m.get()
    over = match_flow_state[match_id]["current_over"]
    is_valid, reason = m.is_delivery_valid(user_id, int(choice), over, db_m['current_innings'])
    if not is_valid:
        await client.send_message(user_id, f"⚠️ You cannot bowl {choice} right now.\n\nReason: {choice} {reason}\n\nPlease send another number.")
        return False
    cancel_timer(match_id)
    match_flow_state[match_id]["bowler_waiting"] = False
    batter = m.get_current_batter()
    b_choice = match_flow_state[match_id]["batter_choice"]
    bw_choice = int(choice)
    await resolve_team_ball(client, db_m['chat_id'], match_id, batter, bowler, b_choice, bw_choice)
    return True

async def resolve_team_ball(client, chat_id, match_id, batter, bowler, b_choice, bw_choice):
    m = Match(match_id)
    db_m = m.get()
    over = match_flow_state[match_id]["current_over"]
    ball = match_flow_state[match_id]["current_ball"]
    innings = db_m['current_innings']
    is_out = (b_choice == bw_choice)
    runs = 0 if is_out else b_choice
    m.record_delivery(innings, over, ball, batter['telegram_id'], bowler['telegram_id'], b_choice, bw_choice, runs, 1 if is_out else 0)
    
    if not is_out:
        match_flow_state[match_id]["innings_runs"] += runs
        lang = get_match_lang(match_id)
        comm = get_commentary(lang, "six" if runs == 6 else "four" if runs == 4 else "single", batter['username'])
        text = f"🏏 **BALL RESULT**\n\n👤 {get_mention_by_id(client, chat_id, batter['telegram_id'])} → {b_choice}\n🎯 {get_mention_by_id(client, chat_id, bowler['telegram_id'])} → {bw_choice}\n\n{comm}\n**+{runs} RUNS**"
        msg = await client.send_message(chat_id, text)
        await send_animation(client, chat_id, runs, msg.id)
    else:
        is_duck = (m.db.execute("SELECT runs FROM match_players WHERE match_id=? AND telegram_id=?", (match_id, batter['telegram_id'])).fetchone()['runs'] == 0)
        text = f"🎯 **OUT!**\n\n👤 {get_mention_by_id(client, chat_id, batter['telegram_id'])} → {b_choice}\n🎯 {get_mention_by_id(client, chat_id, bowler['telegram_id'])} → {bw_choice}"
        msg = await client.send_message(chat_id, text)
        await send_animation(client, chat_id, "DUCK" if is_duck else "OUT", msg.id)
        match_flow_state[match_id]["wickets"] += 1
    await proceed_team_next_ball(client, chat_id, match_id, is_out)

async def proceed_team_next_ball(client, chat_id, match_id, is_out=False):
    m = Match(match_id)
    db_m = m.get()
    batting_team = 'a' if db_m['current_innings'] == 1 else 'b'
    players = m.get_players(batting_team)
    wickets = match_flow_state[match_id]["wickets"]
    
    if is_out and wickets >= len(players):
        await end_team_innings(client, chat_id, match_id); return
    if is_out:
        m.update_state(MatchState.NEXT_BATTER)
        await prompt_team_batting(client, chat_id, match_id); return

    over = match_flow_state[match_id]["current_over"]
    ball = match_flow_state[match_id]["current_ball"]
    if ball >= BALLS_PER_OVER:
        if over >= db_m['overs']:
            await end_team_innings(client, chat_id, match_id); return
        match_flow_state[match_id]["current_over"] += 1
        match_flow_state[match_id]["current_ball"] = 1
        await client.send_message(chat_id, f"🛑 Over {over} complete!")
        m.update_state(MatchState.NEXT_BATTER)
        await prompt_team_batting(client, chat_id, match_id); return

    match_flow_state[match_id]["current_ball"] += 1
    b_choice = match_flow_state[match_id]["batter_choice"]
    if b_choice in [1, 3, 5]:
        await client.send_message(chat_id, "🏃 Odd runs! Strike rotates.")
        m.update_state(MatchState.NEXT_BATTER)
        await prompt_team_batting(client, chat_id, match_id); return

    batter = m.get_current_batter()
    m.update_state(MatchState.BATTER_WAITING)
    match_flow_state[match_id]["batter_waiting"] = True
    target_str = f"\nTarget: {db_m['target']}" if db_m['current_innings'] == 2 else ""
    text = f"🏏 Score: {match_flow_state[match_id]['innings_runs']}/{wickets}{target_str}\nOver: {over}.{ball}\n\n{get_mention_by_id(client, chat_id, batter['telegram_id'])} is batting.\n\nSend your shot (1–6)."
    msg = await client.send_message(chat_id, text)
    
    async def batter_timeout():
        await asyncio.sleep(AFK_TIMEOUT)
        if match_flow_state.get(match_id, {}).get("batter_waiting"):
            await client.send_message(chat_id, "⏰ BATTER TIMEOUT!\n\n🎯 OUT!")
            m.record_delivery(db_m['current_innings'], over, ball, batter['telegram_id'], 0, 0, 0, 0, 1)
            await send_animation(client, chat_id, "OUT", msg.id)
            match_flow_state[match_id]["wickets"] += 1
            await proceed_team_next_ball(client, chat_id, match_id, is_out=True)
    set_timer(match_id, asyncio.create_task(batter_timeout()))

async def end_team_innings(client, chat_id, match_id):
    m = Match(match_id)
    db_m = m.get()
    batting_team = 'a' if db_m['current_innings'] == 1 else 'b'
    total, wickets = m.get_team_total(batting_team)
    m.db.execute("UPDATE matches SET target = ? WHERE match_id = ?", (total + 1, match_id))
    m.db.commit()
    
    if db_m['current_innings'] == 1:
        m.db.execute("UPDATE matches SET current_innings = 2 WHERE match_id = ?", (match_id,))
        m.db.commit()
        team_name = db_m['team_a_name'] if batting_team == 'a' else db_m['team_b_name']
        await client.send_message(chat_id, f"🛑 **INNINGS END**\n\n{team_name} scored {total}/{wickets}.\n\nTarget for next team: {total + 1}")
        match_flow_state[match_id].update({"innings_runs": 0, "wickets": 0, "current_over": 1, "current_ball": 1})
        m.update_state(MatchState.INNINGS)
        await prompt_team_batting(client, chat_id, match_id)
    else:
        bowling_team = 'a' if batting_team == 'b' else 'b'
        bowl_total, _ = m.get_team_total(bowling_team)
        m.update_state(MatchState.RESULT)
        if total > bowl_total:
            winner_name = db_m['team_a_name'] if batting_team == 'a' else db_m['team_b_name']
            await client.send_message(chat_id, f"🏆 **{winner_name} WINS!**\n\nFinal Score: {total}/{wickets}")
        elif total < bowl_total:
            winner_name = db_m['team_a_name'] if bowling_team == 'a' else db_m['team_b_name']
            await client.send_message(chat_id, f"🏆 **{winner_name} WINS!**\n\nFinal Score: {total}/{wickets}")
        else:
            await client.send_message(chat_id, "🏆 **MATCH TIED!**\n\n🔥 1-OVER SUPER OVER\nHost, type `/superover` to start!")

# ==========================================
# GLOBAL MESSAGE HANDLER
# ==========================================
@bot.on_message(filters.text & ~filters.command(["start", "startcricket", "joinsolo", "forcestart", "join_team_a", "join_team_b", "bat", "field", "batting", "bowling", "score", "scoreboard", "teams", "call", "shift", "rebat", "endcricket", "changecom", "sledge", "superover"]))
async def handle_game_input(client, message):
    text = message.text.strip()
    if text not in VALID_SHOTS: return
    choice = int(text)
    
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        active = get_match_by_group(message.chat.id)
        if not active: return
        m = Match(active['match_id'])
        db_m = m.get()
        if db_m['mode'] == 'solo' and db_m['status'] == MatchState.BATTER_WAITING:
            await handle_solo_batter_input(client, message.chat.id, active['match_id'], message.from_user.id, choice)
        elif db_m['mode'] == 'team' and db_m['status'] == MatchState.BATTER_WAITING:
            await handle_team_batter_input(client, message.chat.id, active['match_id'], message.from_user.id, choice)
    elif message.chat.type == ChatType.PRIVATE:
        db = get_db()
        active_bowler = db.execute("""SELECT mp.match_id FROM match_players mp JOIN matches m ON mp.match_id = m.match_id WHERE mp.telegram_id = ? AND mp.is_bowling = 1 AND m.status = 'BOWLER_WAITING'""", (message.from_user.id,)).fetchone()
        if not active_bowler:
            await message.reply("⚠️ You are not currently bowling in an active match."); return
        m = Match(active_bowler['match_id'])
        db_m = m.get()
        if db_m['mode'] == 'solo':
            await handle_solo_bowler_input(client, active_bowler['match_id'], message.from_user.id, choice)
        elif db_m['mode'] == 'team':
            await handle_team_bowler_input(client, active_bowler['match_id'], message.from_user.id, choice)

# ==========================================
# EXTRA COMMANDS
# ==========================================
@bot.on_message(filters.command("score") & filters.group)
async def score_cmd(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    db_m = m.get()
    if db_m['mode'] == 'team':
        t1, w1 = m.get_team_total('a')
        t2, w2 = m.get_team_total('b')
        over = match_flow_state.get(active['match_id'], {}).get("current_over", 1)
        ball = match_flow_state.get(active['match_id'], {}).get("current_ball", 1)
        target = db_m['target'] if db_m['current_innings'] == 2 else t1 + 1
        target_str = f"\nTarget: {target}" if db_m['current_innings'] == 2 else ""
        text = f"🏏 **LIVE SCORE**\n\n🔵 {db_m['team_a_name']}\n{t1}/{w1}\n\n🔴 {db_m['team_b_name']}\n{t2}/{w2}\n\nOver: {over}.{ball}{target_str}"
    else:
        players = m.get_players()
        sorted_players = sorted(players, key=lambda p: p['runs'], reverse=True)
        medals = ["🥇", "🥈", "🥉"]
        text = "🏏 **SOLO LIVE SCORE**\n\n"
        for i, p in enumerate(sorted_players):
            medal = medals[i] if i < 3 else "🏏"
            text += f"{medal} {get_display_name(p)} — {p['runs']}\n"
    await message.reply(text)

@bot.on_message(filters.command("scoreboard") & filters.group)
async def scoreboard_cmd(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    db_m = m.get()
    text = "🏆 **SCORECARD**\n\n"
    for team in ['a', 'b']:
        if db_m['mode'] == 'solo' and team == 'b': continue
        players = m.get_players(team)
        total, wickets = m.get_team_total(team)
        team_name = db_m['team_a_name'] if team == 'a' else db_m['team_b_name'] if db_m['mode'] == 'team' else "SOLO"
        text += f"{'🔵' if team=='a' else '🔴'} {team_name} — {total}/{wickets}\n"
        for p in players:
            out_str = " ❌" if p['is_out'] else ""
            text += f"  {get_display_name(p)} {p['runs']}({p['balls']}){out_str}\n"
        text += "\n"
    await message.reply(text)

@bot.on_message(filters.command("teams") & filters.group)
async def teams_cmd(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    text = "🏟️ **TEAMS**\n\n"
    for team in ['a', 'b']:
        players = m.get_players(team)
        team_name = "SOLO" if active['mode'] == 'solo' else (m.get()['team_a_name'] if team == 'a' else m.get()['team_b_name'])
        text += f"{'🔵' if team=='a' else '🔴'} {team_name}\n"
        for p in players:
            cap = " (C)" if p['join_order'] == 1 and active['mode'] == 'team' else ""
            text += f"  {p['join_order']}. {get_display_name(p)}{cap}\n"
        text += "\n"
    await message.reply(text)

@bot.on_message(filters.command("sledge") & filters.group)
async def sledge_cmd(client, message):
    await message.reply(random.choice(SLEDGES))

@bot.on_message(filters.command("call") & filters.group)
async def call_cmd(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    players = m.get_players()
    failed = []
    for p in players:
        try: await client.send_message(p['telegram_id'], "🏏 Match is active in your group! Join now.")
        except Exception: failed.append(get_display_name(p))
    text = "📣 **Match Call Sent!**\n\n"
    if failed: text += f"⚠️ Could not DM (haven't started bot): {', '.join(failed)}"
    else: text += "All players notified in DM!"
    await message.reply(text)

@bot.on_message(filters.command("changecom") & filters.group)
async def changecom_cmd(client, message):
    try:
        lang = message.command[1].lower()
        if lang in ["eng", "hin"]:
            active = get_match_by_group(message.chat.id)
            if active:
                match_flow_state[active['match_id']]["lang"] = lang
                await message.reply(f"✅ Commentary changed to {'English' if lang == 'eng' else 'Hindi'}!")
        else: await message.reply("⚠️ Usage: /changecom eng OR /changecom hin")
    except IndexError: await message.reply("⚠️ Usage: /changecom eng OR /changecom hin")

@bot.on_message(filters.command("shift") & filters.group)
async def shift_cmd(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    if message.from_user.id != m.get()['host_id']: return await message.reply("⚠️ Only host can shift players.")
    try:
        uid = int(message.command[1])
        new_team = message.command[2].lower()
    except (IndexError, ValueError): return await message.reply("⚠️ Usage: /shift <user_id> <a/b>")
    if new_team not in ['a', 'b']: return await message.reply("⚠️ Team must be 'a' or 'b'.")
    batter = m.get_current_batter()
    bowler = m.get_current_bowler()
    if batter and batter['telegram_id'] == uid: return await message.reply("❌ Cannot shift current batter!")
    if bowler and bowler['telegram_id'] == uid: return await message.reply("❌ Cannot shift current bowler!")
    m.shift_player(uid, new_team)
    await message.reply(f"✅ Player shifted to Team {'A' if new_team == 'a' else 'B'}.")

@bot.on_message(filters.command("rebat") & filters.group)
async def rebat_cmd(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    if message.from_user.id != m.get()['host_id']: return await message.reply("⚠️ Only host can use rebat.")
    try: uid = int(message.command[1])
    except (IndexError, ValueError): return await message.reply("⚠️ Usage: /rebat <user_id>")
    m.unout_player(uid)
    await message.reply("✅ Player restored. Use /batting <num>.")

@bot.on_message(filters.command("endcricket") & filters.group)
async def endcricket_cmd(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    if message.from_user.id != m.get()['host_id']: return await message.reply("⚠️ Only host can end the match.")
    chat_id = message.chat.id
    if chat_id not in end_confirmations:
        end_confirmations[chat_id] = message.from_user.id
        await message.reply("⚠️ Are you sure? Type /endcricket again to confirm.")
    else:
        cancel_timer(active['match_id'])
        m.update_state(MatchState.RESULT)
        await message.reply("🛑 Match forcefully ended by host.")
        del end_confirmations[chat_id]

@bot.on_message(filters.command("superover") & filters.group)
async def start_super_over(client, message):
    active = get_match_by_group(message.chat.id)
    if not active: return
    m = Match(active['match_id'])
    db_m = m.get()
    if db_m['status'] != MatchState.RESULT: return await message.reply("❌ Can only start Super Over if match is tied.")
    t1, w1 = m.get_team_total('a')
    t2, w2 = m.get_team_total('b')
    if t1 != t2: return await message.reply("❌ Match is not tied.")
    
    m.db.execute("UPDATE matches SET status = 'INNINGS', overs = 1, current_innings = 1, target = 0 WHERE match_id = ?", (active['match_id'],))
    m.db.execute("UPDATE match_players SET runs = 0, balls = 0, wickets = 0, is_out = 0, is_batting = 0, is_bowling = 0 WHERE match_id = ?", (active['match_id'],))
    m.db.commit()
    
    match_flow_state[active['match_id']].update({
        "timer_task": None, "batter_waiting": False, "bowler_waiting": False,
        "current_over": 1, "current_ball": 1, "innings_runs": 0, "wickets": 0, "is_super_over": True
    })
    await client.send_message(message.chat.id, "🔥 **1-OVER SUPER OVER STARTED!**\n\nTeam A bats first. Captain, send batter:\n`/batting 1`")
    await prompt_team_batting(client, message.chat.id, active['match_id'])

# ==========================================
# FLASK SERVER (Directly inside bot.py)
# ==========================================
from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is online!", 200

@app.route('/health')
def health():
    return "Healthy", 200

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Started Flask health server on thread.")
    logger.info("Starting Telegram Bot...")
    bot.run()
