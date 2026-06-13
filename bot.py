import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
import database

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('BOT_PREFIX', '!')

class BetBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=PREFIX, intents=intents)

    async def setup_hook(self):
        # Inicializar Base de Datos
        await database.init_db()
        print("Base de datos inicializada.")

        # Cargar Cogs
        initial_extensions = [
            'cogs.general',
            'cogs.betting_cog',
        ]

        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                print(f"Extensión {extension} cargada.")
            except Exception as e:
                print(f"Error al cargar {extension}: {e}")

    async def on_ready(self):
        print(f'Conectado como {self.user} (ID: {self.user.id})')
        print('------')

async def main():
    bot = BetBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
