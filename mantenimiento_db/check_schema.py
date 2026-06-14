import sqlite3
import os

DB_PATH = 'betbot.db'

def check_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    tables = ['matches', 'bets', 'parlays', 'parlay_legs']
    for table in tables:
        print(f"\n--- SCHEMA FOR {table} ---")
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        for col in columns:
            print(f"ID: {col[0]} | Name: {col[1]} | Type: {col[2]} | PK: {col[5]}")
            
    conn.close()

if __name__ == "__main__":
    check_schema()
