import asyncio
import random
import threading
from flask import Flask
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import (
    UserNotParticipant,
    ChatWriteForbidden,
    PeerIdInvalid,
    UserIsBlocked,
    InputUserDeactivated,
)

from config import BOT_TOKEN, API_ID, API_HASH, PORT, AFK_TIMEOUT, BALLS_PER_OVER
from database import get_db, init_db
from game import Match, MatchState
from rules import (
    RULES_TEXT,
    get_commentary,
    get_out_commentary,
    get_duck_message,
    get_sledge,
    get_innings_break,
    get_match_end,
    get_match_start,
)
from animations import send_image_with_caption

# ─── Flask App ───
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "🏏 Hand Cricket Bot is alive!", 200


@flask_app.route("/health")
def health():
    return "OK", 200


# ─── Pyrogram Client ───
bot = Client(
    "handcricket_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ─── Active Timers (ONLY for asyncio timeout tasks) ───
active_timers = {}

# ─── Bot Username (cached at startup) ───
BOT_USERNAME = ""


# ═══════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════

def safe_name(obj):
    """Get display name safely from Pyrogram User or sqlite3.Row."""
    if obj is None:
        return "Unknown"
    # sqlite3.Row
    if hasattr(obj, "keys") and callable(obj.keys):
        try:
            return obj["display_name"] or "Player"
        except (IndexError, KeyError):
            return "Player"
    # Pyrogram User object
    if hasattr(obj, "first_name"):
        fname = obj.first_name or ""
        lname = obj.last_name or ""
        return f"{fname} {lname}".strip() or "Player"
    return "Unknown"


def safe_username(obj):
    """Get username safely."""
    if obj is None:
        return None
    if hasattr(obj, "keys") and callable(obj.keys):
        try:
            return obj["username"]
        except (IndexError, KeyError):
            return None
    if hasattr(obj, "username"):
        return obj.username
    return None


def safe_user_id(obj):
    """Get user_id safely."""
    if obj is None:
        return 0
    if hasattr(obj, "keys") and callable(obj.keys):
        try:
            return obj["user_id"]
        except (IndexError, KeyError):
            return 0
    if hasattr(obj, "id"):
        return obj.id
    return 0


def mention(user_id, name):
    """Create a mention link."""
    return f"[{name}](tg://user?id={user_id})"


async def safe_send(client, chat_id, text, **kwargs):
    """Send message safely, ignoring errors."""
    try:
        return await client.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN, **kwargs)
    except Exception:
        try:
            return await client.send_message(chat_id, text, **kwargs)
        except Exception:
            return None


async def safe_send_dm(client, user_id, text):
    """Send a DM safely."""
    try:
        return await client.send_message(user_id, text, parse_mode=ParseMode.MARKDOWN)
    except (PeerIdInvalid, UserIsBlocked, InputUserDeactivated):
        return None
    except Exception:
        return None


def cancel_timer(key):
    """Cancel an active timer if it exists."""
    task = active_timers.pop(key, None)
    if task and not task.done():
        task.cancel()


def get_overs_text(overs, balls):
    """Format overs as string."""
    return f"{overs}.{balls}"


# ═══════════════════════════════════════════════
# SCOREBOARD HELPERS
# ═══════════════════════════════════════════════

def build_solo_scoreboard(match):
    """Build solo mode scoreboard text."""
    match_id = match["match_id"]
    players = Match.get_players(match_id)
    scores = Match.get_solo_scores(match)
    lines = ["🏏 **SOLO SCOREBOARD** 🏏\n"]
    for p in players:
        uid = str(p["user_id"])
        user = Match.get_user(p["user_id"])
        name = safe_name(user) if user else "Player"
        data = scores.get(uid, {})
        runs = data.get("runs", 0)
        balls = data.get("balls", 0)
        is_out = data.get("is_out", False)
        status = "OUT" if is_out else ("batting" if data.get("batting", False) else "yet to bat")
        lines.append(f"  {name}: **{runs}** ({balls}b) - {status}")
    lines.append(f"\n📊 Current Over: {match['current_over']}.{match['current_ball']}")
    return "\n".join(lines)


