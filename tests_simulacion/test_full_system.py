import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
import sys
import os

# Añadir el directorio raíz al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import betting
from cogs.betting_cog import Betting

class TestFullSystemResolution(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Base de datos temporal
        database.DB_PATH = "test_full_resolution.db"
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)
        await database.init_db()
        
        # Mock del bot y canal
        self.bot = MagicMock()
        self.bot.session = AsyncMock()
        self.bot.get_channel = MagicMock()
        self.bot.fetch_channel = AsyncMock()
        self.bot.wait_until_ready = AsyncMock() # Fix: must be awaitable
        self.channel = AsyncMock()
        self.bot.get_channel.return_value = self.channel
        self.bot.fetch_channel.return_value = self.channel
        
        # Mock de usuarios para menciones
        self.bot.get_user = MagicMock(side_effect=lambda id: MagicMock(mention=f"<@{id}>"))
        
        os.environ['ANNOUNCEMENT_CHANNEL_ID'] = '123456'
        self.cog = Betting(self.bot)

    async def asyncTearDown(self):
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)

    async def test_complete_scenario(self):
        """Simula el ciclo de vida de una apuesta individual y un parlay."""
        user_id = 1001
        match_id = "final_match_99"
        home, away = "Spain", "Germany"
        
        await database.register_user(user_id)
        await database.add_or_update_match(match_id, home, away, "SCHEDULED")
        
        # 1. El usuario apuesta $50 a Spain
        await database.place_bet(user_id, match_id, 50.0, "HOME_TEAM")
        
        # 2. El usuario crea un Parlay de 2 piernas ($20)
        # Match A: Spain vs Germany (Home)
        # Match B: France vs Italy (Away)
        match_b_id = "match_b"
        await database.add_or_update_match(match_b_id, "France", "Italy", "SCHEDULED")
        await database.place_parlay(user_id, 20.0, [(match_id, "HOME_TEAM"), (match_b_id, "AWAY_TEAM")])
        
        initial_balance = await database.get_user_balance(user_id) # Debería ser 100 - 50 - 20 = 30
        self.assertEqual(initial_balance, 30.0)

        # 3. Simular que el primer partido termina 1-0 ganando Spain
        import api_football
        api_football.fetch_json = AsyncMock(return_value={
            'matches': [
                {
                    'id': match_id,
                    'homeTeam': {'name': home},
                    'awayTeam': {'name': away},
                    'status': 'FINISHED',
                    'score': {'winner': 'HOME_TEAM', 'fullTime': {'home': 1, 'away': 0}}
                },
                {
                    'id': match_b_id,
                    'homeTeam': {'name': "France"},
                    'awayTeam': {'name': "Italy"},
                    'status': 'SCHEDULED', # Todavía no termina
                    'score': {'winner': None, 'fullTime': {'home': 0, 'away': 0}}
                }
            ]
        })

        print("\n--- Resolviendo Partido 1 (Spain vs Germany 1-0) ---")
        await self.cog.match_processor()

        # Verificar cobro de apuesta individual:
        # User pool: 50. Winning pool: 50. Total effective (inc 150 house): 200.
        # Multiplicador: 200/50 = 4.0x. Pago: 50 * 4.0 = 200.
        # Balance: 30 + 200 = 230.
        balance_after_1 = await database.get_user_balance(user_id)
        self.assertEqual(balance_after_1, 230.0)
        print(f"✅ Apuesta individual pagada. Balance: {balance_after_1}")

        # Verificar que el mensaje de resultado tiene el marcador
        found_score = False
        for call in self.channel.send.call_args_list:
            embed = call.kwargs.get('embed')
            if embed and "Finalizado:" in embed.title and "(1-0)" in embed.description:
                found_score = True
        self.assertTrue(found_score, "El marcador (1-0) no aparece en el anuncio de resultado")

        # 4. Intentar resolver el mismo partido OTRA VEZ (Simular duplicado)
        print("--- Intento duplicado de resolución ---")
        self.channel.send.reset_mock()
        await self.cog.match_processor()
        
        # No debería haber nuevos anuncios ni cambios en el balance
        final_balance_1 = await database.get_user_balance(user_id)
        self.assertEqual(final_balance_1, 230.0)
        self.assertEqual(self.channel.send.call_count, 0)
        print("✅ Candado de duplicidad funcionó: Ni pagos ni mensajes extra.")

        # 5. Resolver el segundo partido para cerrar el Parlay
        api_football.fetch_json = AsyncMock(return_value={
            'matches': [
                {
                    'id': match_id,
                    'homeTeam': {'name': home},
                    'awayTeam': {'name': away},
                    'status': 'FINISHED',
                    'score': {'winner': 'HOME_TEAM', 'fullTime': {'home': 1, 'away': 0}}
                },
                {
                    'id': match_b_id,
                    'homeTeam': {'name': "France"},
                    'awayTeam': {'name': "Italy"},
                    'status': 'FINISHED',
                    'score': {'winner': 'AWAY_TEAM', 'fullTime': {'home': 1, 'away': 2}}
                }
            ]
        })

        print("\n--- Resolviendo Partido 2 (France vs Italy 1-2) ---")
        await self.cog.match_processor()

        # El parlay tenía 2 piernas. Pago: 20 * (2^2) = 80.
        # Balance final: 230 + 80 = 310.
        final_balance = await database.get_user_balance(user_id)
        self.assertEqual(final_balance, 310.0)
        print(f"✅ Parlay pagado. Balance final: {final_balance}")

        # Verificar anuncio de parlay
        found_parlay_win = False
        for call in self.channel.send.call_args_list:
            embed = call.kwargs.get('embed')
            if embed and "PARLAY GANADO" in embed.title:
                found_parlay_win = True
        self.assertTrue(found_parlay_win, "No se anunció la victoria del Parlay.")
        print("✅ Sistema verificado al 100%: Apuestas, Parlays, Marcadores y Seguridad.")

if __name__ == '__main__':
    unittest.main()
