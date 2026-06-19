import aiosqlite
import os

# Ruta persistente para Railway o local
MOUNT_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
if MOUNT_PATH != '.' and not os.path.exists(MOUNT_PATH):
    os.makedirs(MOUNT_PATH, exist_ok=True)

DB_PATH = os.path.join(MOUNT_PATH, 'betbot.db')

def round_money(value):
    return round(float(value), 2)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 100.0
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                match_id TEXT PRIMARY KEY,
                home_team TEXT,
                away_team TEXT,
                status TEXT,
                winner TEXT,
                live_msg_id INTEGER,
                last_score TEXT
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bets (
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
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS parlays (
                parlay_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                resolved BOOLEAN DEFAULT 0,
                payout REAL DEFAULT 0.0,
                won BOOLEAN,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS parlay_legs (
                leg_id INTEGER PRIMARY KEY AUTOINCREMENT,
                parlay_id INTEGER,
                match_id TEXT,
                prediction TEXT,
                status TEXT DEFAULT 'PENDING', -- PENDING, WON, LOST
                FOREIGN KEY (parlay_id) REFERENCES parlays (parlay_id),
                FOREIGN KEY (match_id) REFERENCES matches (match_id)
            )
        ''')
        await db.commit()

async def place_parlay(user_id, amount, legs):
    """legs is a list of (match_id, prediction)"""
    amount = round_money(amount)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = ROUND(balance - ?, 2) WHERE user_id = ?', (amount, user_id))
        async with db.execute('INSERT INTO parlays (user_id, amount) VALUES (?, ?)', (user_id, amount)) as cursor:
            parlay_id = cursor.lastrowid
            for match_id, prediction in legs:
                await db.execute('INSERT INTO parlay_legs (parlay_id, match_id, prediction) VALUES (?, ?, ?)', 
                                (parlay_id, str(match_id), prediction))
        await db.commit()
        return parlay_id

async def get_all_active_match_ids():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT DISTINCT match_id FROM bets WHERE resolved = 0') as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def get_active_matches_with_names():
    """Returns a list of (id, home, away) for all matches with active bets OR parlay legs."""
    async with aiosqlite.connect(DB_PATH) as db:
        query = '''
            SELECT DISTINCT m.match_id, m.home_team, m.away_team 
            FROM matches m 
            LEFT JOIN bets b ON m.match_id = b.match_id AND b.resolved = 0
            LEFT JOIN parlay_legs pl ON m.match_id = pl.match_id AND pl.status = 'PENDING'
            WHERE b.bet_id IS NOT NULL OR pl.leg_id IS NOT NULL
        '''
        async with db.execute(query) as cursor:
            return await cursor.fetchall()


async def get_active_parlay_ids():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT parlay_id FROM parlays WHERE resolved = 0') as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def get_parlay_legs(parlay_id):
    async with aiosqlite.connect(DB_PATH) as db:
        query = 'SELECT match_id, prediction, status FROM parlay_legs WHERE parlay_id = ?'
        async with db.execute(query, (parlay_id,)) as cursor:
            return await cursor.fetchall()

async def update_parlay_leg_status(parlay_id, match_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE parlay_legs SET status = ? WHERE parlay_id = ? AND match_id = ?', 
                        (status, parlay_id, str(match_id)))
        await db.commit()

async def resolve_parlay(parlay_id, payout, won):
    payout = round_money(payout)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE parlays SET resolved = 1, payout = ?, won = ? WHERE parlay_id = ?', 
                        (payout, won, parlay_id))
        if won:
            # Get user_id first
            async with db.execute('SELECT user_id FROM parlays WHERE parlay_id = ?', (parlay_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    user_id = row[0]
                    await db.execute('UPDATE users SET balance = ROUND(balance + ?, 2) WHERE user_id = ?', (payout, user_id))
        await db.commit()

async def get_user_active_parlays(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        query = 'SELECT parlay_id, amount FROM parlays WHERE user_id = ? AND resolved = 0'
        async with db.execute(query, (user_id,)) as cursor:
            parlays = await cursor.fetchall()
            result = []
            for p_id, amount in parlays:
                legs_query = '''
                    SELECT m.home_team, m.away_team, l.prediction, l.status 
                    FROM parlay_legs l
                    JOIN matches m ON l.match_id = m.match_id
                    WHERE l.parlay_id = ?
                '''
                async with db.execute(legs_query, (p_id,)) as cursor_legs:
                    legs = await cursor_legs.fetchall()
                    result.append({'id': p_id, 'amount': amount, 'legs': legs})
            return result

async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
        await db.commit()

async def get_all_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT key, value FROM settings') as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

async def get_user_balance(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def register_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 100.0)', (user_id,))
        await db.commit()

async def update_balance(user_id, amount):
    amount = round_money(amount)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = ROUND(balance + ?, 2) WHERE user_id = ?', (amount, user_id))
        await db.commit()

async def place_bet(user_id, match_id, amount, prediction):
    amount = round_money(amount)
    async with aiosqlite.connect(DB_PATH) as db:
        # Deduct balance first
        await db.execute('UPDATE users SET balance = ROUND(balance - ?, 2) WHERE user_id = ?', (amount, user_id))
        # Insert bet
        await db.execute('''
            INSERT INTO bets (user_id, match_id, amount, prediction)
            VALUES (?, ?, ?, ?)
        ''', (user_id, match_id, amount, prediction))
        await db.commit()

async def add_or_update_match(match_id, home_team, away_team, status, winner=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO matches (match_id, home_team, away_team, status, winner)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                status = excluded.status,
                winner = excluded.winner
        ''', (match_id, home_team, away_team, status, winner))
        await db.commit()

async def get_active_bets_for_match(match_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id, amount, prediction FROM bets WHERE match_id = ? AND resolved = 0', (str(match_id),)) as cursor:
            return await cursor.fetchall()

async def get_user_active_bets(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        # Join with matches table to get team names
        query = '''
            SELECT m.home_team, m.away_team, b.amount, b.prediction, m.match_id
            FROM bets b
            JOIN matches m ON b.match_id = m.match_id
            WHERE b.user_id = ? AND b.resolved = 0
        '''
        async with db.execute(query, (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_bet_amount(user_id, match_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT amount FROM bets WHERE user_id = ? AND match_id = ? AND resolved = 0', (user_id, str(match_id))) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def remove_bet(user_id, match_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM bets WHERE user_id = ? AND match_id = ? AND resolved = 0', (user_id, str(match_id)))
        await db.commit()

async def remove_parlay(user_id, parlay_id):
    """Deletes a parlay and its legs. Payout/Refund logic handled in caller."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM parlay_legs WHERE parlay_id = ?', (parlay_id,))
        await db.execute('DELETE FROM parlays WHERE parlay_id = ? AND user_id = ? AND resolved = 0', (parlay_id, user_id))
        await db.commit()

async def mark_bet_resolved(match_id, user_id, payout, won):
    payout = round_money(payout)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            UPDATE bets 
            SET resolved = 1, payout = ?, won = ? 
            WHERE match_id = ? AND user_id = ? AND resolved = 0
        ''', (payout, won, str(match_id), user_id))
        await db.commit()

async def mark_all_bets_resolved_empty(match_id):
    """Marks bets as resolved with 0 payout if match ended but logic didn't catch specific winners (fallback)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE bets SET resolved = 1 WHERE match_id = ? AND resolved = 0', (str(match_id),))
        await db.commit()

async def get_all_active_match_ids():
    """Returns a list of match_ids that have unresolved bets."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT DISTINCT match_id FROM bets WHERE resolved = 0') as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def get_user_history(user_id, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        query = '''
            SELECT m.home_team, m.away_team, b.amount, b.prediction, b.payout, b.won, m.winner
            FROM bets b
            JOIN matches m ON b.match_id = m.match_id
            WHERE b.user_id = ? AND b.resolved = 1
            ORDER BY b.bet_id DESC
            LIMIT ?
        '''
        async with db.execute(query, (user_id, limit)) as cursor:
            return await cursor.fetchall()

async def get_global_history(limit=15):
    """Returns the most recent resolved bets for all users."""
    async with aiosqlite.connect(DB_PATH) as db:
        query = '''
            SELECT u.user_id, m.home_team, m.away_team, b.amount, b.prediction, b.payout, b.won, m.winner
            FROM bets b
            JOIN matches m ON b.match_id = m.match_id
            JOIN users u ON b.user_id = u.user_id
            WHERE b.resolved = 1
            ORDER BY b.bet_id DESC
            LIMIT ?
        '''
        async with db.execute(query, (limit,)) as cursor:
            return await cursor.fetchall()

async def give_daily_bonus(amount, threshold=0.0):
    """Gives a bonus to all users whose balance is below or equal to the threshold."""
    amount = round_money(amount)
    threshold = round_money(threshold)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = ROUND(balance + ?, 2) WHERE ROUND(balance, 2) <= ?', (amount, threshold))
        await db.commit()

async def normalize_money_values():
    """Rounds stored monetary values to two decimals without deleting rows."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = ROUND(balance, 2)')
        await db.execute('UPDATE bets SET payout = ROUND(payout, 2)')
        await db.execute('UPDATE parlays SET payout = ROUND(payout, 2)')
        await db.commit()

async def get_match_pools(match_id):
    """Returns total pool and a dict of pools per prediction."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT prediction, SUM(amount) FROM bets WHERE match_id = ? AND resolved = 0 GROUP BY prediction', (match_id,)) as cursor:
            rows = await cursor.fetchall()
            pools = {row[0]: row[1] for row in rows}
            total = sum(pools.values())
            return total, pools

async def get_top_users(limit=10):
    """Returns the top users sorted by balance."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT ?', (limit,)) as cursor:
            return await cursor.fetchall()

async def get_live_msg_info(match_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT live_msg_id, last_score FROM matches WHERE match_id = ?', (str(match_id),)) as cursor:
            return await cursor.fetchone()

async def update_live_msg_info(match_id, msg_id, score):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE matches SET live_msg_id = ?, last_score = ? WHERE match_id = ?', (msg_id, score, str(match_id)))
        await db.commit()

async def get_match_by_id(match_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT match_id, home_team, away_team, status FROM matches WHERE match_id = ?', (str(match_id),)) as cursor:
            return await cursor.fetchone()

async def is_match_resolved(match_id):
    """Verifica si un partido ya ha sido marcado como FINISHED en la tabla matches."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT status FROM matches WHERE match_id = ?', (str(match_id),)) as cursor:
            row = await cursor.fetchone()
            return row and row[0] == 'FINISHED'