def build_team_scoreboard(match):
    """Build team mode scoreboard text."""
    match_id = match["match_id"]
    lines = ["🏏 **TEAM SCOREBOARD** 🏏\n"]

    batting = match["batting_team"]
    bowling = match["bowling_team"]
    innings = match["innings"]

    if innings >= 1:
        lines.append(f"**Innings 1** ({match['innings1_overs']} ov):")
        lines.append(f"  Score: **{match['innings1_runs']}/{match['innings1_wickets']}**")

    if innings >= 2:
        lines.append(f"\n**Innings 2** ({match['innings2_overs']} ov):")
        lines.append(f"  Score: **{match['innings2_runs']}/{match['innings2_wickets']}**")
        target = match["target"]
        if target > 0:
            curr_runs = match["innings2_runs"]
            needed = target - curr_runs
            lines.append(f"  🎯 Need **{needed}** more runs")

    if innings < 2 or match["state"] != MatchState.MATCH_OVER:
        curr_runs = match["innings1_runs"] if innings == 1 else match["innings2_runs"]
        curr_wkts = match["innings1_wickets"] if innings == 1 else match["innings2_wickets"]
        lines.append(f"\n📊 Current: **{curr_runs}/{curr_wkts}** ({match['current_over']}.{match['current_ball']} ov)")

    # Batting card
    bat_players = Match.get_players(match_id, team=batting)
    if bat_players:
        lines.append(f"\n🏏 **Batting ({batting})**:")
        for bp in bat_players:
            user = Match.get_user(bp["user_id"])
            name = safe_name(user) if user else "Player"
            status = "out" if bp["is_out"] else "not out"
            if bp["user_id"] == match["current_batter_id"]:
                status = "batting *"
            lines.append(f"  {name}: {bp['batting_runs']}({bp['batting_balls']}) {status}")

    # Bowling card
    bowl_players = Match.get_players(match_id, team=bowling)
    if bowl_players:
        lines.append(f"\n🎳 **Bowling ({bowling})**:")
        for bp in bowl_players:
            user = Match.get_user(bp["user_id"])
            name = safe_name(user) if user else "Player"
            if bp["bowling_balls"] > 0:
                overs_str = f"{bp['bowling_balls'] // 6}.{bp['bowling_balls'] % 6}"
                lines.append(f"  {name}: {overs_str} ov, {bp['bowling_runs_given']}/{bp['bowling_wickets']}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════
# AFK TIMEOUT
# ═══════════════════════════════════════════════

async def start_afk_timer(client, match_id, target_type, target_user_id, chat_id):
    """Start an AFK timer. target_type is 'batter' or 'bowler'."""
    key = f"{match_id}_{target_type}"
    cancel_timer(key)

    async def _timeout():
        await asyncio.sleep(AFK_TIMEOUT)
        match = Match.get_match_by_id(match_id)
        if not match or match["state"] == MatchState.MATCH_OVER:
            return

        user = Match.get_user(target_user_id)
        name = safe_name(user) if user else "Player"

        if target_type == "bowler":
            if match["state"] != MatchState.BOWLER_WAITING:
                return
            if match["current_bowler_id"] != target_user_id:
                return
            # Bowler AFK -> +6 runs penalty
            await safe_send(client, chat_id,
                f"⏱ **AFK TIMEOUT!** {mention(target_user_id, name)} (bowler) didn't respond!\n"
                f"🏏 **+6 RUNS** penalty awarded to the batter!")
            # Process as if batter scored 6
            await process_ball_result(client, match_id, chat_id, match["temp_batter_choice"], 0, is_afk_bowler=True)

        elif target_type == "batter":
            if match["state"] != MatchState.BATTER_WAITING:
                return
            if match["current_batter_id"] != target_user_id:
                return
            # Batter AFK -> OUT
            await safe_send(client, chat_id,
                f"⏱ **AFK TIMEOUT!** {mention(target_user_id, name)} (batter) didn't respond!\n"
                f"🔴 **OUT!** Timed out! 💤")
            await process_ball_result(client, match_id, chat_id, 0, 0, is_afk_batter=True)

    task = asyncio.create_task(_timeout())
    active_timers[key] = task


# ═══════════════════════════════════════════════
# CORE BALL PROCESSING
# ═══════════════════════════════════════════════

async def process_ball_result(client, match_id, chat_id, batter_choice, bowler_choice,
                               is_afk_bowler=False, is_afk_batter=False):
    """Process the result of a ball."""
    match = Match.get_match_by_id(match_id)
    if not match:
        return

    cancel_timer(f"{match_id}_batter")
    cancel_timer(f"{match_id}_bowler")

    batter_id = match["current_batter_id"]
    bowler_id = match["current_bowler_id"]
    innings = match["innings"]
    current_over = match["current_over"]
    current_ball = match["current_ball"]
    mode = match["mode"]
    lang = match["commentary_lang"] or "en"
    over_balls = Match.get_over_balls(match)

    batter_user = Match.get_user(batter_id)
    bowler_user = Match.get_user(bowler_id)
    batter_name = safe_name(batter_user) if batter_user else "Batter"
    bowler_name = safe_name(bowler_user) if bowler_user else "Bowler"

    is_out = False
    runs = 0

    if is_afk_batter:
        is_out = True
        runs = 0
        batter_choice = 0
        bowler_choice = 0
    elif is_afk_bowler:
        is_out = False
        runs = 6
        bowler_choice = 0
    else:
        if batter_choice == bowler_choice:
            is_out = True
            runs = 0
        else:
            is_out = False
            runs = batter_choice

    # Record delivery
    new_ball = current_ball + 1
    Match.add_delivery(match_id, innings, current_over, new_ball, batter_id, bowler_id,
                       batter_choice, bowler_choice, runs, 1 if is_out else 0)

    # Update over balls tracking
    if not is_afk_bowler and not is_afk_batter:
        over_balls.append(bowler_choice)
    Match.set_over_balls(match_id, over_balls)

    # Update player stats
    bp = Match.get_player(match_id, batter_id)
    if bp:
        new_batting_runs = bp["batting_runs"] + runs
        new_batting_balls = bp["batting_balls"] + 1
        new_fours = bp["fours"] + (1 if runs == 4 else 0)
        new_sixes = bp["sixes"] + (1 if runs == 6 else 0)
        updates = {
            "batting_runs": new_batting_runs,
            "batting_balls": new_batting_balls,
            "fours": new_fours,
            "sixes": new_sixes,
        }
        if is_out:
            updates["is_out"] = 1
        Match.update_player(match_id, batter_id, **updates)

    bwp = Match.get_player(match_id, bowler_id)
    if bwp and not is_afk_bowler:
        Match.update_player(match_id, bowler_id,
            bowling_runs_given=bwp["bowling_runs_given"] + runs,
            bowling_balls=bwp["bowling_balls"] + 1,
            bowling_wickets=bwp["bowling_wickets"] + (1 if is_out else 0),
        )

    # Build result message
    if is_out:
        bp_updated = Match.get_player(match_id, batter_id)
        total_runs_batter = bp_updated["batting_runs"] if bp_updated else 0
        if total_runs_batter == 0:
            out_text = get_duck_message()
            image_type = "duck"
        else:
            out_text = get_out_commentary(lang)
            image_type = "out"
        result_text = (
            f"🎳 Bowler: {mention(bowler_id, bowler_name)} chose **{bowler_choice}**\n"
            f"🏏 Batter: {mention(batter_id, batter_name)} chose **{batter_choice}**\n\n"
            f"{out_text}\n"
            f"📊 {mention(batter_id, batter_name)} scored **{total_runs_batter} runs** ({bp_updated['batting_balls'] if bp_updated else 0}b)"
        )
        if is_afk_batter:
            result_text = (
                f"💤 {mention(batter_id, batter_name)} was timed out!\n"
                f"🔴 **OUT!** AFK Timeout!\n"
                f"📊 Scored **{total_runs_batter} runs**"
            )
        # Send image with result as caption
        await send_image_with_caption(client, chat_id, image_type, result_text)
    else:
        commentary = get_commentary(runs, lang)
        result_text = (
            f"🎳 Bowler: {mention(bowler_id, bowler_name)} chose **{bowler_choice}**\n"
            f"🏏 Batter: {mention(batter_id, batter_name)} chose **{batter_choice}**\n\n"
            f"{commentary}"
        )
        if is_afk_bowler:
            result_text = (
                f"💤 {mention(bowler_id, bowler_name)} was timed out!\n"
                f"🏏 **+6 RUNS** penalty!\n"
                f"6️⃣ SIX added to {mention(batter_id, batter_name)}'s score!"
            )
        
        # Send image with caption for runs (1-6)
        await send_image_with_caption(client, chat_id, str(runs), result_text)

    # Update match scores
    if mode == "solo":
        await update_solo_state(client, match_id, chat_id, runs, is_out, new_ball)
    else:
        await update_team_state(client, match_id, chat_id, runs, is_out, new_ball)


# ═══════════════════════════════════════════════
# SOLO MODE STATE MACHINE
# ═══════════════════════════════════════════════

async def update_solo_state(client, match_id, chat_id, runs, is_out, ball_num):
    """Update state after a ball in solo mode."""
    match = Match.get_match_by_id(match_id)
    if not match:
        return

    scores = Match.get_solo_scores(match)
    batter_id = str(match["current_batter_id"])
    
    # Use stored batting order (shuffled at match start), NOT DB order!
    player_ids = Match.get_team_batting_order(match)
    player_ids = [str(uid) for uid in player_ids]

    if batter_id not in scores:
        scores[batter_id] = {"runs": 0, "balls": 0, "is_out": False, "batting": True}

    scores[batter_id]["runs"] += runs
    scores[batter_id]["balls"] += 1

    over_done = (ball_num >= BALLS_PER_OVER)
    batter_done = is_out or over_done

    if batter_done:
        scores[batter_id]["batting"] = False
        if is_out:
            scores[batter_id]["is_out"] = True

        # Update user global stats
        uid = int(batter_id)
        total = scores[batter_id]["runs"]
        user = Match.get_user(uid)
        if user:
            high = max(user["highest_score"], total)
            Match.update_user_stats(uid,
                add_total_runs=total,
                add_matches_played=0,
                highest_score=high,
                add_ducks=1 if (is_out and total == 0) else 0,
            )

        Match.set_solo_scores(match_id, scores)

        # Move to next batter
        solo_idx = match["solo_batting_index"]
        next_idx = solo_idx + 1

        if next_idx >= len(player_ids):
            # All players have batted - match over
            await finish_solo_match(client, match_id, chat_id, scores, player_ids)
            return

        Match.update_match(match_id,
            solo_batting_index=next_idx,
            current_over=0,
            current_ball=0,
            over_balls_json="[]",
            bowler_last_ball=0,
        )

        next_batter_id = int(player_ids[next_idx])
        scores[str(next_batter_id)] = {"runs": 0, "balls": 0, "is_out": False, "batting": True}
        Match.set_solo_scores(match_id, scores)

        # Pick bowler (rotate among other players)
        bowling_idx = match["solo_bowling_index"]
        bowler_uid = pick_solo_bowler(player_ids, next_idx, bowling_idx)
        new_bowl_idx = player_ids.index(str(bowler_uid))

        Match.update_match(match_id,
            current_batter_id=next_batter_id,
            current_bowler_id=bowler_uid,
            solo_bowling_index=new_bowl_idx,
            temp_batter_choice=0,
            temp_bowler_choice=0,
        )

        batter_user = Match.get_user(next_batter_id)
        bowler_user = Match.get_user(bowler_uid)
        bname = safe_name(batter_user)
        bwname = safe_name(bowler_user)

        if over_done and not is_out:
            await safe_send(client, chat_id,
                f"📢 Over complete! {mention(int(batter_id), safe_name(Match.get_user(int(batter_id))))} scored **{scores[batter_id]['runs']}** runs!\n\n")

        await safe_send(client, chat_id,
            f"🏏 Next up: {mention(next_batter_id, bname)}, you're batting! Type **1-6** in the group!")

        Match.update_match(match_id, state=MatchState.BATTER_WAITING)
        await start_afk_timer(client, match_id, "batter", next_batter_id, chat_id)
        return

    # Ball done, but batter continues
    Match.update_match(match_id,
        current_ball=ball_num,
        temp_batter_choice=0,
        temp_bowler_choice=0,
        bowler_last_ball=match["temp_bowler_choice"] if not is_out else 0,
        state=MatchState.BATTER_WAITING,
    )
    Match.set_solo_scores(match_id, scores)

    # Show mini score - only prompt batter
    total_runs = scores[batter_id]["runs"]
    total_balls = scores[batter_id]["balls"]
    batter_user = Match.get_user(int(batter_id))
    batter_name = safe_name(batter_user)
    await safe_send(client, chat_id,
        f"📊 {mention(int(batter_id), batter_name)}: **{total_runs}** ({total_balls}b) | Over: {match['current_over']}.{ball_num}\n\n"
        f"🏏 {mention(int(batter_id), batter_name)}, type your next number **1-6**!")

    await start_afk_timer(client, match_id, "batter", int(batter_id), chat_id)


def pick_solo_bowler(player_ids, batter_idx, last_bowl_idx):
    """Pick next bowler (not the batter)."""
    n = len(player_ids)
    idx = (last_bowl_idx + 1) % n
    while idx == batter_idx:
        idx = (idx + 1) % n
    return int(player_ids[idx])


async def finish_solo_match(client, match_id, chat_id, scores, player_ids):
    """Determine winner in solo mode."""
    Match.update_match(match_id, state=MatchState.MATCH_OVER)

    sorted_players = sorted(
        player_ids,
        key=lambda uid: scores.get(uid, {}).get("runs", 0),
        reverse=True,
    )

    lines = [f"🏆 **MATCH OVER!** 🏆\n", get_match_end(), "\n📊 **Final Standings:**\n"]
    for i, uid in enumerate(sorted_players):
        user = Match.get_user(int(uid))
        name = safe_name(user) if user else "Player"
        data = scores.get(uid, {})
        r = data.get("runs", 0)
        b = data.get("balls", 0)
        out = " (out)" if data.get("is_out", False) else " (not out)"
        medal = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else "  "))
        lines.append(f"{medal} {name}: **{r}** ({b}b){out}")

    winner_id = int(sorted_players[0])
    winner_user = Match.get_user(winner_id)
    wname = safe_name(winner_user) if winner_user else "Player"
    lines.append(f"\n🎊 **Winner: {mention(winner_id, wname)}!** 🎊")

    # Update winner stats
    Match.update_user_stats(winner_id, add_matches_won=1)
    for uid in player_ids:
        Match.update_user_stats(int(uid), add_matches_played=1)

    await safe_send(client, chat_id, "\n".join(lines))
    cancel_timer(f"{match_id}_batter")
    cancel_timer(f"{match_id}_bowler")


