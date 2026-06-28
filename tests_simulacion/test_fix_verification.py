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

class TestResolutionAndNames(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Usar una base de datos temporal para el test
        database.DB_PATH = "test_resolution.db"
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)
        await database.init_db()
        
        # Mock del bot
        self.bot = MagicMock()
        self.bot.session = AsyncMock()
        self.bot.get_channel = MagicMock()
        self.bot.fetch_channel = AsyncMock()
        
        # Mock del canal de anuncios
        self.channel = AsyncMock()
        self.bot.get_channel.return_value = self.channel
        self.bot.fetch_channel.return_value = self.channel
        
        os.environ['ANNOUNCEMENT_CHANNEL_ID'] = '123456'
        
        self.cog = Betting(self.bot)

    async def asyncTearDown(self):
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)

    async def test_resolution_flow_and_names(self):
        """Verifica que los nombres de los equipos y la resolución (sin duplicados) funcionen."""
        user_id = 999
        match_id = "test_match_1"
        home_team = "Argentina"
        away_team = "Brazil"
        
        await database.register_user(user_id)
        await database.add_or_update_match(match_id, home_team, away_team, "SCHEDULED")
        await database.place_bet(user_id, match_id, 100.0, "HOME_TEAM")
        
        # 1. Simular actualización en vivo y verificar nombres
        # En el bot real, esto pasa en check_matches o fast_score_update
        import discord
        
        # Mock de api_football para devolver detalles del partido
        import api_football
        api_football.get_match_details = AsyncMock(return_value={
            'id': match_id,
            'homeTeam': {'name': home_team},
            'awayTeam': {'name': away_team},
            'status': 'IN_PLAY',
            'utcDate': '2026-06-15T20:00:00Z',
            'score': {'fullTime': {'home': 1, 'away': 0}}
        })
        api_football.fetch_fifa_live_scores = AsyncMock(return_value={'matches': []})
        
        # Ejecutar una vez el check_matches (simplificado)
        # Forzamos los datos para que entre en la lógica de envío de mensaje
        await self.cog.check_matches()
        
        # Verificar que el mensaje enviado NO contenga "home vs away"
        calls = self.channel.send.call_args_list
        found_names = False
        for call in calls:
            embed = call.kwargs.get('embed')
            if embed and f"{home_team} vs {away_team}" in embed.title:
                found_names = True
                print(f"✅ Título del embed correcto: {embed.title}")
        
        self.assertTrue(found_names, "No se encontró el mensaje EN VIVO con los nombres de los equipos.")

        # 2. Simular resolución y verificar bloqueo de duplicidad
        api_football.get_match_details = AsyncMock(return_value={
            'id': match_id,
            'homeTeam': {'name': home_team},
            'awayTeam': {'name': away_team},
            'status': 'FINISHED',
            'utcDate': '2026-06-15T20:00:00Z',
            'score': {'winner': 'HOME_TEAM', 'fullTime': {'home': 2, 'away': 0}}
        })
        
        # Mock de fetch_user para el resumen de cobros
        self.bot.get_user = MagicMock(return_value=MagicMock(mention="@testuser"))

        # Primera resolución
        print("--- Intento 1 de resolución ---")
        await self.cog.check_matches()
        
        # Verificar que se envió el anuncio de resultado
        found_result = False
        for call in self.channel.send.call_args_list:
            embed = call.kwargs.get('embed')
            if embed and "Resultado:" in embed.title:
                found_result = True
                self.assertIn("(2-0)", embed.description, "El marcador no aparece en el resultado")
                print(f"✅ Anuncio de resultado enviado con marcador: {embed.description}")
        
        self.assertTrue(found_result)
        
        # Verificar balance con multiplicador capado a 10x.
        new_balance = await database.get_user_balance(user_id)
        self.assertEqual(new_balance, 1000.0)
        print(f"✅ Balance tras resolución 1: {new_balance}")

        # Segunda resolución (debería ser bloqueada por el candado)
        print("--- Intento 2 de resolución (duplicado) ---")
        self.channel.send.reset_mock()
        await self.cog.check_matches()
        
        # No debería haber nuevos mensajes de resultado
        found_duplicate = False
        for call in self.channel.send.call_args_list:
            embed = call.kwargs.get('embed')
            if embed and "Resultado:" in embed.title:
                found_duplicate = True
        
        self.assertFalse(found_duplicate, "Se detectó un anuncio duplicado!")
        
        # El balance no debería haber cambiado
        final_balance = await database.get_user_balance(user_id)
        self.assertEqual(final_balance, 1000.0)
        print(f"✅ Balance tras intento 2: {final_balance} (Sin cambios, OK)")

if __name__ == '__main__':
    unittest.main()
