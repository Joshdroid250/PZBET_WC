import unittest
import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

# Añadir el directorio raíz al path para importar los módulos del bot
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import api_football
import database

class TestFifaMigration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Usar una base de datos en memoria para pruebas
        self.db_path = ":memory:"
        # Mockear el path de la DB en el módulo database ANTES de cualquier operación
        with patch('database.DB_PATH', self.db_path):
            await database.init_db()
            
            # Insertar un usuario de prueba
            async with database.aiosqlite.connect(self.db_path) as db:
                await db.execute("INSERT INTO users (user_id, balance) VALUES (999, 1000)")
                await db.commit()

    @patch('database.DB_PATH', ':memory:')
    async def test_alphanumeric_id_handling(self):
        # Reinicializar para cada test ya que :memory: es volátil
        await database.init_db()
        async with database.aiosqlite.connect(':memory:') as db:
            await db.execute("INSERT INTO users (user_id, balance) VALUES (999, 1000)")
            await db.commit()
        
        match_id = "test_match_123"
        home = "Test Home"
        away = "Test Away"
        
        # 1. Registrar partido
        await database.add_or_update_match(match_id, home, away, "SCHEDULED")
        
        # 2. Realizar apuesta
        await database.place_bet(999, match_id, 50.0, "HOME_TEAM")
        
        # 3. Verificar que se guardó correctamente como texto
        async with database.aiosqlite.connect(':memory:') as db:
            async with db.execute("SELECT match_id FROM matches WHERE match_id = ?", (match_id,)) as cursor:
                row = await cursor.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], match_id)
            
            async with db.execute("SELECT match_id FROM bets WHERE match_id = ?", (match_id,)) as cursor:
                row = await cursor.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], match_id)

    async def test_active_matches_with_names(self):
        """Verifica que get_active_matches_with_names devuelva los datos correctos."""
        match_id = "yh2o5mrvrjl7"
        await database.add_or_update_match(match_id, "Netherlands", "Japan", "IN_PLAY")
        await database.place_bet(999, match_id, 10.0, "DRAW")
        
        active = await database.get_active_matches_with_names()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0][0], match_id)
        self.assertEqual(active[0][1], "Netherlands")
        self.assertEqual(active[0][2], "Japan")

    @patch('api_football.fetch_json')
    async def test_api_fetch_structure(self, mock_fetch):
        """Simula una respuesta de la FIFA API y verifica que el módulo la procese."""
        mock_response = {
            "matches": [
                {
                    "id": "yh2o5mrvrjl7",
                    "status": "IN_PLAY",
                    "homeTeam": {"name": "Netherlands"},
                    "awayTeam": {"name": "Japan"},
                    "score": {
                        "fullTime": {"home": 1, "away": 0},
                        "winner": None
                    }
                }
            ]
        }
        mock_fetch.return_value = mock_response
        
        matches = await api_football.fetch_fifa_live_scores()
        self.assertEqual(len(matches['matches']), 1)
        self.assertEqual(matches['matches'][0]['id'], "yh2o5mrvrjl7")
        self.assertEqual(matches['matches'][0]['score']['fullTime']['home'], 1)

if __name__ == '__main__':
    unittest.main()
