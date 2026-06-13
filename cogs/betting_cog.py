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
            await interaction.response.send_message("❌ No estás registrado. Usa `!join` primero.", ephemeral=True)
            return

        if balance < amount_val:
            await interaction.response.send_message(f"❌ Saldo insuficiente. Tienes **${balance:.2f}**.", ephemeral=True)
            return

        # Verificar si el partido sigue abierto
        match_info = api_football.get_match_details(self.match_id)
        if not match_info or match_info['status'] == 'FINISHED':
            await interaction.response.send_message("❌ Este partido ya ha finalizado.", ephemeral=True)
            return

        # Registrar el partido en la DB para que aparezca en !apuestas (JOIN)
        await database.add_or_update_match(
            self.match_id, 
            match_info['homeTeam']['name'], 
            match_info['awayTeam']['name'], 
            match_info['status']
        )

        # Registrar apuesta
        await database.place_bet(user_id, self.match_id, amount_val, self.prediction)
        
        # Obtener estadísticas del pozo
        total_bets, pools = await database.get_match_pools(self.match_id)
        house_injection = betting.HOUSE_INJECTION
        total_pool = total_bets + house_injection
        
        # Calcular multiplicador actual para esta predicción
        pred_pool = pools.get(self.prediction, 0)
        multiplier = total_pool / pred_pool if pred_pool > 0 else 1.0
        if multiplier > 10.0: multiplier = 10.0 # Cap de seguridad
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
        embed.add_field(name="📊 Estadísticas del Partido", value=f"**Volumen Total:** ${total_pool:.2f}\n**Multiplicador Estimado:** x{multiplier:.2f}\n{bar}", inline=False)
        
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
        match_info = api_football.get_match_details(match_id)
        
        home = match_info['homeTeam']['name']
        away = match_info['awayTeam']['name']
        
        view = discord.ui.View()
        btn_home = discord.ui.Button(label=f"Ganador: {home}", style=discord.ButtonStyle.primary)
        btn_draw = discord.ui.Button(label="Empate", style=discord.ButtonStyle.secondary)
        btn_away = discord.ui.Button(label=f"Ganador: {away}", style=discord.ButtonStyle.danger)

        async def add_leg(inter, pred):
            # Check if match already in selected_legs
            self.view.selected_legs = [l for l in self.view.selected_legs if l[0] != match_id]
            self.view.selected_legs.append((match_id, pred, home, away))
            
            # Update original message
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
        match_info = api_football.get_match_details(match_id)
        
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
        
        # Nueva vista para el partido seleccionado
        view = discord.ui.View(timeout=None)
        
        # Botones de apuesta
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
            await inter.edit_original_response(content="Usa `!matches` para volver a la lista completa.")

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
        self.is_parlay = is_parlay

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        val_parts = self.values[0].split('_')
        prefix = val_parts[0]
        bet_id = int(val_parts[1])
        amount = float(val_parts[2])
        
        penalty = 0.20
        return_amount = amount * (1 - penalty)
        
        if prefix == 'ind':
            # Verificar si el partido no ha terminado
            match_info = api_football.get_match_details(bet_id)
            if match_info and match_info['status'] == 'FINISHED':
                await interaction.response.send_message("❌ El partido ya terminó, no puedes hacer cashout.", ephemeral=True)
                return
            await database.remove_bet(user_id, bet_id)
        else:
            # Parlay
            await database.remove_parlay(user_id, bet_id)

        await database.update_balance(user_id, return_amount)
        
        embed = discord.Embed(title="💰 Cashout Exitoso", color=discord.Color.gold())
        embed.description = f"Has recuperado **${return_amount:.2f}** (80% del original)."
        await interaction.response.send_message(embed=embed)

class CashoutView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id

    @discord.ui.button(label="Apuestas Individuales", style=discord.ButtonStyle.primary)
    async def individual(self, interaction: discord.Interaction, button: discord.ui.Button):
        bets = await database.get_user_active_bets(self.user_id)
        if not bets:
            await interaction.response.send_message("No tienes apuestas individuales activas.", ephemeral=True)
            return
        
        view = discord.ui.View()
        view.add_item(CashoutSelect(bets, is_parlay=False))
        await interaction.response.edit_message(content="Selecciona la apuesta individual:", view=view)

    @discord.ui.button(label="Parlays (Combinadas)", style=discord.ButtonStyle.secondary)
    async def parlay(self, interaction: discord.Interaction, button: discord.ui.Button):
        parlays = await database.get_user_active_parlays(self.user_id)
        if not parlays:
            await interaction.response.send_message("No tienes parlays activos.", ephemeral=True)
            return
        
        view = discord.ui.View()
        view.add_item(CashoutSelect(parlays, is_parlay=True))
        await interaction.response.edit_message(content="Selecciona el parlay:", view=view)

