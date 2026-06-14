import unittest
import asyncio
import os
import database
import betting
from unittest.mock import MagicMock

class TestScoreBetting(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database.DB_PATH = 'test_score_betbot.db'
        if os.path.exists(database.DB_PATH):
            try: os.remove(database.DB_PATH)
            except: pass
        await database.init_db()

    async def asyncTearDown(self):
        if os.path.exists(database.DB_PATH):
            try: os.remove(database.DB_PATH)
            except: pass

    async def test_weighted_payout_distribution(self):
        # User 1: Outcome bet (1X2) - $100 on HOME_TEAM
        # User 2: Score bet - $20 on 2-1 (HOME_TEAM)
        # Injection: $50
        # Total Pool: $100 + $20 + $50 = $170
        
        user1, user2 = 1, 2
        match_id = 500
        await database.register_user(user1)
        await database.register_user(user2)
        await database.add_or_update_match(match_id, "Home", "Away", "SCHEDULED")
        
        await database.place_bet(user1, match_id, 100.0, "HOME_TEAM")
        await database.place_bet(user2, match_id, 20.0, "HOME_TEAM", 2, 1)
        
        mock_bot = MagicMock()
        mock_bot.guilds = []
        
        # Result is 2-1 (HOME_TEAM wins)
        # Weighted Pool: (100 * 1.0) + (20 * 5.0) = 100 + 100 = 200 weighted dollars
        # Payout per weighted dollar: 170 / 200 = 0.85
        # User 1: (100 * 1.0) * 0.85 = 85.0
        # User 2: (20 * 5.0) * 0.85 = 85.0
        
        await betting.resolve_match_bets(mock_bot, match_id, "HOME_TEAM", 2, 1)
        
        balance1 = await database.get_user_balance(user1)
        balance2 = await database.get_user_balance(user2)
        
        # User 1 had 0 after bet. Now 85.0
        self.assertAlmostEqual(balance1, 85.0)
        # User 2 had 80 after bet (100-20). Now 80 + 85.0 = 165.0
        self.assertAlmostEqual(balance2, 165.0)

    async def test_score_miss_outcome_win(self):
        # Result is 1-0. User 2 (bet 2-1) loses score part.
        user1, user2 = 1, 2
        match_id = 501
        await database.register_user(user1)
        await database.register_user(user2)
        await database.add_or_update_match(match_id, "Home", "Away", "SCHEDULED")
        
        await database.place_bet(user1, match_id, 100.0, "HOME_TEAM")
        await database.place_bet(user2, match_id, 20.0, "HOME_TEAM", 2, 1)
        
        mock_bot = MagicMock()
        mock_bot.guilds = []
        
        # Weighted winners: only User 1 (100 * 1.0) = 100.
        # Total pool: 170.
        # User 1 gets all: 170.0
        await betting.resolve_match_bets(mock_bot, match_id, "HOME_TEAM", 1, 0)
        
        self.assertAlmostEqual(await database.get_user_balance(user1), 170.0)
        self.assertAlmostEqual(await database.get_user_balance(user2), 80.0) # Lost his 20

    async def test_only_score_wins(self):
        # Someone bets on a draw outcome, someone else bets on 2-1 score.
        # Result is 2-1.
        user1, user2 = 1, 2
        match_id = 502
        await database.register_user(user1)
        await database.register_user(user2)
        await database.add_or_update_match(match_id, "Home", "Away", "SCHEDULED")
        
        await database.place_bet(user1, match_id, 100.0, "DRAW")
        await database.place_bet(user2, match_id, 20.0, "HOME_TEAM", 2, 1)
        
        mock_bot = MagicMock()
        mock_bot.guilds = []
        
        # Winner is HOME_TEAM 2-1.
        # User 1 loses.
        # User 2 wins Score part. Weighted pool = 20 * 5.0 = 100.
        # Total pool = 100 + 20 + 50 = 170.
        # User 2 gets all 170.
        await betting.resolve_match_bets(mock_bot, match_id, "HOME_TEAM", 2, 1)
        
        self.assertAlmostEqual(await database.get_user_balance(user1), 0.0)
        self.assertAlmostEqual(await database.get_user_balance(user2), 80.0 + 170.0)

if __name__ == '__main__':
    unittest.main()