# ═══════════════════════════════════════════════
# TEAM MODE STATE MACHINE
# ═══════════════════════════════════════════════

async def update_team_state(client, match_id, chat_id, runs, is_out, ball_num):
    """Update state after a ball in team mode."""
    match = Match.get_match_by_id(match_id)
    if not match:
        return

    innings = match["innings"]
    batting_team = match["batting_team"]
    bowling_team = match["bowling_team"]
    batter_id = match["current_batter_id"]
    non_striker_id = match["current_non_striker_id"]

    # Update innings runs
    if innings == 1:
        new_runs = match["innings1_runs"] + runs
        new_wkts = match["innings1_wickets"] + (1 if is_out else 0)
        Match.update_match(match_id,
            innings1_runs=new_runs,
            innings1_wickets=new_wkts,
            innings1_overs=get_overs_text(match["current_over"], ball_num),
        )
    else:
        new_runs = match["innings2_runs"] + runs
        new_wkts = match["innings2_wickets"] + (1 if is_out else 0)
        Match.update_match(match_id,
            innings2_runs=new_runs,
            innings2_wickets=new_wkts,
            innings2_overs=get_overs_text(match["current_over"], ball_num),
        )

    bat_order = Match.get_team_batting_order(match)
    bowl_order = Match.get_team_bowling_order(match)
    bat_idx = match["team_batter_index"]
    bowl_idx = match["team_bowler_index"]

    over_done = (ball_num >= BALLS_PER_OVER)

    # Check if target chased (innings 2)
    if innings == 2 and not is_out:
        target = match["target"]
        if new_runs >= target:
            # Batting team wins
            Match.update_match(match_id, state=MatchState.MATCH_OVER)
            bat_team_players = Match.get_players(match_id, team=batting_team)
            remaining_wkts = len(bat_team_players) - 1 - new_wkts
            await safe_send(client, chat_id,
                f"🏆 **Team {batting_team} WINS** by **{max(remaining_wkts, 0)} wicket(s)!** 🎉\n\n"
                f"📊 Team {batting_team}: **{new_runs}/{new_wkts}**\n"
                f"🎯 Target was: **{target}**\n\n"
                f"{get_match_end()}")
            await update_team_winner_stats(match_id, batting_team)
            return

    # Check all out
    bat_team_players = Match.get_players(match_id, team=batting_team)
    total_wickets_possible = len(bat_team_players) - 1

    all_out = is_out and (new_wkts >= total_wickets_possible)

    # Determine total overs for the match
    total_overs = match["total_overs"]
    overs_done_fully = match["current_over"] + (1 if over_done else 0)
    innings_overs_done = (over_done and overs_done_fully >= total_overs) if total_overs > 0 else False

    innings_over = all_out or innings_overs_done

    if is_out and not all_out:
        # Next batter comes in
        next_bat_idx = bat_idx + 1
        if next_bat_idx < len(bat_order):
            new_batter_id = bat_order[next_bat_idx]
            Match.update_match(match_id,
                team_batter_index=next_bat_idx,
                current_batter_id=new_batter_id,
                current_ball=ball_num,
                temp_batter_choice=0,
                temp_bowler_choice=0,
            )
            user = Match.get_user(new_batter_id)
            bname = safe_name(user)
            await safe_send(client, chat_id,
                f"🏏 New batter: {mention(new_batter_id, bname)} walks in!\n"
                f"Type **1-6** to play!")

            if over_done:
                # Over is done, rotate strike, change bowler
                await handle_over_change_team(client, match_id, chat_id, new_batter_id, non_striker_id)
                return

            Match.update_match(match_id, state=MatchState.BATTER_WAITING)
            await start_afk_timer(client, match_id, "batter", new_batter_id, chat_id)
            return
        else:
            innings_over = True

    if innings_over:
        if innings == 1:
            # Switch to innings 2
            await start_innings_2(client, match_id, chat_id)
            return
        else:
            # Match over - determine result
            target = match["target"]
            first_inn_runs = match["innings1_runs"]
            if new_runs >= target:
                # Batting team (chasing) wins
                bat_remaining = total_wickets_possible - new_wkts
                await safe_send(client, chat_id,
                    f"🏆 **Team {batting_team} WINS** by **{max(bat_remaining, 0)} wicket(s)!** 🎉\n\n"
                    f"📊 {batting_team}: **{new_runs}/{new_wkts}**\n"
                    f"🎯 Target was: **{target}**\n\n"
                    f"{get_match_end()}")
                Match.update_match(match_id, state=MatchState.MATCH_OVER)
                await update_team_winner_stats(match_id, batting_team)
                return
            elif new_runs == first_inn_runs:
                # Tie
                await safe_send(client, chat_id,
                    f"🤝 **IT'S A TIE!** 🤝\n\n"
                    f"📊 Both teams scored **{new_runs}** runs!\n\n"
                    f"{get_match_end()}")
                Match.update_match(match_id, state=MatchState.MATCH_OVER)
                return
            else:
                # Bowling team (defended) wins
                diff = target - new_runs - 1
                await safe_send(client, chat_id,
                    f"🏆 **Team {bowling_team} WINS** by **{diff} run(s)!** 🎉\n\n"
                    f"📊 {batting_team}: **{new_runs}/{new_wkts}**\n"
                    f"🎯 Target was: **{target}**\n\n"
                    f"{get_match_end()}")
                Match.update_match(match_id, state=MatchState.MATCH_OVER)
                await update_team_winner_stats(match_id, bowling_team)
                return
        return

    # Strike rotation on odd runs
    if not is_out and runs in (1, 3, 5):
        old_batter = match["current_batter_id"]
        old_non_striker = match["current_non_striker_id"]
        Match.update_match(match_id,
            current_batter_id=old_non_striker,
            current_non_striker_id=old_batter,
        )
        batter_id = old_non_striker

    if over_done:
        batter_id_now = match["current_batter_id"]
        non_striker_now = match["current_non_striker_id"]
        # Re-read after possible strike rotation
        match = Match.get_match_by_id(match_id)
        batter_id_now = match["current_batter_id"]
        non_striker_now = match["current_non_striker_id"]
        await handle_over_change_team(client, match_id, chat_id, batter_id_now, non_striker_now)
        return

    # Continue - next ball
    Match.update_match(match_id,
        current_ball=ball_num,
        temp_batter_choice=0,
        temp_bowler_choice=0,
        bowler_last_ball=match["temp_bowler_choice"] if not is_out else 0,
        state=MatchState.BATTER_WAITING,
    )

    # Re-read match for possibly rotated batter
    match = Match.get_match_by_id(match_id)
    cur_batter = match["current_batter_id"]
    batter_user = Match.get_user(cur_batter)
    bname = safe_name(batter_user)

    # Show mini score - only prompt batter
    if innings == 1:
        sc = f"{match['innings1_runs']}/{match['innings1_wickets']}"
    else:
        sc = f"{match['innings2_runs']}/{match['innings2_wickets']}"
        needed = match["target"] - match["innings2_runs"]
        sc += f" (need {needed} more)"

    await safe_send(client, chat_id,
        f"📊 Score: **{sc}** | Over: {match['current_over']}.{ball_num}\n\n"
        f"🏏 {mention(cur_batter, bname)}, type **1-6**!")

    await start_afk_timer(client, match_id, "batter", cur_batter, chat_id)


