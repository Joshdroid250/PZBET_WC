import sqlite3
import os

DB_PATH = 'betbot.db'

def check():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\n--- PARTIDOS ACTIVOS EN DB ---")
    cursor.execute("SELECT match_id, home_team, away_team, status, winner FROM matches WHERE status != 'FINISHED'")
    matches = cursor.fetchall()
    for m in matches:
        print(f"ID: {m[0]} | {m[1]} vs {m[2]} | Estado: {m[3]} | Ganador: {m[4]}")
        
    print("\n--- APUESTAS SIN RESOLVER ---")
    cursor.execute("SELECT bet_id, match_id, user_id, amount, prediction, resolved FROM bets WHERE resolved = 0")
    bets = cursor.fetchall()
    for b in bets:
        print(f"BetID: {b[0]} | MatchID: {b[1]} | User: {b[2]} | $: {b[3]} | Pred: {b[4]} | Res: {b[5]}")
        
    print("\n--- PARLAYS SIN RESOLVER ---")
    cursor.execute("SELECT parlay_id, user_id, amount, resolved FROM parlays WHERE resolved = 0")
    parlays = cursor.fetchall()
    for p in parlays:
        print(f"ParlayID: {p[0]} | User: {p[1]} | $: {p[2]} | Res: {p[3]}")
    
    conn.close()

if __name__ == "__main__":
    check()
