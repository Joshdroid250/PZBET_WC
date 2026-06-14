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
        intents.members = True # REQUERIDO para el sistema de roles
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
        await self.wait_until_ready()
        print(f'Conectado como {self.user.name} (ID: {self.user.id})')
        print('------')

    async def on_message(self, message):
        # Ignorar mensajes de otros bots
        if message.author.bot:
            return

        # Mecanismo de emergencia: Sincronización por mención
        # Si mencionas al bot y escribes "sync", se sincronizará localmente
        if self.user.mentioned_in(message) and "sync" in message.content.lower():
            if message.author.guild_permissions.administrator:
                await message.channel.send(f"🔄 **Sincronización de emergencia detectada.** Sincronizando en {message.guild.name}...")
                try:
                    self.tree.copy_global_to(guild=message.guild)
                    synced = await self.tree.sync(guild=message.guild)
                    await message.channel.send(f"✅ ¡Éxito! {len(synced)} comandos sincronizados localmente.")
                except Exception as e:
                    await message.channel.send(f"❌ Error: {e}")
            else:
                await message.channel.send("❌ Solo administradores pueden usar la sincronización.")
            return # Detener procesamiento para evitar que intente ejecutarlo como comando prefix también

        # Procesar otros comandos con prefijo (!) normalmente
        await self.process_commands(message)

    @commands.command(name='sync')
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx, scope: str = "guild"):
        """Sincroniza los comandos de barra. Uso: !sync guild (recomendado) o !sync global."""
        if scope == "guild":
            await ctx.send(f"⏳ Sincronizando comandos localmente en **{ctx.guild.name}**...")
            try:
                self.tree.copy_global_to(guild=ctx.guild)
                synced = await self.tree.sync(guild=ctx.guild)
                await ctx.send(f"✅ Sincronización LOCAL completa. {len(synced)} comandos listos para usar en este servidor.")
                print(f"Sync local exitoso en {ctx.guild.name} ({ctx.guild.id})")
            except Exception as e:
                await ctx.send(f"❌ Error local: `{e}`")
        else:
            await ctx.send("⏳ Sincronizando comandos GLOBALMENTE (puede tardar hasta 1h)...")
            try:
                synced = await self.tree.sync()
                await ctx.send(f"✅ Sincronización GLOBAL completa. {len(synced)} comandos registrados en Discord.")
            except Exception as e:
                await ctx.send(f"❌ Error global: `{e}`")

async def main():
    bot = BetBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