async def handle_over_change_team(client, match_id, chat_id, batter_id, non_striker_id):
    """Handle end of over in team mode - rotate strike, change bowler."""
    match = Match.get_match_by_id(match_id)
    if not match:
        return

    # Rotate strike at end of over
    new_batter = non_striker_id
    new_non_striker = batter_id

    bowl_order = Match.get_team_bowling_order(match)
    bowl_idx = match["team_bowler_index"]
    new_bowl_idx = (bowl_idx + 1) % len(bowl_order) if bowl_order else 0
    new_bowler_id = bowl_order[new_bowl_idx] if bowl_order else match["current_bowler_id"]

    new_over = match["current_over"] + 1

    Match.update_match(match_id,
        current_over=new_over,
        current_ball=0,
        current_batter_id=new_batter,
        current_non_striker_id=new_non_striker,
        current_bowler_id=new_bowler_id,
        team_bowler_index=new_bowl_idx,
        over_balls_json="[]",
        bowler_last_ball=0,
        temp_batter_choice=0,
        temp_bowler_choice=0,
        state=MatchState.BATTER_WAITING,
    )

    batter_user = Match.get_user(new_batter)
    bname = safe_name(batter_user)

    innings = match["innings"]
    if innings == 1:
        sc = f"{match['innings1_runs']}/{match['innings1_wickets']}"
    else:
        m2 = Match.get_match_by_id(match_id)
        sc = f"{m2['innings2_runs']}/{m2['innings2_wickets']}"

    await safe_send(client, chat_id,
        f"🔄 **End of Over {match['current_over']}!**\n"
        f"📊 Score: **{sc}**\n\n"
        f"🏏 {mention(new_batter, bname)}, you're on strike! Type **1-6**!")

    await start_afk_timer(client, match_id, "batter", new_batter, chat_id)


