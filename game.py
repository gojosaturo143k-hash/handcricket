import json
from database import get_db


class MatchState:
    LOBBY = "LOBBY"
    TOSS = "TOSS"
    TOSS_CHOICE = "TOSS_CHOICE"
    BATTING_ORDER = "BATTING_ORDER"
    BATTER_WAITING = "BATTER_WAITING"
    BOWLER_WAITING = "BOWLER_WAITING"
    INNINGS_BREAK = "INNINGS_BREAK"
    MATCH_OVER = "MATCH_OVER"


class Match:
    """Handles all DB operations for a match."""

    @staticmethod
    def create_match(chat_id, host_id, mode="solo"):
        db = get_db()
        db.execute(
            "INSERT INTO matches (chat_id, host_id, mode, state) VALUES (?, ?, ?, ?)",
            (chat_id, host_id, mode, MatchState.LOBBY),
        )
        db.commit()
        return db.execute(
            "SELECT * FROM matches WHERE chat_id = ? ORDER BY match_id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()

    @staticmethod
    def get_match_by_chat(chat_id):
        db = get_db()
        row = db.execute(
            "SELECT * FROM matches WHERE chat_id = ? AND state != ? ORDER BY match_id DESC LIMIT 1",
            (chat_id, MatchState.MATCH_OVER),
        ).fetchone()
        return row

    @staticmethod
    def get_match_by_id(match_id):
        db = get_db()
        return db.execute(
            "SELECT * FROM matches WHERE match_id = ?", (match_id,)
        ).fetchone()

    @staticmethod
    def get_lobby(chat_id):
        db = get_db()
        return db.execute(
            "SELECT * FROM matches WHERE chat_id = ? AND state = ? ORDER BY match_id DESC LIMIT 1",
            (chat_id, MatchState.LOBBY),
        ).fetchone()

    @staticmethod
    def get_active_match(chat_id):
        db = get_db()
        return db.execute(
            "SELECT * FROM matches WHERE chat_id = ? AND state NOT IN (?, ?) ORDER BY match_id DESC LIMIT 1",
            (chat_id, MatchState.LOBBY, MatchState.MATCH_OVER),
        ).fetchone()

    @staticmethod
    def get_any_active(chat_id):
        """Get any non-finished match (lobby or active)."""
        db = get_db()
        return db.execute(
            "SELECT * FROM matches WHERE chat_id = ? AND state != ? ORDER BY match_id DESC LIMIT 1",
            (chat_id, MatchState.MATCH_OVER),
        ).fetchone()

    @staticmethod
    def update_match(match_id, **kwargs):
        db = get_db()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values())
        vals.append(match_id)
        db.execute(f"UPDATE matches SET {sets}, last_activity = CURRENT_TIMESTAMP WHERE match_id = ?", vals)
        db.commit()

    @staticmethod
    def end_match(match_id):
        Match.update_match(match_id, state=MatchState.MATCH_OVER)

    @staticmethod
    def add_player(match_id, user_id, team=None):
        db = get_db()
        existing = db.execute(
            "SELECT * FROM match_players WHERE match_id = ? AND user_id = ?",
            (match_id, user_id),
        ).fetchone()
        if existing:
            return False
        db.execute(
            "INSERT INTO match_players (match_id, user_id, team) VALUES (?, ?, ?)",
            (match_id, user_id, team),
        )
        db.commit()
        return True

    @staticmethod
    def get_players(match_id, team=None):
        db = get_db()
        if team:
            return db.execute(
                "SELECT * FROM match_players WHERE match_id = ? AND team = ?",
                (match_id, team),
            ).fetchall()
        return db.execute(
            "SELECT * FROM match_players WHERE match_id = ?", (match_id,)
        ).fetchall()

    @staticmethod
    def get_player(match_id, user_id):
        db = get_db()
        return db.execute(
            "SELECT * FROM match_players WHERE match_id = ? AND user_id = ?",
            (match_id, user_id),
        ).fetchone()

    @staticmethod
    def update_player(match_id, user_id, **kwargs):
        db = get_db()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values())
        vals.extend([match_id, user_id])
        db.execute(
            f"UPDATE match_players SET {sets} WHERE match_id = ? AND user_id = ?", vals
        )
        db.commit()

    @staticmethod
    def add_delivery(match_id, innings, over_num, ball_num, batter_id, bowler_id, batter_choice, bowler_choice, runs, is_wicket):
        db = get_db()
        db.execute(
            "INSERT INTO deliveries (match_id, innings, over_num, ball_num, batter_id, bowler_id, batter_choice, bowler_choice, runs, is_wicket) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (match_id, innings, over_num, ball_num, batter_id, bowler_id, batter_choice, bowler_choice, runs, is_wicket),
        )
        db.commit()

    @staticmethod
    def get_deliveries(match_id, innings=None):
        db = get_db()
        if innings is not None:
            return db.execute(
                "SELECT * FROM deliveries WHERE match_id = ? AND innings = ? ORDER BY id",
                (match_id, innings),
            ).fetchall()
        return db.execute(
            "SELECT * FROM deliveries WHERE match_id = ? ORDER BY id",
            (match_id,),
        ).fetchall()

    @staticmethod
    def ensure_user(user_id, display_name, username=None):
        db = get_db()
        existing = db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO users (user_id, display_name, username) VALUES (?, ?, ?)",
                (user_id, display_name, username),
            )
            db.commit()
        else:
            db.execute(
                "UPDATE users SET display_name = ?, username = ? WHERE user_id = ?",
                (display_name, username, user_id),
            )
            db.commit()

    @staticmethod
    def get_user(user_id):
        db = get_db()
        return db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

    @staticmethod
    def update_user_stats(user_id, **kwargs):
        db = get_db()
        sets = []
        vals = []
        for k, v in kwargs.items():
            if k.startswith("add_"):
                real_key = k[4:]
                sets.append(f"{real_key} = {real_key} + ?")
                vals.append(v)
            else:
                sets.append(f"{k} = ?")
                vals.append(v)
        vals.append(user_id)
        if sets:
            db.execute(f"UPDATE users SET {', '.join(sets)} WHERE user_id = ?", vals)
            db.commit()

    @staticmethod
    def get_over_balls(match):
        """Return list of ball numbers bowled this over."""
        raw = match["over_balls_json"]
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @staticmethod
    def set_over_balls(match_id, balls_list):
        Match.update_match(match_id, over_balls_json=json.dumps(balls_list))

    @staticmethod
    def get_solo_scores(match):
        raw = match["solo_scores_json"]
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    @staticmethod
    def set_solo_scores(match_id, scores_dict):
        Match.update_match(match_id, solo_scores_json=json.dumps(scores_dict))

    @staticmethod
    def get_team_batting_order(match):
        raw = match["team_batting_order_json"]
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @staticmethod
    def get_team_bowling_order(match):
        raw = match["team_bowling_order_json"]
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @staticmethod
    def set_team_batting_order(match_id, order):
        Match.update_match(match_id, team_batting_order_json=json.dumps(order))

    @staticmethod
    def set_team_bowling_order(match_id, order):
        Match.update_match(match_id, team_bowling_order_json=json.dumps(order))

    @staticmethod
    def get_match_by_bowler_dm(bowler_id):
        """Find a match where this user is the current bowler and state is BOWLER_WAITING."""
        db = get_db()
        return db.execute(
            "SELECT * FROM matches WHERE current_bowler_id = ? AND state = ? ORDER BY match_id DESC LIMIT 1",
            (bowler_id, MatchState.BOWLER_WAITING),
        ).fetchone()

    @staticmethod
    def check_bowling_restriction(over_balls, number, last_ball):
        """
        Returns True if the number is ALLOWED.
        Rules:
        - Same number cannot be used 3 times in an over.
        - Cannot bowl same number twice consecutively.
        """
        if number == last_ball and last_ball != 0:
            return False
        count = over_balls.count(number)
        if count >= 2:
            return False
        return True

    @staticmethod
    def format_overs(overs, balls):
        """Format overs like 2.3"""
        return f"{overs}.{balls}"