class Betting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_matches.start()

    def cog_unload(self):
        self.check_matches.cancel()

    @commands.command(name='matches')
    async def matches(self, ctx):
        """Lista los partidos en un menú desplegable para evitar spam."""
        competition = os.getenv('COMPETITION_CODE', 'PL')
        upcoming = api_football.get_upcoming_matches(competition)
        
        if not upcoming:
            await ctx.send("No hay partidos programados próximamente.")
            return

        embed = discord.Embed(
            title="⚽ Selección de Partidos",
            description="Elige un partido del menú de abajo para ver detalles y apostar.",
            color=discord.Color.blue()
        )
        
        view = BettingView(upcoming[:25]) # Límite de 25 para el Select de Discord
        await ctx.send(embed=embed, view=view)

    @commands.command(name='apuestas')
    async def apuestas(self, ctx):
        """Muestra tus apuestas activas que aún no se han resuelto."""
        user_id = ctx.author.id
        user_bets = await database.get_user_active_bets(user_id)
        
        if not user_bets:
            embed = discord.Embed(title="🚫 Sin Apuestas", description="No tienes apuestas activas en este momento.", color=discord.Color.light_grey())
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(title="📝 Tus Apuestas Activas", color=discord.Color.blue())
        for home, away, amount, pred, m_id in user_bets:
            # Calcular estadísticas en vivo
            total_bets, pools = await database.get_match_pools(m_id)
            house_injection = betting.HOUSE_INJECTION
            total_pool = total_bets + house_injection
            
            pred_pool = pools.get(pred, 0)
            multiplier = total_pool / pred_pool if pred_pool > 0 else 1.0
            if multiplier > 10.0: multiplier = 10.0
            
            pred_text = pred.replace('_', ' ')
            embed.add_field(
                name=f"{home} vs {away}",
                value=(
                    f"**Monto:** ${amount:.2f}\n"
                    f"**Predicción:** {pred_text}\n"
                    f"**Multiplicador en vivo:** x{multiplier:.2f}\n"
                    f"**Pozo Total:** ${total_pool:.2f}\n"
                    f"**ID:** {m_id}"
                ),
                inline=False
            )
        
        if user_bets:
            flag = api_football.get_flag_url(user_bets[0][0])
            if flag:
                embed.set_thumbnail(url=flag)

        embed.set_footer(text="Las apuestas se resuelven automáticamente al terminar el partido.")
        await ctx.send(embed=embed)

    @commands.command(name='historial')
    async def historial(self, ctx):
        """Muestra tus últimas 10 apuestas resueltas."""
        user_id = ctx.author.id
        try:
            history = await database.get_user_history(user_id)
            if not history:
                embed = discord.Embed(title="📜 Historial Vacío", description="Aún no tienes completada ninguna apuesta.", color=discord.Color.light_grey())
                await ctx.send(embed=embed)
                return

            embed = discord.Embed(title="📜 Tu Historial de Apuestas", color=discord.Color.blue())
            for home, away, amount, pred, payout, won, winner in history:
                status = "✅ GANADA" if won else "❌ PERDIDA"
                pred_name = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
                res_text = f"Resultado: {winner.replace('_', ' ')}" if winner else "Resultado: N/A"
                
                embed.add_field(
                    name=f"{home} vs {away}",
                    value=f"**Estado:** {status}\n**Apostado:** ${amount:.2f} | **Recibido:** ${payout:.2f}\n**Tu Predicción:** {pred_name}\n*{res_text}*",
                    inline=False
                )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send("❌ Ocurrió un error al cargar tu historial.")

    @commands.command(name='cashout')
    async def cashout(self, ctx, match_id: int):
        """Retira tu apuesta antes de que termine el partido (con una penalización del 20%)."""
        user_id = ctx.author.id
        amount = await database.get_bet_amount(user_id, match_id)
        
        if amount is None:
            await ctx.send("No tienes ninguna apuesta activa en este partido.")
            return

        match_info = api_football.get_match_details(match_id)
        if match_info and match_info['status'] == 'FINISHED':
            await ctx.send("El partido ya ha terminado. No puedes hacer cashout.")
            return

        penalty = 0.20
        return_amount = amount * (1 - penalty)
        await database.remove_bet(user_id, match_id)
        await database.update_balance(user_id, return_amount)
        
        embed = discord.Embed(title="💰 Cashout Exitoso", color=discord.Color.gold())
        embed.description = f"Has recuperado **${return_amount:.2f}**."
        await ctx.send(embed=embed)

    @commands.command(name='vivo')
    async def vivo(self, ctx):
        """Muestra los partidos en vivo."""
        competition = os.getenv('COMPETITION_CODE', 'PL')
        url = f"{api_football.BASE_URL}/competitions/{competition}/matches?status=LIVE"
        import requests
        headers = {'X-Auth-Token': api_football.API_KEY}
        response = requests.get(url, headers=headers)
        
        matches = []
        if response.status_code == 200:
            matches = response.json().get('matches', [])
        
        if not matches:
            await ctx.send("No hay partidos jugándose en este momento.")
            return

        embed = discord.Embed(title="🏟️ Partidos en Vivo", description="Selecciona un partido para apostar.", color=discord.Color.red())
        view = BettingView(matches[:25])
        await ctx.send(embed=embed, view=view)

    @commands.command(name='parlay')
    async def parlay(self, ctx):
        """Inicia el constructor de parlays."""
        competition = os.getenv('COMPETITION_CODE', 'PL')
        upcoming = api_football.get_upcoming_matches(competition)
        
        if not upcoming:
            await ctx.send("No hay partidos programados.")
            return

        embed = discord.Embed(title="🏗️ Constructor de Parlays", description="Selecciona al menos 2 partidos.", color=discord.Color.blue())
        view = ParlayBuilderView(upcoming, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.command(name='mis_parlays')
    async def mis_parlays(self, ctx):
        """Muestra tus parlays activos."""
        user_id = ctx.author.id
        parlays = await database.get_user_active_parlays(user_id)
        if not parlays:
            await ctx.send("No tienes parlays activos.")
            return

        embed = discord.Embed(title="🚀 Tus Parlays Activos", color=discord.Color.gold())
        for p in parlays:
            legs_text = ""
            for home, away, pred, status in p['legs']:
                emoji = "⏳" if status == 'PENDING' else "✅" if status == 'WON' else "❌"
                pred_text = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
                legs_text += f"{emoji} **{home} vs {away}**: {pred_text}\n"
            
            embed.add_field(name=f"Parlay ID: {p['id']} - Monto: ${p['amount']:.2f}", value=legs_text, inline=False)
        await ctx.send(embed=embed)

    @tasks.loop(minutes=1)
    async def check_matches(self):
        """Tarea en segundo plano optimizada."""
        try:
            current_time = asyncio.get_event_loop().time()
            now_utc = datetime.now(timezone.utc)
            
            if not hasattr(self, '_last_check_time'):
                self._last_check_time = 0
            
            active_match_ids = await database.get_all_active_match_ids()
            
            # También considerar partidos de parlays activos
            parlay_ids = await database.get_active_parlay_ids()
            for p_id in parlay_ids:
                legs = await database.get_parlay_legs(p_id)
                for m_id, _, status in legs:
                    if status == 'PENDING' and m_id not in active_match_ids:
                        active_match_ids.append(m_id)

            if not active_match_ids:
                if current_time - self._last_check_time < 1800: return
                self._last_check_time = current_time
                return

            is_any_match_running = False
            earliest_start = None
            matches_to_check = []

            for m_id in active_match_ids:
                match = api_football.get_match_details(m_id)
                if not match: continue
                matches_to_check.append(match)
                if match['status'] in ['IN_PLAY', 'PAUSED', 'LIVE']: is_any_match_running = True
                start_str = match['utcDate'].replace('Z', '+00:00')
                start_dt = datetime.fromisoformat(start_str)
                if earliest_start is None or start_dt < earliest_start: earliest_start = start_dt

            interval = 300
            if is_any_match_running: interval = 60
            elif earliest_start:
                time_until_start = (earliest_start - now_utc).total_seconds()
                if time_until_start > 600: interval = 600
                else: interval = 60
            
            if current_time - self._last_check_time < interval: return
            self._last_check_time = current_time

            for match in matches_to_check:
                match_id = match['id']
                status = match['status']
                home_name = match['homeTeam']['name']
                away_name = match['awayTeam']['name']
                
                if status == 'FINISHED':
                    winner = match['score']['winner']
                    if winner:
                        # 1. Resolver apuestas individuales
                        payouts = await betting.resolve_match_bets(match_id, winner)
                        
                        # 2. Enviar ANUNCIO del partido (Primero los resultados del partido)
                        channel_id = os.getenv('ANNOUNCEMENT_CHANNEL_ID')
                        if channel_id:
                            channel = self.bot.get_channel(int(channel_id))
                            if channel:
                                score_home = match['score']['fullTime']['home']
                                score_away = match['score']['fullTime']['away']
                                emoji_home = api_football.get_flag_emoji(home_name)
                                emoji_away = api_football.get_flag_emoji(away_name)
                                winner_name = home_name if winner == 'HOME_TEAM' else away_name if winner == 'AWAY_TEAM' else "Empate"
                                embed = discord.Embed(title=f"🏁 Resultado: {emoji_home} {home_name} {score_home} - {score_away} {away_name} {emoji_away}", description=f"El ganador fue: **{winner_name}**", color=discord.Color.gold())
                                
                                winners_list = []
                                for p in payouts:
                                    user = self.bot.get_user(p['user_id'])
                                    name = user.mention if user else f"Usuario {p['user_id']}"
                                    if p['won']: winners_list.append(f"✅ {name}: +${p['payout']:.2f}")
                                    else: winners_list.append(f"❌ {name}: -${p['amount_bet']:.2f}")
                                
                                if winners_list:
                                    embed.add_field(name="Resumen de Apuestas", value="\n".join(winners_list), inline=False)
                                
                                await channel.send(embed=embed)
                        
                        # 3. Resolver y Anunciar Parlays (Después de los resultados del partido)
                        await betting.resolve_parlays_for_match(self.bot, match_id, winner)
                        
                        await database.add_or_update_match(match_id, home_name, away_name, status, winner)
            
        except Exception as e:
            print(f"ERROR en check_matches: {e}")

    @check_matches.before_loop
    async def before_check_matches(self):
        await self.bot.wait_until_ready()

    @commands.command(name='debug_resolve')
    @commands.has_permissions(administrator=True)
    async def debug_resolve(self, ctx, match_id: int, winner: str):
        """[ADMIN] Fuerza resolución y envía anuncios."""
        winner = winner.upper()
        await ctx.send(f"⚙️ Procesando resolución manual para ID: {match_id} como {winner}...")
        
        # 1. Resolver apuestas individuales
        payouts = await betting.resolve_match_bets(match_id, winner)
        
        # 2. Resolver parlays (Llamada a la función centralizada)
        await betting.resolve_parlays_for_match(self.bot, match_id, winner)

        # 3. Enviar ANUNCIO del partido (Independiente del Parlay)
        match_info = api_football.get_match_details(match_id)
        home_name = match_info['homeTeam']['name'] if match_info else "Equipo Local"
        away_name = match_info['awayTeam']['name'] if match_info else "Equipo Visitante"
        
        channel_id = os.getenv('ANNOUNCEMENT_CHANNEL_ID')
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                try: channel = await self.bot.fetch_channel(int(channel_id))
                except: channel = None
            
            if channel:
                emoji_home = api_football.get_flag_emoji(home_name)
                emoji_away = api_football.get_flag_emoji(away_name)
                winner_name = home_name if winner == 'HOME_TEAM' else away_name if winner == 'AWAY_TEAM' else "Empate"
                
                embed = discord.Embed(
                    title=f"🏁 [DEBUG] Resultado: {emoji_home} {home_name} vs {away_name} {emoji_away}",
                    description=f"El ganador fue: **{winner_name}**",
                    color=discord.Color.gold()
                )
                
                summary = []
                for p in payouts:
                    user = self.bot.get_user(p['user_id'])
                    if not user:
                        try: user = await self.bot.fetch_user(p['user_id'])
                        except: user = None
                    
                    name = user.mention if user else f"Usuario {p['user_id']}"
                    res = "✅" if p['won'] else "❌"
                    summary.append(f"{res} {name}: ${p['payout']:.2f}")
                
                embed.add_field(name="Resumen de Cobros", value="\n".join(summary) if summary else "Sin apuestas individuales.", inline=False)
                await channel.send(embed=embed)
                await ctx.send("✅ Anuncio enviado al canal configurado.")
        
        await database.add_or_update_match(match_id, home_name, away_name, "FINISHED", winner)
        await ctx.send("✅ Resolución forzada completada.")

async def setup(bot):
    await bot.add_cog(Betting(bot))