async def start_innings_2(client, match_id, chat_id):
    """Start the second innings in team mode."""
    match = Match.get_match_by_id(match_id)
    if not match:
        return

    target = match["innings1_runs"] + 1
    old_batting = match["batting_team"]
    old_bowling = match["bowling_team"]

    # Swap teams
    new_batting = old_bowling
    new_bowling = old_batting

    # Get batting order for new batting team
    new_bat_players = Match.get_players(match_id, team=new_batting)
    new_bowl_players = Match.get_players(match_id, team=new_bowling)

    if not new_bat_players or not new_bowl_players:
        await safe_send(client, chat_id, "❌ Error: No players found for teams!")
        Match.update_match(match_id, state=MatchState.MATCH_OVER)
        return

    bat_order = [p["user_id"] for p in new_bat_players]
    bowl_order = [p["user_id"] for p in new_bowl_players]

    # Reset player batting stats for innings 2
    for p in new_bat_players:
        Match.update_player(match_id, p["user_id"],
            batting_runs=0, batting_balls=0, is_out=0, fours=0, sixes=0)
    for p in new_bowl_players:
        Match.update_player(match_id, p["user_id"],
            bowling_runs_given=0, bowling_balls=0, bowling_wickets=0)

    opener1 = bat_order[0]
    opener2 = bat_order[1] if len(bat_order) > 1 else bat_order[0]
    first_bowler = bowl_order[0]

    Match.update_match(match_id,
        innings=2,
        batting_team=new_batting,
        bowling_team=new_bowling,
        target=target,
        current_over=0,
        current_ball=0,
        current_batter_id=opener1,
        current_non_striker_id=opener2,
        current_bowler_id=first_bowler,
        team_batter_index=1 if len(bat_order) > 1 else 0,
        team_bowler_index=0,
        over_balls_json="[]",
        bowler_last_ball=0,
        temp_batter_choice=0,
        temp_bowler_choice=0,
        state=MatchState.BATTER_WAITING,
    )
    Match.set_team_batting_order(match_id, bat_order)
    Match.set_team_bowling_order(match_id, bowl_order)

    u1 = Match.get_user(opener1)
    u2 = Match.get_user(opener2)

    await safe_send(client, chat_id,
        f"{get_innings_break()}\n\n"
        f"🎯 **Target: {target} runs**\n\n"
        f"🏏 **{new_batting}** now batting!\n"
        f"Openers: {mention(opener1, safe_name(u1))} & {mention(opener2, safe_name(u2))}\n\n"
        f"🏏 {mention(opener1, safe_name(u1))}, type **1-6** to start!")

    await start_afk_timer(client, match_id, "batter", opener1, chat_id)


async def update_team_winner_stats(match_id, winning_team):
    """Update stats for the winning team."""
    players = Match.get_players(match_id, team=winning_team)
    for p in players:
        Match.update_user_stats(p["user_id"], add_matches_won=1)
    all_players = Match.get_players(match_id)
    for p in all_players:
        Match.update_user_stats(p["user_id"], add_matches_played=1)


# ═══════════════════════════════════════════════
# BOWLER DM PROMPT
# ═══════════════════════════════════════════════

async def prompt_bowler_dm(client, match_id, bowler_id, batter_id):
    """Send bowling prompt to bowler in DM and notify in group."""
    match = Match.get_match_by_id(match_id)
    if not match:
        return

    chat_id = match["chat_id"]
    batter_user = Match.get_user(batter_id)
    bowler_user = Match.get_user(bowler_id)
    bname = safe_name(batter_user)
    bwname = safe_name(bowler_user)

    over_balls = Match.get_over_balls(match)
    last_ball = match["bowler_last_ball"]

    restricted = []
    for n in range(1, 7):
        if not Match.check_bowling_restriction(over_balls, n, last_ball):
            restricted.append(str(n))

    restrict_text = ""
    if restricted:
        restrict_text = f"\n🚫 Restricted: {', '.join(restricted)}"

    dm_msg = (
        f"🎳 **Your turn to bowl!**\n\n"
        f"🏏 Batter: {bname}\n"
        f"📊 Over: {match['current_over']}.{match['current_ball']}\n"
        f"{restrict_text}\n\n"
        f"Type a number **1-6** here to bowl! 🎯"
    )

    result = await safe_send_dm(client, bowler_id, dm_msg)
    
    if not result:
        # DM failed - bowler hasn't started the bot yet
        global BOT_USERNAME
        if not BOT_USERNAME:
            me = await client.get_me()
            BOT_USERNAME = me.username or "this_bot"
        await safe_send(client, chat_id,
            f"🎳 {mention(bowler_id, bwname)}, it's your turn to bowl!\n\n"
            f"⚠️ **You haven't started the bot yet!**\n"
            f"👉 Click here: @{BOT_USERNAME} and press **START**\n"
            f"Then you'll get the bowling prompt in DM!")


# ═══════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════

@bot.on_message(filters.command("start") & filters.private)
async def cmd_start_private(client, message):
    user = message.from_user
    Match.ensure_user(user.id, safe_name(user), safe_username(user))

    # Check if this user has a pending bowling turn
    match = Match.get_match_by_bowler_dm(user.id)
    if match:
        batter_id = match["current_batter_id"]
        await prompt_bowler_dm(client, match["match_id"], user.id, batter_id)
        return

    await safe_send(client, message.chat.id,
        f"🏏 **Welcome to Hand Cricket Bot!** 🏏\n\n"
        f"Add me to a group and use /startcricket to begin!\n\n"
        f"{RULES_TEXT}")


@bot.on_message(filters.command("start") & filters.group)
async def cmd_start_group(client, message):
    await safe_send(client, message.chat.id,
        "🏏 **Hand Cricket Bot** 🏏\n\n"
        "Use /startcricket to create a match!\n"
        "Use /joinsolo for solo mode or /join_team_a / /join_team_b for team mode.")


@bot.on_message(filters.command("startcricket") & filters.group)
async def cmd_startcricket(client, message):
    chat_id = message.chat.id
    user = message.from_user

    existing = Match.get_any_active(chat_id)
    if existing:
        await safe_send(client, chat_id,
            "⚠️ A match is already in progress! Use /endcricket to end it first.")
        return

    Match.ensure_user(user.id, safe_name(user), safe_username(user))
    match = Match.create_match(chat_id, user.id)

    await safe_send(client, chat_id,
        f"🏏 **Match Lobby Created!** 🏏\n\n"
        f"Host: {mention(user.id, safe_name(user))}\n\n"
        f"**Join the match:**\n"
        f"🎯 /joinsolo - Free-for-all solo mode\n"
        f"🅰️ /join_team_a - Join Team A\n"
        f"🅱️ /join_team_b - Join Team B\n\n"
        f"Use /forcestart when everyone has joined!")


@bot.on_message(filters.command("joinsolo") & filters.group)
async def cmd_joinsolo(client, message):
    chat_id = message.chat.id
    user = message.from_user
    Match.ensure_user(user.id, safe_name(user), safe_username(user))

    match = Match.get_lobby(chat_id)
    if not match:
        await safe_send(client, chat_id, "❌ No lobby found! Use /startcricket first.")
        return

    if match["mode"] == "team" and len(Match.get_players(match["match_id"])) > 0:
        await safe_send(client, chat_id, "❌ This lobby is in team mode! Use /join_team_a or /join_team_b.")
        return

    Match.update_match(match["match_id"], mode="solo")
    added = Match.add_player(match["match_id"], user.id, team=None)
    if not added:
        await safe_send(client, chat_id, f"⚠️ {safe_name(user)}, you're already in the match!")
        return

    players = Match.get_players(match["match_id"])
    names = []
    for p in players:
        u = Match.get_user(p["user_id"])
        names.append(safe_name(u) if u else "Player")

    await safe_send(client, chat_id,
        f"✅ {mention(user.id, safe_name(user))} joined! (Solo Mode)\n"
        f"👥 Players ({len(players)}): {', '.join(names)}\n\n"
        f"Use /forcestart when ready!")


