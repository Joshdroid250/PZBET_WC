import asyncio
import os
import discord
from discord.ext import commands
import database
import betting
import api_football
from dotenv import load_dotenv

load_dotenv()

async def manual_announce():
    # Setup temporal del bot para enviar el mensaje
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    
    token = os.getenv('DISCORD_TOKEN')
    channel_id = os.getenv('ANNOUNCEMENT_CHANNEL_ID')
    
    if not token or not channel_id:
        print("Falta TOKEN o CHANNEL_ID en .env")
        return

    @bot.event
    async def on_ready():
        print(f"Bot listo como {bot.user}. Enviando anuncio manual...")
        m_id = 537351
        home, away = "Germany", "Curaçao"
        winner = "HOME_TEAM"
        f_h, f_a = 7, 1
        
        channel = bot.get_channel(int(channel_id))
        if channel:
            winner_name = home
            embed_res = discord.Embed(title=f"🏁 Resultado Final: {home} vs {away}", description=f"El ganador fue: **{winner_name}** ({f_h}-{f_a})", color=discord.Color.gold())
            
            # Obtener resumen de lo que ya se pagó de la DB
            import sqlite3
            conn = sqlite3.connect('betbot.db')
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, amount, payout, won FROM bets WHERE match_id = ?", (m_id,))
            rows = cursor.fetchall()
            
            summary = []
            for u_id, amt, payout, won in rows:
                user = bot.get_user(u_id) or await bot.fetch_user(u_id)
                name = user.mention if user else f"ID:{u_id}"
                res_icon = "✅" if won else "❌"
                summary.append(f"{res_icon} {name}: **${payout:.2f}** (Apostó ${amt:.2f})")
            
            if summary:
                embed_res.add_field(name="💰 Premios Repartidos", value="\n".join(summary), inline=False)
            
            embed_res.set_footer(text="Nota: Estos premios ya fueron acreditados a sus cuentas.")
            await channel.send(embed=embed_res)
            print("✅ Anuncio enviado con éxito.")
        else:
            print("❌ No se encontró el canal de anuncios.")
        
        await bot.close()

    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(manual_announce())
