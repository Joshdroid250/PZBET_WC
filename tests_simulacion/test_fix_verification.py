import os
import unittest
from unittest.mock import AsyncMock, MagicMock

import api_football
import database
from cogs.betting_cog import Betting


class TestResolutionAndNames(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database.DB_PATH = "test_resolution.db"
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)
        await database.init_db()

        self.bot = MagicMock()
        self.bot.session = AsyncMock()
        self.bot.guilds = []
        self.bot.wait_until_ready = AsyncMock()
        self.bot.get_user = MagicMock(return_value=MagicMock(mention="@testuser"))
        self.bot.fetch_user = AsyncMock(return_value=MagicMock(mention="@testuser"))

        self.channel = AsyncMock()
        self.channel.send.return_value.id = 987654
        self.bot.get_channel = MagicMock(return_value=self.channel)
        self.bot.fetch_channel = AsyncMock(return_value=self.channel)

        os.environ["ANNOUNCEMENT_CHANNEL_ID"] = "123456"
        self.cog = Betting(self.bot)

    async def asyncTearDown(self):
        self.cog.cog_unload()
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)

    async def test_resolution_flow_and_names(self):
        user_id = 999
        match_id = "test_match_1"
        home_team = "Argentina"
        away_team = "Brazil"

        await database.register_user(user_id)
        await database.add_or_update_match(match_id, home_team, away_team, "SCHEDULED")
        await database.place_bet(user_id, match_id, 100.0, "HOME_TEAM", locked_multiplier=10.0)

        api_football.fetch_json = AsyncMock(return_value={
            "matches": [
                {
                    "id": match_id,
                    "homeTeam": {"name": home_team},
                    "awayTeam": {"name": away_team},
                    "status": "IN_PLAY",
                    "utcDate": "2026-06-15T20:00:00Z",
                    "score": {"winner": None, "fullTime": {"home": 1, "away": 0}},
                }
            ]
        })

        await self.cog.match_processor()

        found_names = False
        for call in self.channel.send.call_args_list:
            embed = call.kwargs.get("embed")
            if embed and f"{home_team} vs {away_team}" in embed.title:
                found_names = True
        self.assertTrue(found_names)

        self.channel.send.reset_mock()
        api_football.fetch_json = AsyncMock(return_value={
            "matches": [
                {
                    "id": match_id,
                    "homeTeam": {"name": home_team},
                    "awayTeam": {"name": away_team},
                    "status": "FINISHED",
                    "utcDate": "2026-06-15T20:00:00Z",
                    "score": {"winner": "HOME_TEAM", "fullTime": {"home": 2, "away": 0}},
                }
            ]
        })

        await self.cog.match_processor()

        found_result = False
        for call in self.channel.send.call_args_list:
            embed = call.kwargs.get("embed")
            if embed and "Finalizado:" in embed.title:
                found_result = True
                self.assertIn("(2-0)", embed.description)
        self.assertTrue(found_result)

        self.assertEqual(await database.get_user_balance(user_id), 1000.0)

        self.channel.send.reset_mock()
        await self.cog.match_processor()

        self.assertEqual(self.channel.send.call_count, 0)
        self.assertEqual(await database.get_user_balance(user_id), 1000.0)


if __name__ == "__main__":
    unittest.main()