@bot.on_message(filters.command("join_team_a") & filters.group)
async def cmd_join_team_a(client, message):
    await join_team(client, message, "A")


@bot.on_message(filters.command("join_team_b") & filters.group)
async def cmd_join_team_b(client, message):
    await join_team(client, message, "B")


async def join_team(client, message, team):
    chat_id = message.chat.id
    user = message.from_user
    Match.ensure_user(user.id, safe_name(user), safe_username(user))

    match = Match.get_lobby(chat_id)
    if not match:
        await safe_send(client, chat_id, "❌ No lobby found! Use /startcricket first.")
        return

    if match["mode"] == "solo" and len(Match.get_players(match["match_id"])) > 0:
        # Check if any existing players have no team (solo mode)
        existing = Match.get_players(match["match_id"])
        has_solo = any(p["team"] is None for p in existing)
        if has_solo:
            await safe_send(client, chat_id, "❌ This lobby is in solo mode! Use /joinsolo.")
            return

    Match.update_match(match["match_id"], mode="team")
    added = Match.add_player(match["match_id"], user.id, team=team)
    if not added:
        await safe_send(client, chat_id, f"⚠️ {safe_name(user)}, you're already in the match!")
        return

    team_a = Match.get_players(match["match_id"], team="A")
    team_b = Match.get_players(match["match_id"], team="B")

    a_names = [safe_name(Match.get_user(p["user_id"])) for p in team_a]
    b_names = [safe_name(Match.get_user(p["user_id"])) for p in team_b]

    await safe_send(client, chat_id,
        f"✅ {mention(user.id, safe_name(user))} joined **Team {team}**!\n\n"
        f"🅰️ Team A ({len(team_a)}): {', '.join(a_names) or 'Empty'}\n"
        f"🅱️ Team B ({len(team_b)}): {', '.join(b_names) or 'Empty'}\n\n"
        f"Use /forcestart when ready!")


@bot.on_message(filters.command("forcestart") & filters.group)
async def cmd_forcestart(client, message):
    chat_id = message.chat.id
    user = message.from_user

    match = Match.get_lobby(chat_id)
    if not match:
        await safe_send(client, chat_id, "❌ No lobby found! Use /startcricket first.")
        return

    if match["host_id"] != user.id:
        await safe_send(client, chat_id, "❌ Only the host can force start!")
        return

    mode = match["mode"]
    match_id = match["match_id"]
    players = Match.get_players(match_id)

    if mode == "solo":
        if len(players) < 2:
            await safe_send(client, chat_id, "❌ Need at least 2 players for solo mode!")
            return
        await start_solo_match(client, match_id, chat_id)
    else:
        team_a = Match.get_players(match_id, team="A")
        team_b = Match.get_players(match_id, team="B")
        if len(team_a) < 1 or len(team_b) < 1:
            await safe_send(client, chat_id, "❌ Each team needs at least 1 player!")
            return
        await start_team_toss(client, match_id, chat_id)


async def start_solo_match(client, match_id, chat_id):
    """Start a solo mode match."""
    players = Match.get_players(match_id)
    player_ids = [p["user_id"] for p in players]  # Use int, not str
    random.shuffle(player_ids)

    # IMPORTANT: Store shuffled batting order in DB for later use!
    Match.set_team_batting_order(match_id, player_ids)

    scores = {}
    first_batter = player_ids[0]
    scores[str(first_batter)] = {"runs": 0, "balls": 0, "is_out": False, "batting": True}

    # Pick first bowler (not the batter)
    player_ids_str = [str(uid) for uid in player_ids]
    bowler_uid = pick_solo_bowler(player_ids_str, 0, -1)

    Match.update_match(match_id,
        state=MatchState.BATTER_WAITING,
        innings=1,
        current_over=0,
        current_ball=0,
        current_batter_id=first_batter,
        current_bowler_id=bowler_uid,
        solo_batting_index=0,
        solo_bowling_index=player_ids_str.index(str(bowler_uid)),
        temp_batter_choice=0,
        temp_bowler_choice=0,
        over_balls_json="[]",
        bowler_last_ball=0,
    )
    Match.set_solo_scores(match_id, scores)

    batter_user = Match.get_user(first_batter)
    bname = safe_name(batter_user)

    order_text = "\n".join(
        f"  {i+1}. {safe_name(Match.get_user(uid))}"
        for i, uid in enumerate(player_ids)
    )

    await safe_send(client, chat_id,
        f"🏏 **MATCH STARTED!** 🏏 (Solo Mode)\n\n"
        f"{get_match_start()}\n\n"
        f"📋 **Batting Order:**\n{order_text}\n\n"
        f"Each player bats for **1 over (6 balls)**.\n"
        f"Highest score wins! 🏆\n\n"
        f"🏏 {mention(first_batter, bname)}, you're batting first! Type **1-6** in the group!")

    await start_afk_timer(client, match_id, "batter", first_batter, chat_id)


async def start_team_toss(client, match_id, chat_id):
    """Start the toss for team mode."""
    match = Match.get_match_by_id(match_id)
    host_id = match["host_id"]

    team_a = Match.get_players(match_id, team="A")
    team_b = Match.get_players(match_id, team="B")

    # Pick random toss winner team
    toss_team = random.choice(["A", "B"])
    toss_players = team_a if toss_team == "A" else team_b
    toss_winner = toss_players[0]["user_id"]

    Match.update_match(match_id,
        state=MatchState.TOSS_CHOICE,
        toss_winner_id=toss_winner,
    )

    user = Match.get_user(toss_winner)
    wname = safe_name(user)

    await safe_send(client, chat_id,
        f"🪙 **TOSS TIME!** 🪙\n\n"
        f"The coin spins... 🌀\n\n"
        f"🎉 **Team {toss_team}** wins the toss!\n"
        f"{mention(toss_winner, wname)}, choose:\n\n"
        f"/bat - Bat first 🏏\n"
        f"/field - Field first 🎳")


@bot.on_message(filters.command("bat") & filters.group)
async def cmd_bat(client, message):
    await handle_toss_choice(client, message, "bat")


@bot.on_message(filters.command("field") & filters.group)
async def cmd_field(client, message):
    await handle_toss_choice(client, message, "field")


