import discord
from discord.ext import commands, tasks
import database
import api_football
import betting
import kalshi_odds
import os
import asyncio
from datetime import datetime, timezone

def _safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(arg) for arg in args)
        print(text.encode("ascii", "replace").decode("ascii"), **kwargs)

async def get_pozo_embed(match_id, bot=None):
    """Helper para construir el Embed del pozo de forma consistente."""
    session = bot.session if bot else None
    match_info = await api_football.get_match_details(match_id, session=session)
    if not match_info:
        return None

    total_bets, pools = await database.get_match_pools(match_id)
    total_pool = total_bets + betting.HOUSE_INJECTION
    
    home = match_info['homeTeam']['name']
    away = match_info['awayTeam']['name']
    
    embed = discord.Embed(
        title=f"📊 Análisis del Pozo: {home} vs {away}",
        description=f"Estado: **{match_info['status']}**\nVolumen Total: **${total_pool:.2f}**",
        color=discord.Color.blue()
    )

    for label, pred_key in [("Local", "HOME_TEAM"), ("Visitante", "AWAY_TEAM"), ("Empate", "DRAW")]:
        amount = pools.get(pred_key, 0)
        multiplier = min(10.0, total_pool / amount if amount > 0 else total_pool / 1.0)
        bar = betting.get_multiplier_bar(multiplier)
        name = home if pred_key == "HOME_TEAM" else away if pred_key == "AWAY_TEAM" else "Empate"
        
        embed.add_field(
            name=f"🔹 {name}",
            value=f"Apostado: `${amount:.2f}`\nCuota: **x{multiplier:.2f}**\n{bar}",
            inline=True
        )

    embed.set_footer(text=f"ID del partido: {match_id} | Inyección de la casa incluida.")
    return embed

