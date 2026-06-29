import os
import unittest
from unittest.mock import MagicMock

import betting
import database


class TestScoreBetting(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database.DB_PATH = "test_score_betbot.db"
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)
        await database.init_db()

    async def asyncTearDown(self):
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)

    async def test_frozen_multipliers_pay_each_matching_outcome_bet(self):
        user1, user2 = 1, 2
        match_id = 500
        await database.register_user(user1)
        await database.register_user(user2)
        await database.add_or_update_match(match_id, "Home", "Away", "SCHEDULED")

        await database.place_bet(user1, match_id, 100.0, "HOME_TEAM", locked_multiplier=6.0)
        await database.place_bet(user2, match_id, 20.0, "HOME_TEAM", 2, 1, locked_multiplier=5.17)

        mock_bot = MagicMock()
        mock_bot.guilds = []

        await betting.resolve_match_bets(mock_bot, match_id, "HOME_TEAM", 2, 1)

        self.assertAlmostEqual(await database.get_user_balance(user1), 600.0)
        self.assertAlmostEqual(await database.get_user_balance(user2), 183.4)

    async def test_score_fields_do_not_override_outcome_loss(self):
        user1, user2 = 1, 2
        match_id = 502
        await database.register_user(user1)
        await database.register_user(user2)
        await database.add_or_update_match(match_id, "Home", "Away", "SCHEDULED")

        await database.place_bet(user1, match_id, 100.0, "DRAW", locked_multiplier=2.0)
        await database.place_bet(user2, match_id, 20.0, "HOME_TEAM", 2, 1, locked_multiplier=10.0)

        mock_bot = MagicMock()
        mock_bot.guilds = []

        await betting.resolve_match_bets(mock_bot, match_id, "HOME_TEAM", 2, 1)

        self.assertAlmostEqual(await database.get_user_balance(user1), 0.0)
        self.assertAlmostEqual(await database.get_user_balance(user2), 280.0)


if __name__ == "__main__":
    unittest.main()