async def handle_toss_choice(client, message, choice):
    chat_id = message.chat.id
    user = message.from_user

    match = Match.get_any_active(chat_id)
    if not match or match["state"] != MatchState.TOSS_CHOICE:
        return

    if user.id != match["toss_winner_id"]:
        await safe_send(client, chat_id, "❌ Only the toss winner can choose!")
        return

    match_id = match["match_id"]
    toss_winner_id = match["toss_winner_id"]

    # Figure out which team the toss winner is on
    toss_player = Match.get_player(match_id, toss_winner_id)
    toss_team = toss_player["team"] if toss_player else "A"
    other_team = "B" if toss_team == "A" else "A"

    if choice == "bat":
        batting_team = toss_team
        bowling_team = other_team
    else:
        batting_team = other_team
        bowling_team = toss_team

    Match.update_match(match_id,
        toss_choice=choice,
        batting_team=batting_team,
        bowling_team=bowling_team,
    )

    await safe_send(client, chat_id,
        f"🏏 **Team {batting_team}** will bat first!\n"
        f"🎳 **Team {bowling_team}** will bowl first!\n\n"
        f"Host, set the batting order:\n"
        f"`/batting <number_of_overs>` - Set total overs (e.g., /batting 2)\n"
        f"Or /forcestart again to start with default 2 overs.\n\n"
        f"Starting with default settings...")

    # Auto-start with 2 overs
    await start_team_match(client, match_id, chat_id, total_overs=2)


@bot.on_message(filters.command("batting") & filters.group)
async def cmd_batting(client, message):
    chat_id = message.chat.id
    user = message.from_user

    match = Match.get_any_active(chat_id)
    if not match:
        return

    if match["host_id"] != user.id:
        await safe_send(client, chat_id, "❌ Only the host can set overs!")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await safe_send(client, chat_id, "Usage: /batting <number_of_overs>\nExample: /batting 3")
        return

    try:
        overs = int(parts[1])
        if overs < 1 or overs > 20:
            await safe_send(client, chat_id, "❌ Overs must be between 1 and 20!")
            return
    except ValueError:
        await safe_send(client, chat_id, "❌ Invalid number!")
        return

    match_id = match["match_id"]
    if match["state"] in (MatchState.TOSS_CHOICE, MatchState.LOBBY):
        Match.update_match(match_id, total_overs=overs)
        await safe_send(client, chat_id, f"✅ Match set to **{overs} overs** per innings!")
    elif match["batting_team"]:
        Match.update_match(match_id, total_overs=overs)
        await safe_send(client, chat_id, f"✅ Overs updated to **{overs}**!")


@bot.on_message(filters.command("bowling") & filters.group)
async def cmd_bowling(client, message):
    chat_id = message.chat.id
    await safe_send(client, chat_id,
        "ℹ️ Bowling is done in the bot's DM!\n"
        "The bowler will receive a prompt in private chat.")


async def start_team_match(client, match_id, chat_id, total_overs=2):
    """Start team mode innings 1."""
    match = Match.get_match_by_id(match_id)
    if not match:
        return

    batting_team = match["batting_team"]
    bowling_team = match["bowling_team"]

    bat_players = Match.get_players(match_id, team=batting_team)
    bowl_players = Match.get_players(match_id, team=bowling_team)

    bat_order = [p["user_id"] for p in bat_players]
    bowl_order = [p["user_id"] for p in bowl_players]

    opener1 = bat_order[0]
    opener2 = bat_order[1] if len(bat_order) > 1 else bat_order[0]
    first_bowler = bowl_order[0]

    Match.set_team_batting_order(match_id, bat_order)
    Match.set_team_bowling_order(match_id, bowl_order)

    Match.update_match(match_id,
        state=MatchState.BATTER_WAITING,
        innings=1,
        total_overs=total_overs,
        current_over=0,
        current_ball=0,
        current_batter_id=opener1,
        current_non_striker_id=opener2,
        current_bowler_id=first_bowler,
        team_batter_index=1 if len(bat_order) > 1 else 0,
        team_bowler_index=0,
        over_balls_json="[]",
        bowler_last_ball=0,
        temp_batter_choice=0,
        temp_bowler_choice=0,
        innings1_runs=0,
        innings1_wickets=0,
        innings1_overs="0.0",
    )

    u1 = Match.get_user(opener1)
    u2 = Match.get_user(opener2)

    bat_names = "\n".join(f"  {i+1}. {safe_name(Match.get_user(uid))}" for i, uid in enumerate(bat_order))
    bowl_names = "\n".join(f"  {i+1}. {safe_name(Match.get_user(uid))}" for i, uid in enumerate(bowl_order))

    await safe_send(client, chat_id,
        f"🏏 **MATCH STARTED!** 🏏 (Team Mode - {total_overs} overs)\n\n"
        f"{get_match_start()}\n\n"
        f"🏏 **Team {batting_team} batting:**\n{bat_names}\n\n"
        f"🎳 **Team {bowling_team} bowling:**\n{bowl_names}\n\n"
        f"🏏 Openers: {mention(opener1, safe_name(u1))} & {mention(opener2, safe_name(u2))}\n\n"
        f"🏏 {mention(opener1, safe_name(u1))}, type **1-6** in the group!")

    await start_afk_timer(client, match_id, "batter", opener1, chat_id)


@bot.on_message(filters.command("score") & filters.group)
async def cmd_score(client, message):
    chat_id = message.chat.id
    match = Match.get_any_active(chat_id)
    if not match:
        await safe_send(client, chat_id, "❌ No active match!")
        return

    if match["mode"] == "solo":
        await safe_send(client, chat_id, build_solo_scoreboard(match))
    else:
        await safe_send(client, chat_id, build_team_scoreboard(match))