class PozoMatchSelect(discord.ui.Select):
    def __init__(self, matches, bot):
        options = [
            discord.SelectOption(
                label=f"{m[1]} vs {m[2]}",
                description=f"Consultar pozo actual",
                value=str(m[0])
            ) for m in matches[:25]
        ]
        super().__init__(placeholder="Selecciona un partido para ver el pozo...", options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        match_id = str(self.values[0])
        embed = await get_pozo_embed(match_id, bot=self.bot)
        if embed:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Error al obtener detalles del pozo.", ephemeral=True)

class PozoMatchView(discord.ui.View):
    def __init__(self, matches, bot):
        super().__init__(timeout=120)
        self.add_item(PozoMatchSelect(matches, bot))

class BetModal(discord.ui.Modal, title='Realizar Apuesta'):
    amount = discord.ui.TextInput(
        label='Cantidad a apostar',
        placeholder='Ejemplo: 50.50',
        min_length=1,
        max_length=10,
    )

    def __init__(self, match_id, team_name, prediction, bot):
        super().__init__()
        self.match_id = match_id
        self.team_name = team_name
        self.prediction = prediction
        self.bot = bot

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

        await interaction.response.defer(ephemeral=True)
        balance = await database.get_user_balance(user_id)
        if balance is None:
            await interaction.followup.send("❌ No estás registrado. Usa `/join` primero.", ephemeral=True)
            return

        # Redondear a 2 decimales para evitar problemas de precisión float (ej: 0.489999 vs 0.49)
        balance_rounded = round(balance, 2)
        amount_rounded = round(amount_val, 2)

        if balance_rounded < (amount_rounded - 0.0001):
            await interaction.followup.send(f"❌ Saldo insuficiente. Tienes **${balance:.2f}**.", ephemeral=True)
            return

        # Verificar si el partido sigue abierto y no ha pasado del min 90
        match_info = await api_football.get_match_details(self.match_id, session=self.bot.session)
        if not match_info or match_info['status'] == 'FINISHED':
            await interaction.followup.send("❌ Este partido ya ha finalizado.", ephemeral=True)
            return

        # --- Candado de Seguridad Minuto 90 ---
        match_minute = api_football.calculate_match_minute(match_info['utcDate'])
        if match_minute >= 90:
            await interaction.followup.send("🔒 **Mercado Suspendido**: El partido está en tiempo de descuento o por terminar. No se permiten más apuestas.", ephemeral=True)
            return

        # Registrar el partido en la DB
        await database.add_or_update_match(
            self.match_id, 
            match_info['homeTeam']['name'], 
            match_info['awayTeam']['name'], 
            match_info['status']
        )
        home_team = match_info['homeTeam']['name']
        away_team = match_info['awayTeam']['name']

        # Registrar apuesta
        odds_source = 'local'
        odds_reference = None
        kalshi_match = await kalshi_odds.get_multiplier(home_team, away_team, self.prediction, session=self.bot.session)
        if kalshi_match:
            locked_multiplier = kalshi_match['multiplier']
            odds_source = 'kalshi'
            odds_reference = kalshi_match.get('market_ticker')
        else:
            locked_multiplier = await database.calculate_locked_multiplier(self.match_id, amount_val, self.prediction)

        await database.place_bet(
            user_id,
            self.match_id,
            amount_val,
            self.prediction,
            locked_multiplier=locked_multiplier,
            odds_source=odds_source,
            odds_reference=odds_reference,
        )
        
        # Borrar el mensaje original de selección para limpiar el chat (UX)
        try:
            await interaction.message.delete()
        except: pass

        
        # Crear embed de confirmación personalizado
        home_emoji = api_football.get_team_flag_emoji(match_info['homeTeam'])
        away_emoji = api_football.get_team_flag_emoji(match_info['awayTeam'])

        confirm_embed = discord.Embed(title="✅ Apuesta Confirmada", color=discord.Color.green())
        source_text = "Kalshi" if odds_source == 'kalshi' else "Pozo local"
        confirm_embed.description = f"Has apostado **${amount_val:.2f}** a **{self.team_name}** en el partido:\n{home_emoji} **{home_team} vs {away_team}** {away_emoji}\nCuota congelada: **x{locked_multiplier:.2f}**\nFuente: **{source_text}**"
        
        embeds = [confirm_embed]
        if odds_source != 'kalshi':
            embed_pozo = await get_pozo_embed(self.match_id, bot=self.bot)
            if embed_pozo:
                embeds.append(embed_pozo)

        await interaction.followup.send(embeds=embeds, ephemeral=True)

class ParlayPozoView(discord.ui.View):
    """Vista para mostrar los pozos de un parlay de forma bajo demanda."""
    def __init__(self, match_ids, bot):
        super().__init__(timeout=120)
        self.match_ids = match_ids
        self.bot = bot

    @discord.ui.button(label="🔍 Ver Pozos de mis Partidos", style=discord.ButtonStyle.secondary)
    async def view_pozos(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embeds = []
        for m_id in self.match_ids:
            embed = await get_pozo_embed(m_id, bot=self.bot)
            if embed:
                embeds.append(embed)
        
        if embeds:
            # Discord permite enviar hasta 10 embeds por mensaje
            await interaction.followup.send(content="📊 Aquí tienes el estado actual de los pozos en tu parlay:", embeds=embeds[:10], ephemeral=True)
        else:
            await interaction.followup.send("❌ No se pudieron cargar los pozos.", ephemeral=True)

class ParlayAmountModal(discord.ui.Modal, title='Monto del Parlay'):
    amount = discord.ui.TextInput(
        label='Cantidad total a apostar',
        placeholder='Ejemplo: 20.00',
        min_length=1,
        max_length=10,
    )

    def __init__(self, legs, bot):
        super().__init__()
        self.legs = legs # List of (match_id, prediction, home_name, away_name)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            amount_val = float(self.amount.value)
        except ValueError:
            await interaction.response.send_message("❌ Monto inválido.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        balance = await database.get_user_balance(user_id)
        if balance < amount_val:
            await interaction.followup.send("❌ Saldo insuficiente.", ephemeral=True)
            return

        # --- Candado de Seguridad Minuto 90 para Parlays ---
        match_ids = []
        for m_id, pred, home, away in self.legs:
            match_ids.append(m_id)
            match_info = await api_football.get_match_details(m_id, session=self.bot.session)
            if not match_info: continue
            
            if match_info['status'] == 'FINISHED':
                await interaction.followup.send(f"❌ El partido **{home} vs {away}** ya ha terminado.", ephemeral=True)
                return
            
            match_minute = api_football.calculate_match_minute(match_info['utcDate'])
            if match_minute >= 90:
                await interaction.followup.send(f"🔒 **Mercado Suspendido**: El partido **{home} vs {away}** está terminando. No se pueden crear parlays con este juego.", ephemeral=True)
                return

        # Registrar parlay
        legs_db = [(l[0], l[1]) for l in self.legs]
        await database.place_parlay(user_id, amount_val, legs_db)

        # Borrar el menú de construcción para mantener limpio el chat
        try:
            await interaction.message.delete()
        except: pass

        embed = discord.Embed(title="🚀 Parlay Confirmado", color=discord.Color.gold())
        embed.add_field(name="Monto Total", value=f"${amount_val:.2f}", inline=False)
        
        legs_text = ""
        for _, pred, home, away in self.legs:
            pred_text = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
            legs_text += f"• **{home} vs {away}**: {pred_text}\n"
        
        embed.add_field(name="Combinaciones", value=legs_text, inline=False)
        embed.set_footer(text="¡Ganas si aciertas todas las predicciones!")
        
        # Opción B: Mostrar botón para ver pozos
        view = ParlayPozoView(match_ids, self.bot)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class ParlayBuilderView(discord.ui.View):
    def __init__(self, matches, user_id, bot):
        super().__init__(timeout=300)
        self.matches = matches
        self.user_id = user_id
        self.bot = bot
        self.selected_legs = [] # List of (match_id, prediction, home, away)
        self.add_item(ParlayMatchSelect(matches))

    @discord.ui.button(label="✅ Confirmar Parlay", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta no es tu sesión de Parlay.", ephemeral=True)
            return
        if not self.selected_legs:
            await interaction.response.send_message("❌ Debes seleccionar al menos un partido.", ephemeral=True)
            return
        if len(self.selected_legs) < 2:
            await interaction.response.send_message("❌ Un parlay necesita al menos 2 partidos.", ephemeral=True)
            return
            
        await interaction.response.send_modal(ParlayAmountModal(self.selected_legs, self.bot))

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("No puedes cerrar este menú.", ephemeral=True)
            return
        try:
            await interaction.message.delete()
        except:
            await interaction.response.send_message("Operación cancelada.", ephemeral=True)

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
        if interaction.user.id != self.view.user_id:
            await interaction.response.send_message("Esta no es tu sesión.", ephemeral=True)
            return

        match_id = str(self.values[0])
        match_info = await api_football.get_match_details(match_id, session=self.view.bot.session)
        
        home = match_info['homeTeam']['name']
        away = match_info['awayTeam']['name']
        
        view = discord.ui.View()
        btn_home = discord.ui.Button(label=f"Ganador: {home}", style=discord.ButtonStyle.primary)
        btn_draw = discord.ui.Button(label="Empate", style=discord.ButtonStyle.secondary)
        btn_away = discord.ui.Button(label=f"Ganador: {away}", style=discord.ButtonStyle.danger)
        btn_cancel = discord.ui.Button(label="❌ Cancelar", style=discord.ButtonStyle.gray)

        async def add_leg(inter, pred):
            self.view.selected_legs = [l for l in self.view.selected_legs if l[0] != match_id]
            self.view.selected_legs.append((match_id, pred, home, away))
            legs_text = "\n".join([f"✅ {l[2]} vs {l[3]} (**{l[1]}**)" for l in self.view.selected_legs])
            embed = discord.Embed(title="🏗️ Construyendo Parlay", description=f"Selecciones actuales:\n{legs_text}", color=discord.Color.blue())
            await inter.response.edit_message(embed=embed, view=self.view)

        async def cancel_leg(inter):
            try:
                await inter.message.delete()
            except:
                await inter.response.edit_message(content="Selección cancelada.", view=None)

        btn_home.callback = lambda i: add_leg(i, "HOME_TEAM")
        btn_draw.callback = lambda i: add_leg(i, "DRAW")
        btn_away.callback = lambda i: add_leg(i, "AWAY_TEAM")
        btn_cancel.callback = cancel_leg
        
        view.add_item(btn_home)
        view.add_item(btn_draw)
        view.add_item(btn_away)
        view.add_item(btn_cancel)
        
        await interaction.response.send_message(f"¿Qué resultado predices para **{home} vs {away}**?", view=view, ephemeral=True)

class MatchSelect(discord.ui.Select):
    def __init__(self, matches, user_id, bot):
        options = [
            discord.SelectOption(
                label=f"{m['homeTeam']['name']} vs {m['awayTeam']['name']}",
                description=f"Fecha: {m['utcDate'][:10]}",
                value=str(m['id'])
            ) for m in matches
        ]
        super().__init__(placeholder="Selecciona un partido para apostar...", options=options)
        self.user_id = user_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("No puedes interactuar con el menú de otro usuario.", ephemeral=True)
            return

        match_id = str(self.values[0])
        match_info = await api_football.get_match_details(match_id, session=self.bot.session)
        
        home = match_info['homeTeam']['name']
        away = match_info['awayTeam']['name']
        home_emoji = api_football.get_team_flag_emoji(match_info['homeTeam'])
        away_emoji = api_football.get_team_flag_emoji(match_info['awayTeam'])
        
        embed = discord.Embed(
            title=f"🏆 {home_emoji} {home} vs {away} {away_emoji}",
            description=f"Estado: **{match_info['status']}**\nID: `{match_id}`",
            color=discord.Color.green()
        )
        flag = api_football.get_team_flag_url(match_info['homeTeam'])
        if flag:
            embed.set_thumbnail(url=flag)
        
        view = discord.ui.View(timeout=None)
        btn_home = discord.ui.Button(label=home, style=discord.ButtonStyle.primary)
        btn_draw = discord.ui.Button(label="Empate", style=discord.ButtonStyle.secondary)
        btn_away = discord.ui.Button(label=away, style=discord.ButtonStyle.danger)
        btn_cancel = discord.ui.Button(label="❌ Cancelar", style=discord.ButtonStyle.gray)

        async def make_bet_callback(inter, team, pred):
            await inter.response.send_modal(BetModal(match_id, team, pred, self.bot))

        async def cancel_callback(inter):
            try:
                await inter.message.delete()
            except:
                # Si es efímero y no se puede borrar, al menos quitamos la vista
                await inter.response.edit_message(content="Menú cerrado.", embed=None, view=None)

        btn_home.callback = lambda i: make_bet_callback(i, home, "HOME_TEAM")
        btn_draw.callback = lambda i: make_bet_callback(i, "Empate", "DRAW")
        btn_away.callback = lambda i: make_bet_callback(i, away, "AWAY_TEAM")
        btn_cancel.callback = cancel_callback

        view.add_item(btn_home)
        view.add_item(btn_draw)
        view.add_item(btn_away)
        view.add_item(btn_cancel)

        await interaction.response.edit_message(content=None, embed=embed, view=view)

class BettingView(discord.ui.View):
    def __init__(self, matches, user_id, bot):
        super().__init__(timeout=180)
        self.add_item(MatchSelect(matches, user_id, bot))

async def get_kalshi_embed(match_info, bot):
    home_team = match_info['homeTeam']['name']
    away_team = match_info['awayTeam']['name']
    odds = await kalshi_odds.get_multipliers(home_team, away_team, session=bot.session)

    embed = discord.Embed(
        title=f"Kalshi: {home_team} vs {away_team}",
        description=f"Estado: **{match_info['status']}**\nID: `{match_info['id']}`",
        color=discord.Color.green()
    )

    labels = {
        'HOME_TEAM': home_team,
        'DRAW': 'Empate',
        'AWAY_TEAM': away_team,
    }
    for prediction, label in labels.items():
        match = odds.get(prediction)
        if match:
            value = f"Multiplicador: **x{match['multiplier']:.2f}**\nMercado: `{match.get('market_ticker') or 'N/A'}`"
        else:
            value = "Sin mercado Kalshi encontrado."
        embed.add_field(name=label, value=value, inline=True)

    embed.set_footer(text="Solo informativo. La cuota final se congela al apostar.")
    return embed

class KalshiMatchSelect(discord.ui.Select):
    def __init__(self, matches, user_id, bot):
        options = [
            discord.SelectOption(
                label=f"{m['homeTeam']['name']} vs {m['awayTeam']['name']}",
                description=f"Fecha: {m['utcDate'][:10]}",
                value=str(m['id'])
            ) for m in matches[:25]
        ]
        super().__init__(placeholder="Selecciona un partido para ver Kalshi...", options=options)
        self.user_id = user_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("No puedes interactuar con el menú de otro usuario.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        match_id = str(self.values[0])
        match_info = await api_football.get_match_details(match_id, session=self.bot.session)
        if not match_info:
            await interaction.followup.send("No se pudo obtener el partido seleccionado.", ephemeral=True)
            return

        embed = await get_kalshi_embed(match_info, self.bot)
        await interaction.followup.send(embed=embed, ephemeral=True)

class KalshiMatchView(discord.ui.View):
    def __init__(self, matches, user_id, bot):
        super().__init__(timeout=180)
        self.add_item(KalshiMatchSelect(matches, user_id, bot))

class CashoutSelect(discord.ui.Select):
    def __init__(self, items, is_parlay=False, user_id=None, bot=None):
        options = []
        if not is_parlay:
            for item in items:
                home, away, amount, pred, m_id = item[:5]
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
        self.user_id = user_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("No puedes cobrar las apuestas de otros.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        val_parts = self.values[0].split('_')
        prefix = val_parts[0]
        # match_id/parlay_id es val_parts[1], amount es val_parts[2]
        raw_id = val_parts[1]
        amount = float(val_parts[2])
        return_amount = amount * 0.8
        
        if prefix == 'ind':
            match_id = raw_id # Mantener como string para FIFA IDs
            match_info = await api_football.get_match_details(match_id, session=self.bot.session)
            if not match_info:
                await interaction.followup.send("No se pudo verificar el estado del partido. Intenta de nuevo en unos segundos.", ephemeral=True)
                return
            if match_info and match_info['status'] == 'FINISHED':
                await interaction.followup.send("❌ El partido ya terminó.", ephemeral=True)
                return
            
            # Bloqueo minuto 90 para cashout
            utc_date = match_info.get('utcDate')
            if not utc_date:
                await interaction.followup.send("No se pudo calcular el minuto del partido. Cashout no disponible por ahora.", ephemeral=True)
                return

            match_minute = api_football.calculate_match_minute(utc_date)
            if match_minute >= 90:
                await interaction.followup.send("🔒 **Mercado Suspendido**: El partido está terminando. Cashout deshabilitado.", ephemeral=True)
                return

            await database.remove_bet(user_id, match_id)
        else:
            parlay_id = int(raw_id) # Parlay ID sigue siendo numérico (autoincrement)
            await database.remove_parlay(user_id, parlay_id)

        await database.update_balance(user_id, return_amount)
        
        # Limpiar menú de cashout
        try:
            await interaction.message.edit(content="✅ Cashout completado.", view=None, embed=None)
        except: pass

        await interaction.followup.send(embed=discord.Embed(title="💰 Cashout Exitoso", description=f"Has recuperado **${return_amount:.2f}**.", color=discord.Color.gold()), ephemeral=True)

class CashoutView(discord.ui.View):
    def __init__(self, user_id, bot):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.bot = bot

    @discord.ui.button(label="Apuestas Individuales", style=discord.ButtonStyle.primary)
    async def individual(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Maneja tu propio menú.", ephemeral=True)
            return
        bets = await database.get_user_active_bets(self.user_id)
        if not bets:
            await interaction.response.send_message("Sin apuestas activas.", ephemeral=True)
            return
        view = discord.ui.View()
        view.add_item(CashoutSelect(bets, False, self.user_id, self.bot))
        await interaction.response.edit_message(content="Elige la apuesta:", view=view)

    @discord.ui.button(label="Parlays (Combinadas)", style=discord.ButtonStyle.secondary)
    async def parlay(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Maneja tu propio menú.", ephemeral=True)
            return
        parlays = await database.get_user_active_parlays(self.user_id)
        if not parlays:
            await interaction.response.send_message("Sin parlays activos.", ephemeral=True)
            return
        view = discord.ui.View()
        view.add_item(CashoutSelect(parlays, True, self.user_id, self.bot))
        await interaction.response.edit_message(content="Elige el parlay:", view=view)

class Betting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Consolidado: Una sola tarea que revisa todo cada minuto
        self.match_processor.start()

    def cog_unload(self):
        self.match_processor.cancel()

    @tasks.loop(seconds=10)
    async def match_processor(self):
        """Tarea UNIFICADA para actualizar marcadores y resolver partidos."""
        try:
            # 1. Obtener partidos con apuestas activas
            active_matches_db = await database.get_active_matches_with_names()
            if not active_matches_db:
                return

            _safe_print(f"🔍 [PROCESSOR] Revisando {len(active_matches_db)} partidos activos...")

            # 2. ÚNICA CONSULTA A LA API: Obtener todos los partidos de la competición
            # Para ahorrar llamadas, traemos todos los de la competición configurada
            comp = os.getenv('COMPETITION_CODE', 'WC')
            url_all = f"{api_football.BASE_URL}/competitions/{comp}/matches"
            data_all = await api_football.fetch_json(url_all, session=self.bot.session)
            
            if not data_all or 'matches' not in data_all:
                _safe_print("⚠️ No se pudo obtener la lista de partidos de la API.")
                return

            all_fifa_matches = data_all['matches']
            channel_id_env = os.getenv('ANNOUNCEMENT_CHANNEL_ID')
            channel = None
            if channel_id_env:
                c_id = int(str(channel_id_env).strip().strip('"').strip("'"))
                channel = self.bot.get_channel(c_id) or await self.bot.fetch_channel(c_id)

            for internal_match in active_matches_db:
                m_id, home_db, away_db = internal_match
                
                # Buscar el partido correspondiente en la respuesta de la API
                f_match = next((m for m in all_fifa_matches if str(m['id']) == str(m_id)), None)
                if not f_match:
                    continue

                f_status = f_match['status']
                f_home = f_match['homeTeam']['name']
                f_away = f_match['awayTeam']['name']
                f_score = f"{f_match['score']['fullTime']['home']}-{f_match['score']['fullTime']['away']}"
                
                # Calcular minuto para el log
                f_minute = api_football.calculate_match_minute(f_match['utcDate'])
                _safe_print(f"⚽ [LOG] {f_home} {f_score} {f_away} ({f_status}) - Min: {f_minute:.1f}'")

                # --- CASO A: PARTIDO FINALIZADO ---
                if f_status == 'FINISHED':
                    winner = f_match['score']['winner']
                    if winner:
                        # Resolver y pagar
                        payouts = await betting.resolve_match_bets(self.bot, m_id, winner)
                        if payouts is None: continue # Ya resuelto

                        await betting.resolve_parlays_for_match(self.bot, m_id, winner)
                        await database.add_or_update_match(m_id, f_home, f_away, 'FINISHED', winner)

                        # Limpiar marcador en vivo
                        live_info = await database.get_live_msg_info(m_id)
                        if live_info and live_info[0] and channel:
                            try:
                                msg = await channel.fetch_message(live_info[0])
                                await msg.delete()
                                await database.update_live_msg_info(m_id, None, None)
                            except: pass

                        # Anunciar resultado
                        if channel:
                            winner_display = f_home if winner == 'HOME_TEAM' else f_away if winner == 'AWAY_TEAM' else "Empate"
                            embed_res = discord.Embed(title=f"🏁 Finalizado: {f_home} vs {f_away}", description=f"El ganador fue: **{winner_display}** ({f_score})", color=discord.Color.gold())
                            summary = [f"{'✅' if p['won'] else '❌'} {(self.bot.get_user(p['user_id']) or await self.bot.fetch_user(p['user_id'])).mention}: ${p['payout']:.2f}" for p in payouts]
                            if summary: embed_res.add_field(name="Resumen de Cobros", value="\n".join(summary), inline=False)
                            await channel.send(embed=embed_res)
                    continue

                # --- CASO B: PARTIDO EN VIVO ---
                if f_status in ['IN_PLAY', 'PAUSED', 'LIVE']:
                    if not channel: continue
                    
                    live_info = await database.get_live_msg_info(m_id)
                    msg_id = live_info[0] if live_info else None
                    last_score = live_info[1] if live_info else None

                    emoji_h = api_football.get_team_flag_emoji(f_match['homeTeam'])
                    emoji_a = api_football.get_team_flag_emoji(f_match['awayTeam'])
                    embed_live = discord.Embed(title=f"🏟️ EN VIVO: {emoji_h} {f_home} vs {f_away} {emoji_a}", description=f"Marcador Actual: **{f_score}**", color=discord.Color.red())

                    if msg_id:
                        if f_score != last_score:
                            try:
                                msg = await channel.fetch_message(msg_id)
                                await msg.edit(embed=embed_live)
                                await database.update_live_msg_info(m_id, msg_id, f_score)
                                _safe_print(f"📝 Marcador editado: {f_home} {f_score} {f_away}")
                            except discord.NotFound:
                                new_msg = await channel.send(embed=embed_live)
                                await database.update_live_msg_info(m_id, new_msg.id, f_score)
                            except: pass
                    else:
                        new_msg = await channel.send(embed=embed_live)
                        await database.update_live_msg_info(m_id, new_msg.id, f_score)
                        _safe_print(f"📣 Nuevo marcador enviado: {f_home} vs {f_away}")

        except Exception as e:
            _safe_print(f"Error en match_processor: {e}")

    @match_processor.before_loop
    async def before_match_processor(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name='matches')
    async def matches(self, ctx):
        """Muestra los próximos partidos disponibles para apostar."""
        await ctx.defer(ephemeral=True)
        upcoming = await api_football.get_upcoming_matches(session=self.bot.session)
        if not upcoming:
            await ctx.send("⚽ No hay partidos próximos programados en este momento.", ephemeral=True)
            return
        
        view = BettingView(upcoming[:25], ctx.author.id, self.bot)
        embed = discord.Embed(title="📅 Próximos Partidos", description="Selecciona un partido para realizar tu apuesta.", color=discord.Color.blue())
        await ctx.send(embed=embed, view=view, ephemeral=True)


    @commands.hybrid_command(name='kalshi')
    async def kalshi(self, ctx):
        """Consulta multiplicadores Kalshi para un partido."""
        await ctx.defer(ephemeral=True)
        upcoming = await api_football.get_upcoming_matches(session=self.bot.session)
        if not upcoming:
            await ctx.send("No hay partidos proximos disponibles para consultar.", ephemeral=True)
            return

        view = KalshiMatchView(upcoming[:25], ctx.author.id, self.bot)
        embed = discord.Embed(
            title="Consulta Kalshi",
            description="Selecciona un partido para ver los multiplicadores disponibles.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed, view=view, ephemeral=True)
    @commands.hybrid_command(name='apuestas')
    async def apuestas(self, ctx):
        """Muestra tus apuestas individuales activas."""
        await ctx.defer(ephemeral=True)
        bets = await database.get_user_active_bets(ctx.author.id)
        if not bets:
            await ctx.send("📝 No tienes apuestas individuales activas.", ephemeral=True)
            return

        embed = discord.Embed(title="📋 Tus Apuestas Activas", color=discord.Color.blue())
        for bet in bets:
            home, away, amount, pred, m_id = bet[:5]
            locked_multiplier = bet[5] if len(bet) > 5 else None
            odds_source = bet[6] if len(bet) > 6 else None
            pred_display = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
            multiplier_text = f"\nCuota: **x{locked_multiplier:.2f}**" if locked_multiplier else ""
            source_text = f"\nFuente: **{'Kalshi' if odds_source == 'kalshi' else 'Pozo local'}**" if odds_source else ""
            embed.add_field(
                name=f"{home} vs {away}",
                value=f"Apostado: **${amount:.2f}**\nPredicción: **{pred_display}**{multiplier_text}{source_text}\nID: `{m_id}`",
                inline=False
            )
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='parlay')
    async def parlay(self, ctx):
        """Crea una apuesta combinada (Parlay) para aumentar tus ganancias."""
        await ctx.defer(ephemeral=True)
        upcoming = await api_football.get_upcoming_matches(session=self.bot.session)
        if not upcoming or len(upcoming) < 2:
            await ctx.send("⚽ Se necesitan al menos 2 partidos próximos para crear un parlay.", ephemeral=True)
            return
        
        view = ParlayBuilderView(upcoming[:25], ctx.author.id, self.bot)
        embed = discord.Embed(
            title="🏗️ Creador de Parlays", 
            description="Selecciona al menos 2 partidos. ¡Debes acertar todos para ganar!", 
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name='mis_parlays')
    async def mis_parlays(self, ctx):
        """Muestra tus parlays (apuestas combinadas) activos."""
        await ctx.defer(ephemeral=True)
        parlays = await database.get_user_active_parlays(ctx.author.id)
        if not parlays:
            await ctx.send("🚀 No tienes parlays activos.", ephemeral=True)
            return

        embed = discord.Embed(title="🚀 Tus Parlays Activos", color=discord.Color.gold())
        for p in parlays:
            legs_text = ""
            for home, away, pred, status in p['legs']:
                res_icon = "⏳" if status == 'PENDING' else "✅" if status == 'WON' else "❌"
                pred_text = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
                legs_text += f"{res_icon} **{home} vs {away}**: {pred_text}\n"
            
            embed.add_field(
                name=f"Parlay #{p['id']} - Monto: ${p['amount']:.2f}",
                value=legs_text or "Sin detalles",
                inline=False
            )
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='cashout')
    async def cashout(self, ctx):
        """Cancela una apuesta activa y recupera el 80% de lo invertido."""
        view = CashoutView(ctx.author.id, self.bot)
        await ctx.send("💰 **Menú de Cashout**: ¿Qué tipo de apuesta deseas retirar?", view=view, ephemeral=True)

    @commands.hybrid_command(name='vivo')
    async def vivo(self, ctx):
        """Muestra los partidos que se están jugando ahora y permite apostar."""
        await ctx.defer(ephemeral=True)
        live_data = await api_football.fetch_fifa_live_scores(session=self.bot.session)
        matches = live_data.get('matches', []) if live_data else []
        
        if not matches:
            await ctx.send("⚽ No hay partidos en vivo disponibles para apostar en este momento.", ephemeral=True)
            return
        
        view = BettingView(matches[:25], ctx.author.id, self.bot)
        embed = discord.Embed(
            title="🏟️ Partidos EN VIVO", 
            description="Estos partidos ya empezaron pero aún puedes apostar hasta el minuto 90.", 
            color=discord.Color.red()
        )
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name='pozo')
    async def pozo(self, ctx, match_id: str = None):
        """Consulta el estado del pozo y las cuotas de un partido."""
        await ctx.defer(ephemeral=True)
        if match_id:
            embed = await get_pozo_embed(match_id, bot=self.bot)
            if embed:
                await ctx.send(embed=embed, ephemeral=True)
            else:
                await ctx.send(f"❌ No se encontró información para el partido `{match_id}`.", ephemeral=True)
        else:
            # Mostrar lista de partidos activos en la DB
            active = await database.get_active_matches_with_names()
            if not active:
                await ctx.send("📊 No hay pozos activos con apuestas en este momento.", ephemeral=True)
                return
            
            view = PozoMatchView(active, self.bot)
            await ctx.send("📊 Selecciona un partido para ver su pozo actual:", view=view, ephemeral=True)

    @commands.hybrid_command(name='historial')
    async def historial(self, ctx):
        """Muestra tus últimas 10 apuestas resueltas."""
        await ctx.defer(ephemeral=True)
        history = await database.get_user_history(ctx.author.id)
        if not history:
            await ctx.send("📜 Aún no tienes un historial de apuestas resueltas.", ephemeral=True)
            return

        embed = discord.Embed(title="📜 Tu Historial de Apuestas", color=discord.Color.purple())
        for home, away, amount, pred, payout, won, winner in history:
            icon = "✅" if won else "❌"
            res_text = f"Ganaste: **${payout:.2f}**" if won else "Perdiste"
            pred_text = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
            embed.add_field(
                name=f"{icon} {home} vs {away}",
                value=f"Apostaste: `${amount:.2f}` a **{pred_text}**\n{res_text}",
                inline=False
            )
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='historial_all')
    async def historial_all(self, ctx):
        """Muestra las últimas apuestas resueltas de todos los usuarios."""
        await ctx.defer(ephemeral=True)
        history = await database.get_global_history(15)
        if not history:
            await ctx.send("📜 No hay historial global disponible.", ephemeral=True)
            return

        embed = discord.Embed(title="🌎 Historial Global de Apuestas", color=discord.Color.purple())
        for u_id, home, away, amount, pred, payout, won, winner in history:
            user = self.bot.get_user(u_id)
            name = user.name if user else f"Usuario {u_id}"
            icon = "✅" if won else "❌"
            embed.add_field(
                name=f"{icon} {name}",
                value=f"**{home} vs {away}**\n${amount:.2f} -> ${payout:.2f}",
                inline=True
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='debug_resolve')
    @commands.has_permissions(administrator=True)
    async def debug_resolve(self, ctx, match_id: str, winner: str):
        """[ADMIN] Fuerza resolución manual de un partido y anuncia el resultado."""
        winner = winner.upper()
        if winner not in ['HOME_TEAM', 'AWAY_TEAM', 'DRAW']:
            await ctx.send("❌ Ganador inválido. Usa: HOME_TEAM, AWAY_TEAM o DRAW", ephemeral=True)
            return

        # 1. Obtener info del partido antes de resolver
        m_info = await database.get_match_by_id(match_id)
        if not m_info:
            await ctx.send(f"❌ No se encontró el partido con ID `{match_id}` en la DB.", ephemeral=True)
            return
        
        home_name, away_name = m_info[1], m_info[2]

        # 2. Ejecutar pagos
        payouts = await betting.resolve_match_bets(self.bot, match_id, winner)
        await betting.resolve_parlays_for_match(self.bot, match_id, winner)
        await database.add_or_update_match(match_id, home_name, away_name, 'FINISHED', winner)

        # 3. Anuncio en el canal de goles
        channel_id_env = os.getenv('ANNOUNCEMENT_CHANNEL_ID')
        if channel_id_env:
            try:
                channel_id = int(str(channel_id_env).strip().strip('"').strip("'"))
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                if channel:
                    winner_display = home_name if winner == 'HOME_TEAM' else away_name if winner == 'AWAY_TEAM' else "Empate"
                    embed_res = discord.Embed(
                        title=f"🏁 Finalizado (Manual): {home_name} vs {away_name}", 
                        description=f"El ganador oficial fue: **{winner_display}**", 
                        color=discord.Color.gold()
                    )
                    summary = []
                    for p in payouts:
                        user = self.bot.get_user(p['user_id']) or await self.bot.fetch_user(p['user_id'])
                        name = user.mention if user else f"Usuario {p['user_id']}"
                        res_icon = "✅" if p['won'] else "❌"
                        summary.append(f"{res_icon} {name}: ${p['payout']:.2f}")
                    
                    if summary:
                        embed_res.add_field(name="Resumen de Cobros", value="\n".join(summary), inline=False)
                    
                    await channel.send(embed=embed_res)
            except Exception as e:
                _safe_print(f"Error al anunciar debug_resolve: {e}")

        await ctx.send(f"✅ Partido `{home_name} vs {away_name}` resuelto como `{winner}` y anunciado.", ephemeral=True)

    @commands.command(name='debug_finalizar')
    @commands.has_permissions(administrator=True)
    async def debug_finalizar_prefix(self, ctx, match_id: str, winner: str):
        """[ADMIN] Comando con prefijo (!) para forzar resolución manual."""
        await self.debug_resolve(ctx, match_id, winner)

async def setup(bot): await bot.add_cog(Betting(bot))
