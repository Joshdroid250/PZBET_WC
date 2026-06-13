import unittest
import asyncio
import os
import database
import betting
from datetime import datetime

class TestBetBot(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Usar una base de datos temporal para tests
        database.DB_PATH = 'test_betbot.db'
        if os.path.exists(database.DB_PATH):
            try: os.remove(database.DB_PATH)
            except: pass
        await database.init_db()

    async def asyncTearDown(self):
        if os.path.exists(database.DB_PATH):
            try: os.remove(database.DB_PATH)
            except: pass

    async def test_user_registration_and_balance(self):
        user_id = 12345
        await database.register_user(user_id)
        balance = await database.get_user_balance(user_id)
        self.assertEqual(balance, 100.0)

    async def test_place_bet_deducts_balance(self):
        user_id = 12345
        match_id = 999
        await database.register_user(user_id)
        await database.add_or_update_match(match_id, "Home Team", "Away Team", "SCHEDULED")
        await database.place_bet(user_id, match_id, 50.0, "HOME_TEAM")
        
        balance = await database.get_user_balance(user_id)
        self.assertEqual(balance, 50.0)
        
        bets = await database.get_active_bets_for_match(match_id)
        self.assertEqual(len(bets), 1)
        self.assertEqual(bets[0][1], 50.0)

    async def test_resolve_match_winners(self):
        # Inyección de la casa es 50.0 por defecto
        user1, user2 = 1, 2
        match_id = 101
        await database.register_user(user1)
        await database.register_user(user2)
        await database.add_or_update_match(match_id, "Team A", "Team B", "SCHEDULED")
        
        await database.place_bet(user1, match_id, 60.0, "HOME_TEAM") # Balance: 40
        await database.place_bet(user2, match_id, 40.0, "AWAY_TEAM") # Balance: 60
        
        # Mock bot object for role updates
        from unittest.mock import MagicMock
        mock_bot = MagicMock()
        mock_bot.guilds = []
        
        # Pool Total = 60 + 40 + 50 (House) = 150.0
        # Winner is HOME_TEAM. User 1 should get all 150.0.
        await betting.resolve_match_bets(mock_bot, match_id, "HOME_TEAM")
        
        balance1 = await database.get_user_balance(user1)
        balance2 = await database.get_user_balance(user2)
        
        self.assertEqual(balance1, 190.0)
        self.assertEqual(balance2, 60.0)

    async def test_no_refund_if_no_winners(self):
        # Ahora el dinero se queda en el pozo si nadie gana
        user1 = 1
        match_id = 102
        await database.register_user(user1)
        await database.add_or_update_match(match_id, "Team A", "Team B", "SCHEDULED")
        await database.place_bet(user1, match_id, 50.0, "HOME_TEAM") # Balance: 50
        
        from unittest.mock import MagicMock
        mock_bot = MagicMock()
        mock_bot.guilds = []
        
        await betting.resolve_match_bets(mock_bot, match_id, "AWAY_TEAM")
        
        balance = await database.get_user_balance(user1)
        self.assertEqual(balance, 50.0) # Perdido

    async def test_daily_bonus_persistence(self):
        user_id = 12345
        await database.register_user(user_id)
        # Forzar balance a 0
        async with database.aiosqlite.connect(database.DB_PATH) as db:
            await db.execute('UPDATE users SET balance = 0.0 WHERE user_id = ?', (user_id,))
            await db.commit()
            
        # Dar bono
        await database.give_daily_bonus(15.0)
        balance = await database.get_user_balance(user_id)
        self.assertEqual(balance, 15.0)

    async def test_parlay_resolution(self):
        user_id = 12345
        await database.register_user(user_id) # 100.0
        
        match1, match2 = 201, 202
        await database.add_or_update_match(match1, "T1", "T2", "SCHEDULED")
        await database.add_or_update_match(match2, "T3", "T4", "SCHEDULED")
        
        # Crear parlay de 20.0
        legs = [(match1, "HOME_TEAM"), (match2, "AWAY_TEAM")]
        await database.place_parlay(user_id, 20.0, legs)
        
        # Resolver match 1: GANA
        await database.update_parlay_leg_status(1, match1, "WON")
        
        # Verificar que no se ha resuelto el parlay aún
        async with database.aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute('SELECT resolved FROM parlays WHERE parlay_id = 1') as cursor:
                res = await cursor.fetchone()
                self.assertEqual(res[0], 0)
        
        # Resolver match 2: GANA
        # Simulamos la lógica de resolución que está en betting_cog.py pero aquí testeamos db y cálculo
        await database.update_parlay_leg_status(1, match2, "WON")
        
        # Multiplicador simple: monto * 2^piernas = 20 * 4 = 80.0
        await database.resolve_parlay(1, 80.0, True)
        
        balance = await database.get_user_balance(user_id)
        self.assertEqual(balance, 80.0 + 80.0) # 80 restates + 80 ganado

    async def test_parlay_loss(self):
        user_id = 12345
        await database.register_user(user_id)
        match1, match2 = 301, 302
        await database.add_or_update_match(match1, "T1", "T2", "SCHEDULED")
        await database.add_or_update_match(match2, "T3", "T4", "SCHEDULED")
        
        legs = [(match1, "HOME_TEAM"), (match2, "AWAY_TEAM")]
        await database.place_parlay(user_id, 10.0, legs)
        
        # Match 1 PIERDE
        await database.update_parlay_leg_status(1, match1, "LOST")
        await database.resolve_parlay(1, 0.0, False)
        
        balance = await database.get_user_balance(user_id)
        self.assertEqual(balance, 90.0) # Solo perdió los 10

if __name__ == '__main__':
    unittest.main()