@bot.on_message(filters.command("scoreboard") & filters.group)
async def cmd_scoreboard(client, message):
    chat_id = message.chat.id
    match = Match.get_any_active(chat_id)
    if not match:
        # Try to find the last finished match
        db = get_db()
        match = db.execute(
            "SELECT * FROM matches WHERE chat_id = ? ORDER BY match_id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        if not match:
            await safe_send(client, chat_id, "❌ No match found!")
            return

    if match["mode"] == "solo":
        await safe_send(client, chat_id, build_solo_scoreboard(match))
    else:
        await safe_send(client, chat_id, build_team_scoreboard(match))


@bot.on_message(filters.command("teams") & filters.group)
async def cmd_teams(client, message):
    chat_id = message.chat.id
    match = Match.get_any_active(chat_id)
    if not match:
        await safe_send(client, chat_id, "❌ No active match!")
        return

    if match["mode"] == "solo":
        players = Match.get_players(match["match_id"])
        names = [safe_name(Match.get_user(p["user_id"])) for p in players]
        await safe_send(client, chat_id,
            f"👥 **Solo Mode Players:**\n" + "\n".join(f"  • {n}" for n in names))
    else:
        team_a = Match.get_players(match["match_id"], team="A")
        team_b = Match.get_players(match["match_id"], team="B")
        a_names = [safe_name(Match.get_user(p["user_id"])) for p in team_a]
        b_names = [safe_name(Match.get_user(p["user_id"])) for p in team_b]
        await safe_send(client, chat_id,
            f"🅰️ **Team A:** {', '.join(a_names) or 'Empty'}\n"
            f"🅱️ **Team B:** {', '.join(b_names) or 'Empty'}")


@bot.on_message(filters.command("sledge") & filters.group)
async def cmd_sledge(client, message):
    await safe_send(client, message.chat.id, get_sledge())


@bot.on_message(filters.command("call") & filters.group)
async def cmd_call(client, message):
    chat_id = message.chat.id
    match = Match.get_any_active(chat_id)
    if not match:
        await safe_send(client, chat_id, "❌ No active match!")
        return

    state = match["state"]
    if state == MatchState.BATTER_WAITING:
        batter_id = match["current_batter_id"]
        user = Match.get_user(batter_id)
        bname = safe_name(user)
        await safe_send(client, chat_id,
            f"📢 {mention(batter_id, bname)}! It's your turn to bat! Type **1-6** in the group! ⏱")
    elif state == MatchState.BOWLER_WAITING:
        bowler_id = match["current_bowler_id"]
        user = Match.get_user(bowler_id)
        bwname = safe_name(user)
        await safe_send(client, chat_id,
            f"📢 {mention(bowler_id, bwname)}! It's your turn to bowl! Check my DM! ⏱")
    else:
        await safe_send(client, chat_id, "ℹ️ No one's turn is pending right now.")


@bot.on_message(filters.command("changecom") & filters.group)
async def cmd_changecom(client, message):
    chat_id = message.chat.id
    match = Match.get_any_active(chat_id)
    if not match:
        await safe_send(client, chat_id, "❌ No active match!")
        return

    current = match["commentary_lang"] or "en"
    new_lang = "hi" if current == "en" else "en"
    Match.update_match(match["match_id"], commentary_lang=new_lang)

    lang_name = "Hindi 🇮🇳" if new_lang == "hi" else "English 🇬🇧"
    await safe_send(client, chat_id, f"🗣️ Commentary language changed to **{lang_name}**!")


@bot.on_message(filters.command("endcricket") & filters.group)
async def cmd_endcricket(client, message):
    chat_id = message.chat.id
    user = message.from_user

    match = Match.get_any_active(chat_id)
    if not match:
        await safe_send(client, chat_id, "❌ No active match to end!")
        return

    match_id = match["match_id"]
    # Allow host or any player to end
    Match.update_match(match_id, state=MatchState.MATCH_OVER)
    cancel_timer(f"{match_id}_batter")
    cancel_timer(f"{match_id}_bowler")

    await safe_send(client, chat_id,
        f"🛑 Match ended by {mention(user.id, safe_name(user))}!\n"
        f"Use /startcricket to start a new match.")


# ═══════════════════════════════════════════════
# GLOBAL MESSAGE HANDLER (Numbers 1-6)
# ═══════════════════════════════════════════════

@bot.on_message(filters.text & ~filters.command([
    "start", "startcricket", "joinsolo", "join_team_a", "join_team_b",
    "forcestart", "batting", "bowling", "bat", "field", "score",
    "scoreboard", "teams", "sledge", "call", "changecom", "endcricket"
]))
async def handle_number_message(client, message):
    """Handle plain text numbers 1-6 from batter (group) or bowler (DM)."""
    text = message.text.strip()
    if text not in ("1", "2", "3", "4", "5", "6"):
        return

    number = int(text)
    user = message.from_user
    if not user:
        return

    Match.ensure_user(user.id, safe_name(user), safe_username(user))

    if message.chat.type == ChatType.PRIVATE:
        # This is a bowler responding in DM
        await handle_bowler_dm(client, message, user.id, number)
    elif message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        # This could be a batter in the group
        await handle_batter_group(client, message, user.id, number)


async def handle_batter_group(client, message, user_id, number):
    """Handle batter's number in the group."""
    chat_id = message.chat.id

    match = Match.get_any_active(chat_id)
    if not match:
        return

    if match["state"] != MatchState.BATTER_WAITING:
        return

    if user_id != match["current_batter_id"]:
        return

    match_id = match["match_id"]

    # Cancel batter AFK timer
    cancel_timer(f"{match_id}_batter")

    # Save batter's choice in DB, switch state to BOWLER_WAITING
    Match.update_match(match_id,
        temp_batter_choice=number,
        state=MatchState.BOWLER_WAITING,
    )

    batter_user = Match.get_user(user_id)
    bowler_id = match["current_bowler_id"]
    bowler_user = Match.get_user(bowler_id)
    bname = safe_name(batter_user)
    bwname = safe_name(bowler_user)

    # Mention bowler in group and tell them to check DM
    await safe_send(client, chat_id,
        f"🏏 {mention(user_id, bname)} has played! ✅\n\n"
        f"🎳 {mention(bowler_id, bwname)}, your turn to bowl! Go to my DM and type **1-6**!")

    # NOW send DM to bowler
    await prompt_bowler_dm(client, match_id, bowler_id, user_id)

    # Start bowler AFK timer
    await start_afk_timer(client, match_id, "bowler", bowler_id, chat_id)


async def handle_bowler_dm(client, message, user_id, number):
    """Handle bowler's number in DM."""
    match = Match.get_match_by_bowler_dm(user_id)
    if not match:
        await safe_send_dm(client, user_id,
            "❌ You don't have a pending bowling turn right now!")
        return

    match_id = match["match_id"]
    chat_id = match["chat_id"]

    # Check bowling restrictions
    over_balls = Match.get_over_balls(match)
    last_ball = match["bowler_last_ball"]

    if not Match.check_bowling_restriction(over_balls, number, last_ball):
        restricted = []
        for n in range(1, 7):
            if not Match.check_bowling_restriction(over_balls, n, last_ball):
                restricted.append(str(n))

        await safe_send_dm(client, user_id,
            f"🚫 You can't bowl **{number}**!\n"
            f"Restricted numbers: {', '.join(restricted)}\n"
            f"Choose another number **1-6**!")
        return

    # Cancel bowler AFK timer
    cancel_timer(f"{match_id}_bowler")

    batter_choice = match["temp_batter_choice"]

    # Save bowler choice
    Match.update_match(match_id,
        temp_bowler_choice=number,
        bowler_last_ball=number,
    )

    await safe_send_dm(client, user_id,
        f"🎳 You bowled **{number}**! ✅\n"
        f"⏳ Let's see the result...")

    # Process the ball
    await process_ball_result(client, match_id, chat_id, batter_choice, number)


# ═══════════════════════════════════════════════
# STARTUP HANDLER
# ═══════════════════════════════════════════════

@bot.on_message(filters.command("ping"))
async def cmd_ping(client, message):
    await safe_send(client, message.chat.id, "🏓 Pong! Bot is alive!")


async def cache_bot_username():
    """Cache bot username at startup."""
    global BOT_USERNAME
    me = await bot.get_me()
    BOT_USERNAME = me.username or "handcricket_bot"
    print(f"🤖 Bot username cached: @{BOT_USERNAME}")


# ═══════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    # Start Flask in a daemon thread
    def run_flask():
        flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"🌐 Flask server started on port {PORT}")

    # Run Pyrogram bot in the main thread
    print("🏏 Starting Hand Cricket Bot...")
    
    # Start bot and cache username
    async def main():
        await bot.start()
        await cache_bot_username()
        print("🏏 Hand Cricket Bot is running!")
        await asyncio.Event().wait()  # Keep running
    
    bot.run(main())
