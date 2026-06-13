import discord
from discord.ext import commands, tasks
import database
import api_football
import betting
import os
import asyncio
from datetime import datetime, timezone

class BetModal(discord.ui.Modal, title='Realizar Apuesta'):
    amount = discord.ui.TextInput(
        label='Cantidad a apostar',
        placeholder='Ejemplo: 50.50',
        min_length=1,
        max_length=10,
    )

    def __init__(self, match_id, team_name, prediction):
        super().__init__()
        self.match_id = match_id
        self.team_name = team_name
        self.prediction = prediction

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            amount_val = float(self.amount.value)
        except ValueError:
            await interaction.response.send_message("❌ Por favor, ingresa un número válido.", ephemeral=True)
            return

        if amount_val <= 0:
            await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)
            return

        balance = await database.get_user_balance(user_id)
        if balance is None:
            await interaction.response.send_message("❌ No estás registrado. Usa `/join` primero.", ephemeral=True)
            return

        if balance < amount_val:
            await interaction.response.send_message(f"❌ Saldo insuficiente. Tienes **${balance:.2f}**.", ephemeral=True)
            return

        # Verificar si el partido sigue abierto
        match_info = await api_football.get_match_details(self.match_id)
        if not match_info or match_info['status'] == 'FINISHED':
            await interaction.response.send_message("❌ Este partido ya ha finalizado.", ephemeral=True)
            return

        # Registrar el partido en la DB
        await database.add_or_update_match(
            self.match_id, 
            match_info['homeTeam']['name'], 
            match_info['awayTeam']['name'], 
            match_info['status']
        )

        # Registrar apuesta
        await database.place_bet(user_id, self.match_id, amount_val, self.prediction)
        
        total_bets, pools = await database.get_match_pools(self.match_id)
        house_injection = betting.HOUSE_INJECTION
        total_pool = total_bets + house_injection
        
        pred_pool = pools.get(self.prediction, 0)
        multiplier = total_pool / pred_pool if pred_pool > 0 else 1.0
        if multiplier > 10.0: multiplier = 10.0
        bar = betting.get_multiplier_bar(multiplier)

        home_team = match_info['homeTeam']['name']
        away_team = match_info['awayTeam']['name']
        home_emoji = api_football.get_flag_emoji(home_team)
        away_emoji = api_football.get_flag_emoji(away_team)

        embed = discord.Embed(title="✅ Apuesta Confirmada", color=discord.Color.green())
        embed.add_field(name="Usuario", value=interaction.user.mention, inline=True)
        embed.add_field(name="Partido", value=f"{home_emoji} **{home_team}** vs **{away_team}** {away_emoji}", inline=False)
        embed.add_field(name="Tu Predicción", value=f"**{self.team_name}**", inline=True)
        embed.add_field(name="Monto", value=f"**${amount_val:.2f}**", inline=True)
        embed.add_field(name="📊 Estadísticas", value=f"**Volumen:** ${total_pool:.2f}\n**Multiplicador:** x{multiplier:.2f}\n{bar}", inline=False)
        
        flag_home = api_football.get_flag_url(home_team)
        if flag_home:
            embed.set_thumbnail(url=flag_home)
            
        await interaction.response.send_message(embed=embed)

