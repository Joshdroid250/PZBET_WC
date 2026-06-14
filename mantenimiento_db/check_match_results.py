import sqlite3
import os

DB_PATH = 'betbot.db'

def check_results(match_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print(f"\n--- RESULTADOS PARTIDO {match_id} ---")
    cursor.execute("SELECT home_team, away_team, status, winner FROM matches WHERE match_id = ?", (match_id,))
    match = cursor.fetchone()
    if match:
        print(f"Partido: {match[0]} vs {match[1]} | Estado: {match[2]} | Ganador: {match[3]}")
    
    print("\n--- APUESTAS RESOLVIDAS ---")
    cursor.execute("""
        SELECT b.bet_id, b.user_id, b.amount, b.prediction, b.payout, b.won, 
               b.home_score, b.away_score, b.over_under_line, b.combo_line 
        FROM bets b 
        WHERE b.match_id = ?
    """, (match_id,))
    bets = cursor.fetchall()
    for b in bets:
        label = b[3]
        if b[6] is not None: label = f"Exacto {b[6]}-{b[7]}"
        elif b[8] is not None: label = f"OU +{b[8]}"
        elif b[9] is not None: label = f"Combo +{b[9]}"
        
        status = "GANÓ" if b[5] else "PERDIÓ"
        print(f"BetID: {b[0]} | User: {b[1]} | Apostó: ${b[2]} a {label} | Payout: ${b[4]} | {status}")
    
    conn.close()

if __name__ == "__main__":
    check_results(537351)
