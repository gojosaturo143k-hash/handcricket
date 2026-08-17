import sqlite3
import threading
import os

DB_NAME = "handcricket.db"

# Delete old DB on startup to fix schema issues on Render
if os.path.exists(DB_NAME):
    os.remove(DB_NAME)

local = threading.local()


def get_db():
    """Get a thread-local database connection."""
    if not hasattr(local, "db"):
        local.db = sqlite3.connect(DB_NAME, check_same_thread=False)
        local.db.row_factory = sqlite3.Row
        local.db.execute("PRAGMA journal_mode=WAL")
        local.db.execute("PRAGMA foreign_keys=ON")
    return local.db


def init_db():
    """Create all tables."""
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT 'Player',
            username TEXT DEFAULT NULL,
            total_runs INTEGER DEFAULT 0,
            total_wickets INTEGER DEFAULT 0,
            matches_played INTEGER DEFAULT 0,
            matches_won INTEGER DEFAULT 0,
            highest_score INTEGER DEFAULT 0,
            ducks INTEGER DEFAULT 0,
            sixes INTEGER DEFAULT 0,
            fours INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            host_id INTEGER NOT NULL,
            mode TEXT NOT NULL DEFAULT 'solo',
            state TEXT NOT NULL DEFAULT 'LOBBY',
            innings INTEGER DEFAULT 0,
            current_over INTEGER DEFAULT 0,
            current_ball INTEGER DEFAULT 0,
            current_batter_id INTEGER DEFAULT 0,
            current_bowler_id INTEGER DEFAULT 0,
            current_non_striker_id INTEGER DEFAULT 0,
            batting_team TEXT DEFAULT NULL,
            bowling_team TEXT DEFAULT NULL,
            team_a_runs INTEGER DEFAULT 0,
            team_a_wickets INTEGER DEFAULT 0,
            team_a_overs_done INTEGER DEFAULT 0,
            team_b_runs INTEGER DEFAULT 0,
            team_b_wickets INTEGER DEFAULT 0,
            team_b_overs_done INTEGER DEFAULT 0,
            target INTEGER DEFAULT 0,
            innings1_runs INTEGER DEFAULT 0,
            innings1_wickets INTEGER DEFAULT 0,
            innings1_overs TEXT DEFAULT '0.0',
            innings2_runs INTEGER DEFAULT 0,
            innings2_wickets INTEGER DEFAULT 0,
            innings2_overs TEXT DEFAULT '0.0',
            temp_batter_choice INTEGER DEFAULT 0,
            temp_bowler_choice INTEGER DEFAULT 0,
            toss_winner_id INTEGER DEFAULT 0,
            toss_choice TEXT DEFAULT NULL,
            over_balls_json TEXT DEFAULT '[]',
            bowler_last_ball INTEGER DEFAULT 0,
            solo_batting_index INTEGER DEFAULT 0,
            solo_bowling_index INTEGER DEFAULT 0,
            solo_scores_json TEXT DEFAULT '{}',
            team_batting_order_json TEXT DEFAULT '[]',
            team_bowling_order_json TEXT DEFAULT '[]',
            team_batter_index INTEGER DEFAULT 0,
            team_bowler_index INTEGER DEFAULT 0,
            total_overs INTEGER DEFAULT 0,
            commentary_lang TEXT DEFAULT 'en',
            waiting_for TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS match_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            team TEXT DEFAULT NULL,
            batting_runs INTEGER DEFAULT 0,
            batting_balls INTEGER DEFAULT 0,
            bowling_runs_given INTEGER DEFAULT 0,
            bowling_balls INTEGER DEFAULT 0,
            bowling_wickets INTEGER DEFAULT 0,
            is_out INTEGER DEFAULT 0,
            fours INTEGER DEFAULT 0,
            sixes INTEGER DEFAULT 0,
            FOREIGN KEY (match_id) REFERENCES matches(match_id)
        );

        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            innings INTEGER NOT NULL,
            over_num INTEGER NOT NULL,
            ball_num INTEGER NOT NULL,
            batter_id INTEGER NOT NULL,
            bowler_id INTEGER NOT NULL,
            batter_choice INTEGER NOT NULL,
            bowler_choice INTEGER NOT NULL,
            runs INTEGER DEFAULT 0,
            is_wicket INTEGER DEFAULT 0,
            FOREIGN KEY (match_id) REFERENCES matches(match_id)
        );

        CREATE INDEX IF NOT EXISTS idx_matches_chat ON matches(chat_id);
        CREATE INDEX IF NOT EXISTS idx_match_players_match ON match_players(match_id);
        CREATE INDEX IF NOT EXISTS idx_deliveries_match ON deliveries(match_id);
    """)
    db.commit()


init_db()