class ParlayAmountModal(discord.ui.Modal, title='Monto del Parlay'):
    amount = discord.ui.TextInput(
        label='Cantidad total a apostar',
        placeholder='Ejemplo: 20.00',
        min_length=1,
        max_length=10,
    )

    def __init__(self, legs):
        super().__init__()
        self.legs = legs # List of (match_id, prediction, home_name, away_name)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            amount_val = float(self.amount.value)
        except ValueError:
            await interaction.response.send_message("❌ Monto inválido.", ephemeral=True)
            return

        balance = await database.get_user_balance(user_id)
        if balance < amount_val:
            await interaction.response.send_message("❌ Saldo insuficiente.", ephemeral=True)
            return

        # Registrar parlay
        legs_db = [(l[0], l[1]) for l in self.legs]
        await database.place_parlay(user_id, amount_val, legs_db)

        embed = discord.Embed(title="🚀 Parlay Confirmado", color=discord.Color.gold())
        embed.add_field(name="Monto Total", value=f"${amount_val:.2f}", inline=False)
        
        legs_text = ""
        for _, pred, home, away in self.legs:
            pred_text = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
            legs_text += f"• **{home} vs {away}**: {pred_text}\n"
        
        embed.add_field(name="Combinaciones", value=legs_text, inline=False)
        embed.set_footer(text="¡Ganas si aciertas todas las predicciones!")
        await interaction.response.send_message(embed=embed)

