import discord
from discord.ext import commands
import os
import asyncio
import aiohttp
from dotenv import load_dotenv
import database

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('BOT_PREFIX', '!')

class BetBot(commands.Bot):
    def __init__(self):
        # OPTIMIZACIÓN: Desactivar intents pesados (members) para ahorrar RAM en Railway.
        # Si no necesitas rastrear a todos los miembros 24/7, dejar esto en False.
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = False # Desactivado para ahorrar memoria
        
        # Desactivar caché de miembros explícitamente para mayor ahorro
        super().__init__(
            command_prefix=PREFIX, 
            intents=intents,
            chunk_guilds_at_startup=False
        )
        self.session = None

    async def setup_hook(self):
        # OPTIMIZACIÓN: Sesión única de aiohttp para todas las peticiones (ahorra CPU y RAM)
        self.session = aiohttp.ClientSession()
        
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

        # --- LIMPIEZA AUTOMÁTICA DE DUPLICADOS ---
        # Al reiniciar, el bot se sincronizará globalmente una sola vez.
        # Esto es lo que Discord recomienda para producción.
        print("Sincronizando comandos globales...")
        try:
            await self.tree.sync()
            print("Comandos globales sincronizados.")
        except Exception as e:
            print(f"Error en sync global: {e}")

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self):
        await self.wait_until_ready()
        print(f'Conectado como {self.user.name} (ID: {self.user.id})')
        print('------')

    async def on_message(self, message):
        # Ignorar mensajes de otros bots
        if message.author.bot:
            return

        # Mecanismo de emergencia mejorado: Sincronización limpia
        if self.user.mentioned_in(message) and "sync" in message.content.lower():
            if message.author.guild_permissions.administrator:
                if "clear" in message.content.lower():
                    await message.channel.send(f"🧹 **Limpiando comandos locales** en {message.guild.name}...")
                    self.tree.clear_commands(guild=message.guild)
                    await self.tree.sync(guild=message.guild)
                    await message.channel.send("✅ Limpieza completada. Usa solo los globales.")
                else:
                    await message.channel.send(f"🔄 **Sincronizando GLOBALMENTE**...")
                    try:
                        synced = await self.tree.sync()
                        await message.channel.send(f"✅ ¡Éxito! {len(synced)} comandos sincronizados globalmente.")
                    except Exception as e:
                        await message.channel.send(f"❌ Error: {e}")
            else:
                await message.channel.send("❌ Solo administradores pueden usar la sincronización.")
            return

        await self.process_commands(message)

    @commands.hybrid_command(name='sync')
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx, scope: str = "global"):
        """Sincroniza los comandos de barra. Uso: !sync global o !sync clear."""
        if scope == "clear":
            await ctx.send(f"🧹 Limpiando comandos locales en **{ctx.guild.name}**...", ephemeral=True)
            try:
                self.tree.clear_commands(guild=ctx.guild)
                await self.tree.sync(guild=ctx.guild)
                await ctx.send("✅ Comandos locales eliminados. Reinicia tu Discord si sigues viendo duplicados.", ephemeral=True)
            except Exception as e:
                await ctx.send(f"❌ Error al limpiar: `{e}`", ephemeral=True)
        else:
            await ctx.send("⏳ Sincronizando comandos GLOBALMENTE...", ephemeral=True)
            try:
                synced = await self.tree.sync()
                await ctx.send(f"✅ Sincronización GLOBAL completa. {len(synced)} comandos registrados.", ephemeral=True)
            except Exception as e:
                await ctx.send(f"❌ Error global: `{e}`", ephemeral=True)

async def main():
    bot = BetBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
