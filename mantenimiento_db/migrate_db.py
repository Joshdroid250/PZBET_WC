import sqlite3
import os

DB_PATH = 'betbot.db'

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"La base de datos {DB_PATH} no existe.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Iniciando migración de base de datos...")

    try:
        # Añadir columna live_msg_id si no existe
        cursor.execute("ALTER TABLE matches ADD COLUMN live_msg_id INTEGER")
        print("✅ Columna 'live_msg_id' añadida.")
    except sqlite3.OperationalError:
        print("ℹ️ La columna 'live_msg_id' ya existe.")

    try:
        # Añadir columna last_score si no existe
        cursor.execute("ALTER TABLE matches ADD COLUMN last_score TEXT")
        print("✅ Columna 'last_score' añadida.")
    except sqlite3.OperationalError:
        print("ℹ️ La columna 'last_score' ya existe.")

    conn.commit()
    conn.close()
    print("🚀 Migración completada con éxito.")

if __name__ == "__main__":
    migrate()
