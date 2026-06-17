import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands
import os
import sys
import aiosqlite

# Añadir el directorio actual al path para importar los módulos del proyecto
sys.path.append(os.getcwd())

import database
import api_football
from cogs.betting_cog import Betting

class TestRestoredCommands(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_PATH = 'test_restored.db'

    async def asyncSetUp(self):
        # Limpiar DB antes de cada test si existe
        if os.path.exists(database.DB_PATH):
            try:
                os.remove(database.DB_PATH)
            except:
                pass
        await database.init_db()

        # Mock del bot
        self.bot = AsyncMock(spec=commands.Bot)
        self.bot.session = AsyncMock()
        self.bot.get_channel = MagicMock(return_value=None)
        self.bot.fetch_channel = AsyncMock(return_value=None)
        self.bot.get_user = MagicMock(return_value=None)
        self.bot.fetch_user = AsyncMock(return_value=None)
        self.bot.guilds = []

        # Instanciar el Cog
        self.cog = Betting(self.bot)
        
        # Mock de ctx (Contexto)
        self.ctx = AsyncMock()
        self.ctx.author.id = 12345
        self.ctx.author.name = "TestUser"
        self.ctx.send = AsyncMock()
        self.ctx.defer = AsyncMock()

    async def asyncTearDown(self):
        self.cog.cog_unload()
        # Dar un pequeño respiro para que las conexiones se cierren
        await asyncio.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(database.DB_PATH):
            try:
                os.remove(database.DB_PATH)
            except:
                pass

    async def test_matches_command(self):
        """Verifica que el comando /matches funcione y envíe un embed con vista."""
        api_football.get_upcoming_matches = AsyncMock(return_value=[
            {'id': 'm1', 'homeTeam': {'name': 'Team A'}, 'awayTeam': {'name': 'Team B'}, 'utcDate': '2026-06-15T12:00:00Z'}
        ])
        
        await self.cog.matches.callback(self.cog, self.ctx)
        
        self.ctx.defer.assert_called()
        self.ctx.send.assert_called()
        args, kwargs = self.ctx.send.call_args
        self.assertIsInstance(kwargs['embed'], discord.Embed)
        self.assertIn("Próximos Partidos", kwargs['embed'].title)
        self.assertIsNotNone(kwargs['view'])

    async def test_apuestas_command_empty(self):
        """Verifica /apuestas cuando el usuario no tiene nada."""
        await self.cog.apuestas.callback(self.cog, self.ctx)
        self.ctx.send.assert_called_with("📝 No tienes apuestas individuales activas.", ephemeral=True)

    async def test_parlay_command(self):
        """Verifica que /parlay requiera al menos 2 partidos."""
        api_football.get_upcoming_matches = AsyncMock(return_value=[
            {'id': 'm1', 'homeTeam': {'name': 'Team A'}, 'awayTeam': {'name': 'Team B'}}
        ])
        await self.cog.parlay.callback(self.cog, self.ctx)
        self.ctx.send.assert_called_with("⚽ Se necesitan al menos 2 partidos próximos para crear un parlay.", ephemeral=True)

    async def test_vivo_command(self):
        """Verifica que /vivo muestre partidos en tiempo real."""
        # Corregido: añadir utcDate para evitar KeyError
        api_football.fetch_fifa_live_scores = AsyncMock(return_value={
            'matches': [{
                'id': 'm_live', 
                'homeTeam': {'name': 'Live A'}, 
                'awayTeam': {'name': 'Live B'}, 
                'status': 'IN_PLAY',
                'utcDate': '2026-06-15T12:00:00Z'
            }]
        })
        await self.cog.vivo.callback(self.cog, self.ctx)
        self.ctx.send.assert_called()
        args, kwargs = self.ctx.send.call_args
        self.assertIn("Partidos EN VIVO", kwargs['embed'].title)

    async def test_pozo_command_empty(self):
        """Verifica /pozo cuando no hay partidos activos."""
        await self.cog.pozo.callback(self.cog, self.ctx)
        self.ctx.send.assert_called_with("📊 No hay pozos activos con apuestas en este momento.", ephemeral=True)
        
    async def test_historial_command_empty(self):
        """Verifica /historial vacío."""
        await self.cog.historial.callback(self.cog, self.ctx)
        self.ctx.send.assert_called_with("📜 Aún no tienes un historial de apuestas resueltas.", ephemeral=True)

    async def test_cashout_command(self):
        """Verifica que /cashout envíe el menú inicial."""
        await self.cog.cashout.callback(self.cog, self.ctx)
        self.ctx.send.assert_called()
        args, kwargs = self.ctx.send.call_args
        self.assertIn("Menú de Cashout", args[0])

if __name__ == '__main__':
    unittest.main()
