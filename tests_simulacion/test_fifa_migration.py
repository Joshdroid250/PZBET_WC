import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import api_football
import database


class TestFifaMigration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = "test_fifa_migration.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        database.DB_PATH = self.db_path
        await database.init_db()
        async with database.aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO users (user_id, balance) VALUES (999, 1000)")
            await db.commit()

    async def asyncTearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    async def test_alphanumeric_id_handling(self):
        match_id = "test_match_123"
        home = "Test Home"
        away = "Test Away"

        await database.add_or_update_match(match_id, home, away, "SCHEDULED")
        await database.place_bet(999, match_id, 50.0, "HOME_TEAM")

        async with database.aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT match_id FROM matches WHERE match_id = ?", (match_id,)) as cursor:
                row = await cursor.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], match_id)

            async with db.execute("SELECT match_id FROM bets WHERE match_id = ?", (match_id,)) as cursor:
                row = await cursor.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], match_id)

    async def test_active_matches_with_names(self):
        match_id = "yh2o5mrvrjl7"
        await database.add_or_update_match(match_id, "Netherlands", "Japan", "IN_PLAY")
        await database.place_bet(999, match_id, 10.0, "DRAW")

        active = await database.get_active_matches_with_names()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0][0], match_id)
        self.assertEqual(active[0][1], "Netherlands")
        self.assertEqual(active[0][2], "Japan")

    @patch("api_football.fetch_json")
    async def test_api_fetch_structure(self, mock_fetch):
        mock_fetch.return_value = {
            "matches": [
                {
                    "id": "yh2o5mrvrjl7",
                    "status": "IN_PLAY",
                    "homeTeam": {"name": "Netherlands"},
                    "awayTeam": {"name": "Japan"},
                    "score": {
                        "fullTime": {"home": 1, "away": 0},
                        "winner": None,
                    },
                }
            ]
        }

        matches = await api_football.fetch_fifa_live_scores()
        self.assertEqual(len(matches["matches"]), 1)
        self.assertEqual(matches["matches"][0]["id"], "yh2o5mrvrjl7")
        self.assertEqual(matches["matches"][0]["score"]["fullTime"]["home"], 1)


if __name__ == "__main__":
    unittest.main()
