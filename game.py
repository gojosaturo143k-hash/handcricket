import uuid
import random
from database import get_db
from rules import COMMENTARY

class MatchState:
    LOBBY = "LOBBY"
    SETUP = "SETUP"
    TOSS = "TOSS"
    INNINGS = "INNINGS"
    BATTER_WAITING = "BATTER_WAITING"
    BOWLER_WAITING = "BOWLER_WAITING"
    RESOLVE_BALL = "RESOLVE_BALL"
    NEXT_BATTER = "NEXT_BATTER"
    NEXT_INNINGS = "NEXT_INNINGS"
    RESULT = "RESULT"
    SUPER_OVER = "SUPER_OVER"

class Match:
    def __init__(self, match_id=None):
        self.match_id = match_id or str(uuid.uuid4())
        self.db = get_db()
        
    def create(self, chat_id, mode, host_id, overs=2):
        self.db.execute(
            "INSERT INTO matches (match_id, chat_id, mode, status, host_id, overs) VALUES (?, ?, ?, ?, ?, ?)",
            (self.match_id, chat_id, mode, MatchState.LOBBY, host_id, overs)
        )
        self.db.commit()

    def get(self):
        return self.db.execute("SELECT * FROM matches WHERE match_id = ?", (self.match_id,)).fetchone()

    def update_state(self, status):
        self.db.execute("UPDATE matches SET status = ? WHERE match_id = ?", (status, self.match_id))
        self.db.commit()

    def add_player(self, user_id, username, display_name, team='solo'):
        existing = self.db.execute(
            "SELECT telegram_id FROM match_players WHERE match_id = ? AND telegram_id = ?",
            (self.match_id, user_id)
        ).fetchone()
        if existing:
            return False
        
        count = self.db.execute(
            "SELECT COUNT(*) as c FROM match_players WHERE match_id = ? AND team = ?", 
            (self.match_id, team)
        ).fetchone()['c']
        
        self.db.execute(
            "INSERT INTO match_players (match_id, telegram_id, team, join_order, username, display_name) VALUES (?, ?, ?, ?, ?, ?)",
            (self.match_id, user_id, team, count + 1, username, display_name)
        )
        self.db.commit()
        return True

    def get_players(self, team=None):
        if team:
            return self.db.execute(
                "SELECT * FROM match_players WHERE match_id = ? AND team = ? ORDER BY join_order",
                (self.match_id, team)
            ).fetchall()
        return self.db.execute(
            "SELECT * FROM match_players WHERE match_id = ? ORDER BY team, join_order",
            (self.match_id,)
        ).fetchall()

    def set_batter(self, user_id):
        self.db.execute("UPDATE match_players SET is_batting = 0 WHERE match_id = ?", (self.match_id,))
        self.db.execute("UPDATE match_players SET is_batting = 1 WHERE match_id = ? AND telegram_id = ?", (self.match_id, user_id))
        # V2 Fix: Directly save in matches table
        self.db.execute("UPDATE matches SET current_batter_id = ? WHERE match_id = ?", (user_id, self.match_id))
        self.db.commit()

    def set_bowler(self, user_id):
        self.db.execute("UPDATE match_players SET is_bowling = 0 WHERE match_id = ?", (self.match_id,))
        self.db.execute("UPDATE match_players SET is_bowling = 1 WHERE match_id = ? AND telegram_id = ?", (self.match_id, user_id))
        # V2 Fix: Directly save in matches table
        self.db.execute("UPDATE matches SET current_bowler_id = ? WHERE match_id = ?", (user_id, self.match_id))
        self.db.commit()

    def get_current_batter(self):
        m = self.get()
        if not m or not m['current_batter_id']: return None
        return self.db.execute("SELECT * FROM match_players WHERE match_id = ? AND telegram_id = ?", (self.match_id, m['current_batter_id'])).fetchone()

    def get_current_bowler(self):
        m = self.get()
        if not m or not m['current_bowler_id']: return None
        return self.db.execute("SELECT * FROM match_players WHERE match_id = ? AND telegram_id = ?", (self.match_id, m['current_bowler_id'])).fetchone()

    def record_delivery(self, innings, over, ball, batter_id, bowler_id, b_choice, bw_choice, runs, is_wicket):
        self.db.execute(
            "INSERT INTO deliveries (match_id, innings, over_number, ball_number, batter_id, bowler_id, batter_choice, bowler_choice, runs, is_wicket) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self.match_id, innings, over, ball, batter_id, bowler_id, b_choice, bw_choice, runs, is_wicket)
        )
        if is_wicket:
            self.db.execute("UPDATE match_players SET is_out = 1 WHERE match_id = ? AND telegram_id = ?", (self.match_id, batter_id))
            
        self.db.execute(
            "UPDATE match_players SET runs = runs + ?, balls = balls + 1 WHERE match_id = ? AND telegram_id = ?",
            (runs, self.match_id, batter_id)
        )
        self.db.execute(
            "UPDATE match_players SET wickets = wickets + ? WHERE match_id = ? AND telegram_id = ?",
            (1 if is_wicket else 0, self.match_id, bowler_id)
        )
        
        # V2 Fix: Update match state directly in DB
        self.db.execute("UPDATE matches SET innings_runs = innings_runs + ?, current_ball = current_ball + 1 WHERE match_id = ?", (runs, self.match_id))
        if is_wicket:
            self.db.execute("UPDATE matches SET innings_wickets = innings_wickets + 1 WHERE match_id = ?", (self.match_id,))
            
        self.db.commit()

    def get_team_total(self, team):
        res = self.db.execute(
            "SELECT SUM(runs) as total, SUM(is_out) as wickets FROM match_players WHERE match_id = ? AND team = ?",
            (self.match_id, team)
        ).fetchone()
        return res['total'] or 0, res['wickets'] or 0

    def get_last_deliveries(self, over_num, innings, limit=2):
        return self.db.execute(
            "SELECT bowler_choice FROM deliveries WHERE match_id = ? AND innings = ? AND over_number = ? ORDER BY id DESC LIMIT ?",
            (self.match_id, innings, over_num, limit)
        ).fetchall()

    def is_delivery_valid(self, bowler_id, choice, over_num, innings):
        last = self.get_last_deliveries(over_num, innings, limit=2)
        
        if len(last) >= 1 and last[0]['bowler_choice'] == choice:
            if len(last) >= 2 and last[1]['bowler_choice'] == choice:
                return False, "has already been used twice consecutively."
        
        over_balls = self.db.execute(
            "SELECT COUNT(*) as c FROM deliveries WHERE match_id = ? AND innings = ? AND over_number = ? AND bowler_id = ? AND bowler_choice = ?",
            (self.match_id, innings, over_num, bowler_id, choice)
        ).fetchone()['c']
        
        if over_balls >= 3:
            return False, "has already been used 3 times in this over."

        return True, ""

    def unout_player(self, user_id):
        self.db.execute("UPDATE match_players SET is_out = 0 WHERE match_id = ? AND telegram_id = ?", (self.match_id, user_id))
        self.db.commit()

    def shift_player(self, user_id, new_team):
        self.db.execute("UPDATE match_players SET team = ? WHERE match_id = ? AND telegram_id = ?", (new_team, self.match_id, user_id))
        self.db.commit()


def get_match_by_group(chat_id):
    db = get_db()
    return db.execute("SELECT * FROM matches WHERE chat_id = ? AND status NOT IN ('RESULT', 'LOBBY')", (chat_id,)).fetchone()

def get_lobby_by_group(chat_id):
    db = get_db()
    return db.execute("SELECT * FROM matches WHERE chat_id = ? AND status = 'LOBBY'", (chat_id,)).fetchone()

def get_commentary(lang, key, batter=None):
    options = COMMENTARY.get(lang, COMMENTARY["eng"]).get(key, [])
    text = random.choice(options) if options else ""
    if batter:
        text = text.replace("{batter}", f"@{batter}")
    return text
