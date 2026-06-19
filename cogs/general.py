import discord
from discord.ext import commands, tasks
import database
from datetime import datetime

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_bonus.start()

    def cog_unload(self):
        self.daily_bonus.cancel()

    @tasks.loop(minutes=30)
    async def daily_bonus(self):
        """Regala 15 monedas diariamente a los usuarios con balance 0, persistente a reinicios."""
        today = datetime.now().strftime("%Y-%m-%d")
        last_run = await database.get_setting("last_bonus_date")
        
        if last_run != today:
            print(f"🎁 Distribuyendo bono diario ({today}) a usuarios con balance 0...")
            await database.give_daily_bonus(15.0)
            await database.set_setting("last_bonus_date", today)

    @daily_bonus.before_loop
    async def before_daily_bonus(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name='join')
    async def join(self, ctx):
        """Regístrate en el bot y recibe 100 monedas de regalo."""
        user_id = ctx.author.id
        balance = await database.get_user_balance(user_id)
        if balance is not None:
            embed = discord.Embed(
                title="Ya estás registrado",
                description=f"{ctx.author.mention}, tu saldo actual es de **${balance:.2f}**.",
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await database.register_user(user_id)
            embed = discord.Embed(
                title="¡Bienvenido al Bot de Apuestas! 🏆",
                description=f"Hola {ctx.author.mention}, te hemos asignado **$100.00** monedas fakes para que empieces a apostar.",
                color=discord.Color.green()
            )
            embed.set_footer(text="Usa /matches para ver los partidos disponibles.")
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='balance')
    async def balance(self, ctx):
        """Consulta tu saldo actual."""
        user_id = ctx.author.id
        balance = await database.get_user_balance(user_id)
        if balance is not None:
            embed = discord.Embed(
                title="💰 Tu Saldo",
                description=f"{ctx.author.mention}, tienes **${balance:.2f}** monedas.",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="No registrado",
                description="No tienes una cuenta aún. Usa `/join` para empezar.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='marcador')
    async def marcador(self, ctx):
        """Muestra los resultados actuales de los partidos en vivo (FIFA API)."""
        import api_football
        data = await api_football.fetch_fifa_live_scores(session=self.bot.session)
        
        matches = data.get('matches', []) if data else []
        
        if not matches:
            await ctx.send("⚽ No hay partidos jugándose en vivo en este momento.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🏟️ Marcador FIFA en Vivo",
            description="Resultados en tiempo real (1s delay).",
            color=discord.Color.red()
        )

        for m in matches:
            home = m['homeTeam']['name']
            away = m['awayTeam']['name']
            score_home = m['score']['fullTime']['home']
            score_away = m['score']['fullTime']['away']
            emoji_home = api_football.get_team_flag_emoji(m['homeTeam'])
            emoji_away = api_football.get_team_flag_emoji(m['awayTeam'])
            
            embed.add_field(
                name=f"{emoji_home} {home} vs {away} {emoji_away}",
                value=f"**Marcador:** `{score_home} - {score_away}`",
                inline=False
            )
        
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='ayuda')
    async def ayuda(self, ctx):
        """Muestra la lista completa de comandos."""
        embed = discord.Embed(
            title="📖 Guía de Comandos - BetBot",
            description="Usa los comandos de barra `/` para ver sugerencias automáticas. Para entender cómo funcionan las apuestas, usa `/reglas`.",
            color=discord.Color.purple()
        )
        embed.add_field(name="👤 Usuario", value="`/join`: Regístrate.\n`/balance`: Mira tu dinero.\n`/historial`: Tus apuestas.\n`/historial_all`: Historial de todos.\n`/top`: Mira el ranking de usuarios.", inline=False)
        embed.add_field(name="⚽ Apuestas", value="`/matches`: Próximos partidos.\n`/apuestas`: Tus apuestas activas.\n`/parlay`: Crea una apuesta combinada.\n`/mis_parlays`: Mira tus parlays activos.\n`/cashout`: Retira apuestas.\n`/vivo`: Mira los partidos en vivo.\n`/pozo <id>`: Mira el volumen y cuotas del pozo (Público).\n`/marcador`: Resultados en vivo (goles).\n`/reglas`: Sistema de pozo y premios.", inline=False)
        
        if ctx.author.guild_permissions.administrator:
            embed.add_field(name="⚙️ Administración", value="`/config_roles`: Configura roles y umbrales.\n`/debug_resolve`: Fuerza resolución de partidos.", inline=False)
            
        embed.set_footer(text="¡Buena suerte en tus apuestas!")
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='top')
    async def top(self, ctx):
        """Muestra el ranking de los 10 usuarios más ricos."""
        top_users = await database.get_top_users(10)
        if not top_users:
            await ctx.send("No hay usuarios registrados aún.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🏆 Ranking de Usuarios - BetBot",
            description="Estos son los usuarios con mayor balance del servidor.",
            color=discord.Color.gold()
        )

        medals = ["🥇", "🥈", "🥉", "👤", "👤", "👤", "👤", "👤", "👤", "👤"]

        leaderboard = ""
        for i, (u_id, balance) in enumerate(top_users):
            user = self.bot.get_user(u_id)
            if not user:
                try: user = await self.bot.fetch_user(u_id)
                except: user = None

            name = user.name if user else f"Usuario {u_id}"
            medal = medals[i] if i < len(medals) else "👤"
            leaderboard += f"{medal} **{name}**: ${balance:.2f}\n"

        embed.add_field(name="Top 10", value=leaderboard, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='reglas')
    async def reglas(self, ctx):
        """Explica el funcionamiento detallado de las apuestas."""
        embed = discord.Embed(
            title="⚖️ ¿Cómo funcionan las apuestas?",
            description="BetBot utiliza un sistema de pozo mutuo con inyección de la casa.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="1. El Pozo", 
            value="Todas las apuestas de los usuarios se acumulan en un pozo único para cada partido.", 
            inline=False
        )
        embed.add_field(
            name="2. Inyección de la Casa", 
            value="El bot añade un monto extra (Bono de la Casa) al pozo inicial para asegurar premios atractivos incluso en partidos con pocas apuestas.", 
            inline=False
        )
        embed.add_field(
            name="3. El Premio", 
            value="Si aciertas, el pozo total se reparte entre todos los ganadores proporcionalmente a lo que apostaron. ¡Si eres el único ganador, te llevas todo el pozo!", 
            inline=False
        )
        embed.add_field(
            name="4. Sin Ganadores", 
            value="Si nadie acierta el resultado, el dinero se queda en el pozo (la casa gana) para financiar futuros bonos.", 
            inline=False
        )
        embed.add_field(
            name="5. Bono Diario", 
            value="Si tu balance llega a $0, el bot te regalará **$15.00** automáticamente cada 24 horas.", 
            inline=False
        )
        embed.set_footer(text="Usa /matches para empezar a apostar.")
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='config_roles')
    @commands.has_permissions(administrator=True)
    async def config_roles(self, ctx, type: str, role: discord.Role, threshold: float = None):
        """[ADMIN] Configura roles por desempeño. Tipos: broke, gambler, pro."""
        type = type.lower()
        if type not in ['broke', 'gambler', 'pro']:
            await ctx.send("❌ Tipo inválido. Usa: `broke`, `gambler` o `pro`.", ephemeral=True)
            return
        
        await database.set_setting(f"role_{type}", role.id)
        if threshold is not None:
            await database.set_setting(f"threshold_{type}", threshold)
        
        await ctx.send(f"✅ Configurado: Los usuarios **{type}** recibirán el rol {role.mention}" + 
                       (f" al alcanzar **${threshold:.2f}**." if threshold else "."), ephemeral=True)

    @config_roles.error
    async def config_roles_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Solo los administradores pueden usar este comando.", ephemeral=True)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Error en los argumentos. Uso: `/config_roles <tipo> <@rol> [monto]`\nEjemplo: `/config_roles gambler @Apostador 500`.", ephemeral=True)
        else:
            await ctx.send(f"❌ Error al ejecutar el comando: {error}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(General(bot))
