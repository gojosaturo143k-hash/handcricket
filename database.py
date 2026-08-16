import sqlite3
import threading
import os

DB_NAME = "handcricket.db"

# Yeh line Render pe purani corrupt DB ko delete kar degi jab naya code deploy hoga
if os.path.exists(DB_NAME):
    os.remove(DB_NAME)

local = threading.local()

def get_db():
    if not hasattr(local, 'db'):
        local.db = sqlite3.connect(DB_NAME, check_same_thread=False)
        local.db.row_factory = sqlite3.Row
        local.db.execute("PRAGMA journal_mode=WAL")
    return local.db

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY, username TEXT, display_name TEXT,
        matches INTEGER DEFAULT 0, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
        runs INTEGER DEFAULT 0, wickets INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS matches (
        match_id TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, mode TEXT NOT NULL,
        status TEXT NOT NULL, host_id INTEGER NOT NULL, overs INTEGER DEFAULT 2,
        current_innings INTEGER DEFAULT 1, team_a_name TEXT DEFAULT 'Team A',
        team_b_name TEXT DEFAULT 'Team B', toss_winner INTEGER, toss_choice TEXT,
        target INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP DEFAULT NULL, ended_at TIMESTAMP DEFAULT NULL,
        
        -- VERSION 2.0 ADDITIONS: Direct state tracking (No Memory Loss)
        current_batter_id INTEGER DEFAULT NULL,
        current_bowler_id INTEGER DEFAULT NULL,
        current_over INTEGER DEFAULT 1,
        current_ball INTEGER DEFAULT 1,
        innings_runs INTEGER DEFAULT 0,
        innings_wickets INTEGER DEFAULT 0,
        solo_batting_index INTEGER DEFAULT 0,
        solo_bowler_index INTEGER DEFAULT 0
    );
    
    CREATE TABLE IF NOT EXISTS match_players (
        match_id TEXT NOT NULL, telegram_id INTEGER NOT NULL, team TEXT DEFAULT 'solo',
        join_order INTEGER DEFAULT 0, runs INTEGER DEFAULT 0, balls INTEGER DEFAULT 0,
        wickets INTEGER DEFAULT 0, is_out INTEGER DEFAULT 0, is_batting INTEGER DEFAULT 0,
        is_bowling INTEGER DEFAULT 0,
        username TEXT DEFAULT '', display_name TEXT DEFAULT 'Player',
        PRIMARY KEY (match_id, telegram_id)
    );
    
    CREATE TABLE IF NOT EXISTS deliveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT NOT NULL, innings INTEGER NOT NULL,
        over_number INTEGER NOT NULL, ball_number INTEGER NOT NULL, batter_id INTEGER NOT NULL,
        bowler_id INTEGER NOT NULL, batter_choice INTEGER NOT NULL, bowler_choice INTEGER NOT NULL,
        runs INTEGER NOT NULL, is_wicket INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    db.commit()
