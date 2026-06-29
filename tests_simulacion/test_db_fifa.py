import unittest
import asyncio
import sys
import os
import sqlite3

# Añadir el directorio raíz al path para importar los módulos del bot
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database

class TestFifaDB(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_fifa.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        database.DB_PATH = self.db_path

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_database_schema_and_alphanumeric_ids(self):
        """Verifica que la base de datos acepte IDs alfanuméricos."""
        async def run_test():
            await database.init_db()
            
            # Registrar usuario
            await database.register_user(999)
            
            match_id = "yh2o5mrvrjl7"
            home = "Netherlands"
            away = "Japan"
            
            # 1. Registrar partido con ID alfanumérico
            await database.add_or_update_match(match_id, home, away, "IN_PLAY")
            
            # 2. Realizar apuesta con ID alfanumérico
            await database.place_bet(999, match_id, 10.0, "HOME_TEAM", locked_multiplier=2.0)
            
            # 3. Verificar persistencia
            active = await database.get_active_matches_with_names()
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0][0], match_id)
            self.assertEqual(active[0][1], home)
            self.assertEqual(active[0][2], away)
            
            # 4. Verificar apuesta Kalshi congelada
            db = sqlite3.connect(self.db_path)
            try:
                row = db.execute(
                    "SELECT amount, prediction, locked_multiplier, odds_source FROM bets WHERE match_id = ?",
                    (match_id,),
                ).fetchone()
            finally:
                db.close()
            self.assertEqual(row[0], 10.0)
            self.assertEqual(row[1], "HOME_TEAM")
            self.assertEqual(row[2], 2.0)
            self.assertEqual(row[3], "kalshi")

        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