class ParlayBuilderView(discord.ui.View):
    def __init__(self, matches, user_id):
        super().__init__(timeout=300)
        self.matches = matches
        self.user_id = user_id
        self.selected_legs = [] # List of (match_id, prediction, home, away)
        self.add_item(ParlayMatchSelect(matches))

    @discord.ui.button(label="✅ Confirmar Parlay", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_legs:
            await interaction.response.send_message("❌ Debes seleccionar al menos un partido.", ephemeral=True)
            return
        if len(self.selected_legs) < 2:
            await interaction.response.send_message("❌ Un parlay necesita al menos 2 partidos.", ephemeral=True)
            return
            
        await interaction.response.send_modal(ParlayAmountModal(self.selected_legs))

class ParlayMatchSelect(discord.ui.Select):
    def __init__(self, matches):
        options = [
            discord.SelectOption(
                label=f"{m['homeTeam']['name']} vs {m['awayTeam']['name']}",
                value=str(m['id'])
            ) for m in matches[:25]
        ]
        super().__init__(placeholder="Selecciona un partido para tu parlay...", options=options)

    async def callback(self, interaction: discord.Interaction):
        match_id = int(self.values[0])
        match_info = await api_football.get_match_details(match_id)
        
        home = match_info['homeTeam']['name']
        away = match_info['awayTeam']['name']
        
        view = discord.ui.View()
        btn_home = discord.ui.Button(label=f"Ganador: {home}", style=discord.ButtonStyle.primary)
        btn_draw = discord.ui.Button(label="Empate", style=discord.ButtonStyle.secondary)
        btn_away = discord.ui.Button(label=f"Ganador: {away}", style=discord.ButtonStyle.danger)

        async def add_leg(inter, pred):
            self.view.selected_legs = [l for l in self.view.selected_legs if l[0] != match_id]
            self.view.selected_legs.append((match_id, pred, home, away))
            legs_text = "\n".join([f"✅ {l[2]} vs {l[3]} (**{l[1]}**)" for l in self.view.selected_legs])
            embed = discord.Embed(title="🏗️ Construyendo Parlay", description=f"Selecciones actuales:\n{legs_text}", color=discord.Color.blue())
            await inter.response.edit_message(embed=embed, view=self.view)

        btn_home.callback = lambda i: add_leg(i, "HOME_TEAM")
        btn_draw.callback = lambda i: add_leg(i, "DRAW")
        btn_away.callback = lambda i: add_leg(i, "AWAY_TEAM")
        
        view.add_item(btn_home)
        view.add_item(btn_draw)
        view.add_item(btn_away)
        
        await interaction.response.send_message(f"¿Qué resultado predices para **{home} vs {away}**?", view=view, ephemeral=True)

class MatchSelect(discord.ui.Select):
    def __init__(self, matches):
        options = [
            discord.SelectOption(
                label=f"{m['homeTeam']['name']} vs {m['awayTeam']['name']}",
                description=f"Fecha: {m['utcDate'][:10]}",
                value=str(m['id'])
            ) for m in matches
        ]
        super().__init__(placeholder="Selecciona un partido para apostar...", options=options)

    async def callback(self, interaction: discord.Interaction):
        match_id = int(self.values[0])
        match_info = await api_football.get_match_details(match_id)
        
        home = match_info['homeTeam']['name']
        away = match_info['awayTeam']['name']
        home_emoji = api_football.get_flag_emoji(home)
        away_emoji = api_football.get_flag_emoji(away)
        
        embed = discord.Embed(
            title=f"🏆 {home_emoji} {home} vs {away} {away_emoji}",
            description=f"Estado: **{match_info['status']}**\nID: `{match_id}`",
            color=discord.Color.green()
        )
        flag = api_football.get_flag_url(home)
        if flag:
            embed.set_thumbnail(url=flag)
        
        view = discord.ui.View(timeout=None)
        btn_home = discord.ui.Button(label=home, style=discord.ButtonStyle.primary)
        btn_draw = discord.ui.Button(label="Empate", style=discord.ButtonStyle.secondary)
        btn_away = discord.ui.Button(label=away, style=discord.ButtonStyle.danger)
        btn_back = discord.ui.Button(label="⬅️ Volver", style=discord.ButtonStyle.gray)

        async def make_bet_callback(inter, team, pred):
            await inter.response.send_modal(BetModal(match_id, team, pred))

        btn_home.callback = lambda i: make_bet_callback(i, home, "HOME_TEAM")
        btn_draw.callback = lambda i: make_bet_callback(i, "Empate", "DRAW")
        btn_away.callback = lambda i: make_bet_callback(i, away, "AWAY_TEAM")
        
        async def back_callback(inter):
            await inter.response.edit_message(content="Cargando lista...", embed=None, view=None)
            await inter.edit_original_response(content="Usa `/matches` para volver a la lista completa.")

        btn_back.callback = back_callback

        view.add_item(btn_home)
        view.add_item(btn_draw)
        view.add_item(btn_away)
        view.add_item(btn_back)

        await interaction.response.edit_message(content=None, embed=embed, view=view)

class BettingView(discord.ui.View):
    def __init__(self, matches):
        super().__init__(timeout=180)
        self.add_item(MatchSelect(matches))

class CashoutSelect(discord.ui.Select):
    def __init__(self, items, is_parlay=False):
        options = []
        if not is_parlay:
            for home, away, amount, pred, m_id in items:
                options.append(discord.SelectOption(
                    label=f"{home} vs {away}",
                    description=f"Apuesta: ${amount:.2f}",
                    value=f"ind_{m_id}_{amount}"
                ))
        else:
            for p in items:
                options.append(discord.SelectOption(
                    label=f"Parlay #{p['id']}",
                    description=f"Monto: ${p['amount']:.2f} | {len(p['legs'])} partidos",
                    value=f"par_{p['id']}_{p['amount']}"
                ))
        super().__init__(placeholder="Elige la apuesta para cobrar (80% reembolso)...", options=options)

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        val_parts = self.values[0].split('_')
        prefix, bet_id, amount = val_parts[0], int(val_parts[1]), float(val_parts[2])
        return_amount = amount * 0.8
        
        if prefix == 'ind':
            match_info = await api_football.get_match_details(bet_id)
            if match_info and match_info['status'] == 'FINISHED':
                await interaction.response.send_message("❌ El partido ya terminó.", ephemeral=True)
                return
            await database.remove_bet(user_id, bet_id)
        else:
            await database.remove_parlay(user_id, bet_id)

        await database.update_balance(user_id, return_amount)
        await interaction.response.send_message(embed=discord.Embed(title="💰 Cashout Exitoso", description=f"Has recuperado **${return_amount:.2f}**.", color=discord.Color.gold()))

class CashoutView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id

    @discord.ui.button(label="Apuestas Individuales", style=discord.ButtonStyle.primary)
    async def individual(self, interaction: discord.Interaction, button: discord.ui.Button):
        bets = await database.get_user_active_bets(self.user_id)
        if not bets:
            await interaction.response.send_message("Sin apuestas activas.", ephemeral=True)
            return
        view = discord.ui.View()
        view.add_item(CashoutSelect(bets, False))
        await interaction.response.edit_message(content="Elige la apuesta:", view=view)

    @discord.ui.button(label="Parlays (Combinadas)", style=discord.ButtonStyle.secondary)
    async def parlay(self, interaction: discord.Interaction, button: discord.ui.Button):
        parlays = await database.get_user_active_parlays(self.user_id)
        if not parlays:
            await interaction.response.send_message("Sin parlays activos.", ephemeral=True)
            return
        view = discord.ui.View()
        view.add_item(CashoutSelect(parlays, True))
        await interaction.response.edit_message(content="Elige el parlay:", view=view)

class Betting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_check_time = 0
        self.check_matches.start()

    def cog_unload(self):
        self.check_matches.cancel()

    @commands.hybrid_command(name='matches')
    async def matches(self, ctx):
        """Lista los partidos próximos."""
        comp = os.getenv('COMPETITION_CODE', 'PL')
        upcoming = await api_football.get_upcoming_matches(comp)
        if not upcoming:
            await ctx.send("No hay partidos programados.")
            return
        embed = discord.Embed(title="⚽ Selección de Partidos", color=discord.Color.blue())
        await ctx.send(embed=embed, view=BettingView(upcoming[:25]))

    @commands.hybrid_command(name='apuestas')
    async def apuestas(self, ctx):
        """Mira tus apuestas activas."""
        user_id = ctx.author.id
        user_bets = await database.get_user_active_bets(user_id)
        if not user_bets:
            await ctx.send("No tienes apuestas activas.")
            return
        embed = discord.Embed(title="📝 Tus Apuestas Activas", color=discord.Color.blue())
        for home, away, amount, pred, m_id in user_bets:
            total_bets, pools = await database.get_match_pools(m_id)
            total_pool = total_bets + betting.HOUSE_INJECTION
            pred_pool = pools.get(pred, 0)
            multiplier = min(10.0, total_pool / pred_pool if pred_pool > 0 else 1.0)
            pred_name = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
            embed.add_field(name=f"{home} vs {away}", value=f"**Monto:** ${amount:.2f}\n**Predicción:** {pred_name}\n**Cuota:** x{multiplier:.2f}", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='historial')
    async def historial(self, ctx):
        """Mira tus apuestas pasadas."""
        history = await database.get_user_history(ctx.author.id)
        if not history:
            await ctx.send("Historial vacío.")
            return
        embed = discord.Embed(title="📜 Tu Historial", color=discord.Color.blue())
        for home, away, amount, pred, payout, won, winner in history:
            status = "✅ GANADA" if won else "❌ PERDIDA"
            pred_name = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
            embed.add_field(name=f"{home} vs {away}", value=f"{status} | Apostado: ${amount:.2f} | Ganado: ${payout:.2f}\nPred: {pred_name}", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='historial_all')
    async def historial_all(self, ctx):
        """Historial de todos los usuarios."""
        history = await database.get_global_history(15)
        if not history:
            await ctx.send("Sin historial global.")
            return
        embed = discord.Embed(title="🌍 Historial Global", color=discord.Color.dark_blue())
        for u_id, home, away, amount, pred, payout, won, winner in history:
            user = self.bot.get_user(u_id) or await self.bot.fetch_user(u_id)
            name = user.name if user else f"ID:{u_id}"
            embed.add_field(name=f"👤 {name} | {home} vs {away}", value=f"Ganancia: ${payout:.2f}", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='cashout')
    async def cashout(self, ctx):
        """Retira una apuesta activa."""
        await ctx.send("Selecciona qué tipo de apuesta quieres retirar:", view=CashoutView(ctx.author.id))

    @commands.hybrid_command(name='vivo')
    async def vivo(self, ctx):
        """Mira partidos en juego."""
        comp = os.getenv('COMPETITION_CODE', 'PL')
        url = f"{api_football.BASE_URL}/competitions/{comp}/matches?status=LIVE"
        data = await api_football.fetch_json(url)
        matches = data.get('matches', []) if data else []
        if not matches:
            await ctx.send("Sin partidos en vivo.")
            return
        await ctx.send(embed=discord.Embed(title="🏟️ En Vivo", color=discord.Color.red()), view=BettingView(matches[:25]))

    @commands.hybrid_command(name='parlay')
    async def parlay(self, ctx):
        """Crea un parlay (combinada)."""
        comp = os.getenv('COMPETITION_CODE', 'PL')
        upcoming = await api_football.get_upcoming_matches(comp)
        if not upcoming:
            await ctx.send("Sin partidos para parlay.")
            return
        await ctx.send(embed=discord.Embed(title="🏗️ Constructor de Parlays"), view=ParlayBuilderView(upcoming, ctx.author.id))

    @commands.hybrid_command(name='mis_parlays')
    async def mis_parlays(self, ctx):
        """Tus parlays activos."""
        parlays = await database.get_user_active_parlays(ctx.author.id)
        if not parlays:
            await ctx.send("Sin parlays activos.")
            return
        embed = discord.Embed(title="🚀 Tus Parlays", color=discord.Color.gold())
        for p in parlays:
            text = "\n".join([f"{'✅' if s=='WON' else '❌' if s=='LOST' else '⏳'} {h} vs {a}" for h,a,pr,s in p['legs']])
            embed.add_field(name=f"ID: {p['id']} (${p['amount']:.2f})", value=text, inline=False)
        await ctx.send(embed=embed)

    @tasks.loop(seconds=20)
    async def check_matches(self):
        print("🔍 [DEBUG] Revisando partidos...")
        try:
            now_utc = datetime.now(timezone.utc)
            active_ids = await database.get_all_active_match_ids()
            parlay_ids = await database.get_active_parlay_ids()
            for p_id in parlay_ids:
                for m_id, _, s in await database.get_parlay_legs(p_id):
                    if s == 'PENDING' and m_id not in active_ids: active_ids.append(m_id)
            
            if not active_ids: return
            
            is_live, earliest = False, None
            matches = []
            for m_id in active_ids:
                match = await api_football.get_match_details(m_id)
                if not match: continue
                matches.append(match)
                if match['status'] in ['IN_PLAY', 'PAUSED', 'LIVE']: is_live = True
                dt = datetime.fromisoformat(match['utcDate'].replace('Z', '+00:00'))
                if earliest is None or dt < earliest: earliest = dt

            # Si no hay nada en vivo y el partido más cercano falta más de 10 min, ahorrar API
            if not is_live and earliest and (earliest - now_utc).total_seconds() > 600:
                # Revisar solo cada 5 min (cada 15 ciclos de 20s)
                if not hasattr(self, '_loop_counter'): self._loop_counter = 0
                self._loop_counter += 1
                if self._loop_counter % 15 != 0: return 

            for match in matches:
                m_id, status = match['id'], match['status']
                home, away = match['homeTeam']['name'], match['awayTeam']['name']
                print(f"📌 [LOG] {home} vs {away} | Estado: {status}")
                
                channel_id_env = os.getenv('ANNOUNCEMENT_CHANNEL_ID')
                if channel_id_env and status in ['IN_PLAY', 'PAUSED', 'LIVE']:
                    try:
                        channel_id = int(str(channel_id_env).strip().strip('"').strip("'"))
                        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)

                        if channel:
                            score = f"{match['score']['fullTime']['home']}-{match['score']['fullTime']['away']}"
                            emoji_h = api_football.get_flag_emoji(home)
                            emoji_a = api_football.get_flag_emoji(away)
                            
                            live_info = await database.get_live_msg_info(m_id)
                            msg_id = live_info[0] if live_info else None
                            last_score = live_info[1] if live_info else None
                            
                            embed_live = discord.Embed(title=f"🏟️ EN VIVO: {emoji_h} {home} vs {away} {emoji_a}", description=f"Marcador Actual: **{score}**", color=discord.Color.red())
                            
                            if msg_id:
                                try:
                                    msg = await channel.fetch_message(msg_id)
                                    # Si el mensaje existe, solo editamos si el marcador cambió
                                    if score != last_score:
                                        await msg.edit(embed=embed_live)
                                        await database.update_live_msg_info(m_id, msg_id, score)
                                        print(f"📝 [MSG] Marcador editado: {home} vs {away}")
                                except discord.NotFound:
                                    # Si el mensaje fue borrado, enviamos uno nuevo
                                    new_msg = await channel.send(embed=embed_live)
                                    await database.update_live_msg_info(m_id, new_msg.id, score)
                                    print(f"📣 [MSG] Marcador recreado (era inexistente): {home} vs {away}")
                                except Exception as e:
                                    print(f"⚠️ Error al intentar editar mensaje: {e}")
                            else:
                                # Primer mensaje para este partido
                                new_msg = await channel.send(embed=embed_live)
                                await database.update_live_msg_info(m_id, new_msg.id, score)
                                print(f"📣 [MSG] Nuevo marcador enviado: {home} vs {away}")
                    except Exception as e: print(f"⚠️ Error live msg: {e}")

                if status == 'FINISHED':
                    live_info = await database.get_live_msg_info(m_id)
                    if live_info and live_info[0]:
                        try:
                            channel = self.bot.get_channel(int(channel_id_env)) or await self.bot.fetch_channel(int(channel_id_env))
                            msg = await channel.fetch_message(live_info[0])
                            await msg.delete()
                            await database.update_live_msg_info(m_id, None, None)
                            print(f"🗑️ [MSG] Marcador borrado: {home} vs {away}")
                        except: pass
                    
                    winner = match['score']['winner']
                    if winner:
                        payouts = await betting.resolve_match_bets(self.bot, m_id, winner)
                        channel = self.bot.get_channel(int(channel_id_env)) or await self.bot.fetch_channel(int(channel_id_env))
                        if channel:
                            winner_name = home if winner == 'HOME_TEAM' else away if winner == 'AWAY_TEAM' else "Empate"
                            embed_res = discord.Embed(title=f"🏁 Resultado: {home} vs {away}", description=f"Ganador: **{winner_name}**", color=discord.Color.gold())
                            summary = []
                            for p in payouts:
                                user = self.bot.get_user(p['user_id']) or await self.bot.fetch_user(p['user_id'])
                                name = user.mention if user else f"ID:{p['user_id']}"
                                summary.append(f"{'✅' if p['won'] else '❌'} {name}: ${p['payout']:.2f}")
                            if summary: embed_res.add_field(name="Resumen", value="\n".join(summary))
                            await channel.send(embed=embed_res)
                            print(f"📢 [MSG] Anuncio enviado: {home} vs {away}")
                        await betting.resolve_parlays_for_match(self.bot, m_id, winner)
                        await database.add_or_update_match(m_id, home, away, status, winner)
        except Exception as e: print(f"ERROR: {e}")

    @check_matches.before_loop
    async def before_check_matches(self): await self.bot.wait_until_ready()

    @commands.hybrid_command(name='debug_resolve')
    @commands.has_permissions(administrator=True)
    async def debug_resolve(self, ctx, match_id: int, winner: str):
        """[ADMIN] Fuerza resolución."""
        winner = winner.upper()
        await betting.resolve_match_bets(self.bot, match_id, winner)
        await betting.resolve_parlays_for_match(self.bot, match_id, winner)
        await ctx.send(f"✅ Resuelto ID {match_id} como {winner}.")

async def setup(bot): await bot.add_cog(Betting(bot))
