import sqlite3
import os

DB_PATH = 'betbot.db'

def migrate():
    if not os.path.exists(DB_PATH):
        print("DB non-existent.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Re-creating tables with TEXT match_id...")

    # Disable foreign keys temporarily
    cursor.execute("PRAGMA foreign_keys = OFF")

    # 1. Migrate 'matches'
    cursor.execute("CREATE TABLE matches_new (match_id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT, status TEXT, winner TEXT, live_msg_id INTEGER, last_score TEXT)")
    cursor.execute("INSERT INTO matches_new SELECT CAST(match_id AS TEXT), home_team, away_team, status, winner, live_msg_id, last_score FROM matches")
    cursor.execute("DROP TABLE matches")
    cursor.execute("ALTER TABLE matches_new RENAME TO matches")

    # 2. Migrate 'bets'
    cursor.execute("""
        CREATE TABLE bets_new (
            bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            match_id TEXT,
            amount REAL,
            prediction TEXT,
            home_score INTEGER,
            away_score INTEGER,
            over_under_type TEXT,
            over_under_line REAL,
            combo_type TEXT,
            combo_line REAL,
            resolved BOOLEAN DEFAULT 0,
            payout REAL DEFAULT 0.0,
            won BOOLEAN,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (match_id) REFERENCES matches (match_id)
        )
    """)
    cursor.execute("""
        INSERT INTO bets_new (bet_id, user_id, match_id, amount, prediction, home_score, away_score, 
                             over_under_type, over_under_line, combo_type, combo_line, resolved, payout, won)
        SELECT bet_id, user_id, CAST(match_id AS TEXT), amount, prediction, home_score, away_score,
               over_under_type, over_under_line, combo_type, combo_line, resolved, payout, won
        FROM bets
    """)
    cursor.execute("DROP TABLE bets")
    cursor.execute("ALTER TABLE bets_new RENAME TO bets")

    # 3. Migrate 'parlay_legs'
    cursor.execute("""
        CREATE TABLE parlay_legs_new (
            leg_id INTEGER PRIMARY KEY AUTOINCREMENT,
            parlay_id INTEGER,
            match_id TEXT,
            prediction TEXT,
            status TEXT DEFAULT 'PENDING',
            FOREIGN KEY (parlay_id) REFERENCES parlays (parlay_id),
            FOREIGN KEY (match_id) REFERENCES matches (match_id)
        )
    """)
    cursor.execute("INSERT INTO parlay_legs_new SELECT leg_id, parlay_id, CAST(match_id AS TEXT), prediction, status FROM parlay_legs")
    cursor.execute("DROP TABLE parlay_legs")
    cursor.execute("ALTER TABLE parlay_legs_new RENAME TO parlay_legs")

    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()
    print("Migration finished successfully.")

if __name__ == "__main__":
    migrate()
