import discord
from discord.ext import commands, tasks
import database
import api_football
import betting
import os
import asyncio
from datetime import datetime, timezone

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

        balance = await database.get_user_balance(user_id)
        if balance is None:
            await interaction.response.send_message("❌ No estás registrado. Usa `/join` primero.", ephemeral=True)
            return

        # Redondear a 2 decimales para evitar problemas de precisión float (ej: 0.489999 vs 0.49)
        balance_rounded = round(balance, 2)
        amount_rounded = round(amount_val, 2)

        if balance_rounded < (amount_rounded - 0.0001):
            await interaction.response.send_message(f"❌ Saldo insuficiente. Tienes **${balance:.2f}**.", ephemeral=True)
            return

        # Verificar si el partido sigue abierto y no ha pasado del min 90
        match_info = await api_football.get_match_details(self.match_id, session=self.bot.session)
        if not match_info or match_info['status'] == 'FINISHED':
            await interaction.response.send_message("❌ Este partido ya ha finalizado.", ephemeral=True)
            return

        # --- Candado de Seguridad Minuto 90 ---
        match_minute = api_football.calculate_match_minute(match_info['utcDate'])
        if match_minute >= 90:
            await interaction.response.send_message("🔒 **Mercado Suspendido**: El partido está en tiempo de descuento o por terminar. No se permiten más apuestas.", ephemeral=True)
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
        
        # Borrar el mensaje original de selección para limpiar el chat (UX)
        try:
            await interaction.message.delete()
        except: pass

        # Obtener el pozo actualizado
        embed_pozo = await get_pozo_embed(self.match_id, bot=self.bot)
        
        # Crear embed de confirmación personalizado
        home_team = match_info['homeTeam']['name']
        away_team = match_info['awayTeam']['name']
        home_emoji = api_football.get_flag_emoji(home_team)
        away_emoji = api_football.get_flag_emoji(away_team)

        confirm_embed = discord.Embed(title="✅ Apuesta Confirmada", color=discord.Color.green())
        confirm_embed.description = f"Has apostado **${amount_val:.2f}** a **{self.team_name}** en el partido:\n{home_emoji} **{home_team} vs {away_team}** {away_emoji}"
        
        # Enviamos ambos embeds: el de confirmación y el del pozo actual
        await interaction.response.send_message(embeds=[confirm_embed, embed_pozo], ephemeral=True)

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

        balance = await database.get_user_balance(user_id)
        if balance < amount_val:
            await interaction.response.send_message("❌ Saldo insuficiente.", ephemeral=True)
            return

        # --- Candado de Seguridad Minuto 90 para Parlays ---
        match_ids = []
        for m_id, pred, home, away in self.legs:
            match_ids.append(m_id)
            match_info = await api_football.get_match_details(m_id, session=self.bot.session)
            if not match_info: continue
            
            if match_info['status'] == 'FINISHED':
                await interaction.response.send_message(f"❌ El partido **{home} vs {away}** ya ha terminado.", ephemeral=True)
                return
            
            match_minute = api_football.calculate_match_minute(match_info['utcDate'])
            if match_minute >= 90:
                await interaction.response.send_message(f"🔒 **Mercado Suspendido**: El partido **{home} vs {away}** está terminando. No se pueden crear parlays con este juego.", ephemeral=True)
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
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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

class CashoutSelect(discord.ui.Select):
    def __init__(self, items, is_parlay=False, user_id=None, bot=None):
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
        self.user_id = user_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("No puedes cobrar las apuestas de otros.", ephemeral=True)
            return

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
            if match_info and match_info['status'] == 'FINISHED':
                await interaction.response.send_message("❌ El partido ya terminó.", ephemeral=True)
                return
            
            # Bloqueo minuto 90 para cashout
            match_minute = api_football.calculate_match_minute(match_info['utcDate'])
            if match_minute >= 90:
                await interaction.response.send_message("🔒 **Mercado Suspendido**: El partido está terminando. Cashout deshabilitado.", ephemeral=True)
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

        await interaction.response.send_message(embed=discord.Embed(title="💰 Cashout Exitoso", description=f"Has recuperado **${return_amount:.2f}**.", color=discord.Color.gold()), ephemeral=True)

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
        self._last_check_time = 0
        self.check_matches.start()
        self.fast_score_update.start()

    def cog_unload(self):
        self.check_matches.cancel()
        self.fast_score_update.cancel()

    @tasks.loop(minutes=1)
    async def fast_score_update(self):
        """Tarea de frecuencia moderada (1min) para actualizar marcadores y cerrar partidos."""
        try:
            channel_id_env = os.getenv('ANNOUNCEMENT_CHANNEL_ID')
            if not channel_id_env: return

            # Obtener partidos con apuestas activas y sus nombres
            active_matches = await database.get_active_matches_with_names()
            if not active_matches: 
                # print("DEBUG: No hay apuestas activas en este ciclo.")
                return

            print(f"🔍 [DEBUG] Procesando {len(active_matches)} partidos activos...")

            # 1. Revisar partidos en vivo (LIVE)
            data_live = await api_football.fetch_fifa_live_scores(session=self.bot.session)
            fifa_live = data_live.get('matches', []) if data_live else []
            
            # 2. Revisar partidos terminados (FINISHED)
            data_finished = await api_football.fetch_fifa_finished_matches(session=self.bot.session)
            fifa_finished = data_finished.get('matches', []) if data_finished else []
            
            # Combinar para procesamiento
            all_fifa = fifa_live + fifa_finished
            if not all_fifa: 
                print("DEBUG: La API de la FIFA no devolvió partidos LIVE ni FINISHED.")
                return

            channel_id = int(str(channel_id_env).strip().strip('"').strip("'"))
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            if not channel: return

            for f_match in all_fifa:
                f_home = f_match['homeTeam']['name']
                f_away = f_match['awayTeam']['name']
                f_score = f"{f_match['score']['fullTime']['home']}-{f_match['score']['fullTime']['away']}"
                f_status = f_match['status']
                
                # Buscar si este partido de FIFA coincide con uno de nuestros partidos apostados
                # Intentamos primero por ID (más preciso) y luego por nombre si falla
                internal_match = next((m for m in active_matches if str(m[0]) == str(f_match['id'])), None)
                if not internal_match:
                    internal_match = next((m for m in active_matches if m[1] == f_home and m[2] == f_away), None)
                
                if not internal_match: continue

                m_id = internal_match[0]
                print(f"⚽ [UPDATE] {f_home} {f_score} {f_away} ({f_status})")
                
                # Si el partido ha terminado en la FIFA API, forzar resolución
                if f_status == 'FINISHED':
                    print(f"🏁 [CIERRE RÁPIDO - FIFA API] {f_home} vs {f_away} detectado como FINISHED.")
                    
                    # 1. Obtener info del mensaje ANTES de actualizar/resolver (evita que se pierda la referencia)
                    live_info = await database.get_live_msg_info(m_id)
                    
                    winner = f_match['score']['winner']
                    if winner:
                        # 2. Resolver apuestas y actualizar DB
                        payouts = await betting.resolve_match_bets(self.bot, m_id, winner)
                        if payouts is None: continue # Ya fue procesado por otro hilo (ej: check_matches)

                        await betting.resolve_parlays_for_match(self.bot, m_id, winner)
                        await database.add_or_update_match(m_id, f_home, f_away, 'FINISHED', winner)
                        
                        # 3. Limpiar mensaje en vivo usando la info guardada
                        if live_info and live_info[0]:
                            try:
                                msg = await channel.fetch_message(live_info[0])
                                await msg.delete()
                                await database.update_live_msg_info(m_id, None, None)
                                print(f"🗑️ [MSG] Marcador borrado (Cierre Rápido): {f_home} vs {f_away}")
                            except Exception as e:
                                print(f"⚠️ No se pudo borrar el mensaje {live_info[0]}: {e}")
                        
                        # Anuncio de resultado
                        winner_name = f_home if winner == 'HOME_TEAM' else f_away if winner == 'AWAY_TEAM' else "Empate"
                        embed_res = discord.Embed(title=f"🏁 Finalizado: {f_home} vs {f_away}", description=f"El ganador fue: **{winner_name}** ({f_score})", color=discord.Color.gold())
                        summary = []
                        for p in payouts:
                            user = self.bot.get_user(p['user_id']) or await self.bot.fetch_user(p['user_id'])
                            name = user.mention if user else f"Usuario {p['user_id']}"
                            res_icon = "✅" if p['won'] else "❌"
                            summary.append(f"{res_icon} {name}: ${p['payout']:.2f}")
                        if summary: embed_res.add_field(name="Resumen de Cobros", value="\n".join(summary), inline=False)
                        await channel.send(embed=embed_res)
                    continue

                # Si sigue en vivo, actualizar marcador
                live_info = await database.get_live_msg_info(m_id)
                if not live_info: continue 
                
                msg_id = live_info[0]
                last_score = live_info[1]

                if msg_id:
                    if f_score != last_score:
                        try:
                            msg = await channel.fetch_message(msg_id)
                            emoji_h = api_football.get_flag_emoji(f_home)
                            emoji_a = api_football.get_flag_emoji(f_away)
                            embed = discord.Embed(title=f"🏟️ EN VIVO: {emoji_h} {f_home} vs {f_away} {emoji_a}", description=f"Marcador Actual: **{f_score}**", color=discord.Color.red())
                            await msg.edit(embed=embed)
                            await database.update_live_msg_info(m_id, msg_id, f_score)
                            print(f"⚽ [GOL DETECTADO - FIFA API] {f_home} {f_score} {f_away} | ID Interno: {m_id}")
                        except: pass
        except Exception as e:
            print(f"Error en fast_score_update: {e}")

    @fast_score_update.before_loop
    async def before_fast_score_update(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name='matches')
    async def matches(self, ctx):
        """Lista los partidos próximos."""
        comp = os.getenv('COMPETITION_CODE', 'PL')
        upcoming = await api_football.get_upcoming_matches(comp, session=self.bot.session)
        if not upcoming:
            await ctx.send("No hay partidos programados.", ephemeral=True)
            return
        embed = discord.Embed(title="⚽ Selección de Partidos", color=discord.Color.blue())
        await ctx.send(embed=embed, view=BettingView(upcoming[:25], ctx.author.id, self.bot), ephemeral=True)

    @commands.hybrid_command(name='apuestas')
    async def apuestas(self, ctx):
        """Muestra tus apuestas actuales que aún no se han resuelto."""
        user_id = ctx.author.id
        user_bets = await database.get_user_active_bets(user_id)
        if not user_bets:
            await ctx.send("No tienes apuestas activas.", ephemeral=True)
            return
        embed = discord.Embed(title="📝 Tus Apuestas Activas", color=discord.Color.blue())
        for home, away, amount, pred, m_id in user_bets:
            total_bets, pools = await database.get_match_pools(m_id)
            total_pool = total_bets + betting.HOUSE_INJECTION
            pred_pool = pools.get(pred, 0)
            multiplier = min(10.0, total_pool / pred_pool if pred_pool > 0 else 1.0)
            pred_name = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
            embed.add_field(name=f"{home} vs {away}", value=f"**Monto:** ${amount:.2f}\n**Predicción:** {pred_name}\n**Cuota:** x{multiplier:.2f}", inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='historial')
    async def historial(self, ctx):
        """Mira tus apuestas pasadas."""
        history = await database.get_user_history(ctx.author.id)
        if not history:
            await ctx.send("Historial vacío.", ephemeral=True)
            return
        embed = discord.Embed(title="📜 Tu Historial", color=discord.Color.blue())
        for home, away, amount, pred, payout, won, winner in history:
            status = "✅ GANADA" if won else "❌ PERDIDA"
            pred_name = home if pred == 'HOME_TEAM' else away if pred == 'AWAY_TEAM' else "Empate"
            embed.add_field(name=f"{home} vs {away}", value=f"{status} | Apostado: ${amount:.2f} | Ganado: ${payout:.2f}\nPred: {pred_name}", inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='historial_all')
    async def historial_all(self, ctx):
        """Historial de todos los usuarios."""
        history = await database.get_global_history(15)
        if not history:
            await ctx.send("Sin historial global.", ephemeral=True)
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
        await ctx.send("Selecciona qué tipo de apuesta quieres retirar:", view=CashoutView(ctx.author.id, self.bot), ephemeral=True)

    @commands.hybrid_command(name='pozo', aliases=['p'])
    async def pozo(self, ctx, match_id: str = None):
        """Muestra el volumen total y las cuotas actuales de un partido (Público)."""
        if match_id is None:
            # Modo interactivo: buscar partidos con apuestas o próximos
            active_matches = await database.get_active_matches_with_names()
            if not active_matches:
                await ctx.send("❌ No hay partidos con apuestas activas en este momento. Usa `/pozo <id>` si conoces uno específico.", ephemeral=True)
                return
            
            await ctx.send("Selecciona un partido para ver el estado del pozo:", view=PozoMatchView(active_matches, self.bot), ephemeral=True)
            return

        embed = await get_pozo_embed(match_id, bot=self.bot)
        if not embed:
            await ctx.send("❌ No se encontró el partido.")
            return

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='vivo')
    async def vivo(self, ctx):
        """Mira partidos en juego actualmente y apuesta en vivo."""
        comp = os.getenv('COMPETITION_CODE', 'PL')
        url = f"{api_football.BASE_URL}/competitions/{comp}/matches?status=LIVE"
        data = await api_football.fetch_json(url, session=self.bot.session)
        matches = data.get('matches', []) if data else []
        if not matches:
            await ctx.send("Sin partidos en vivo.", ephemeral=True)
            return
        await ctx.send(embed=discord.Embed(title="🏟️ En Vivo", color=discord.Color.red()), view=BettingView(matches[:25], ctx.author.id, self.bot), ephemeral=True)

    @commands.hybrid_command(name='parlay')
    async def parlay(self, ctx):
        """Crea un parlay (combinada)."""
        comp = os.getenv('COMPETITION_CODE', 'PL')
        upcoming = await api_football.get_upcoming_matches(comp, session=self.bot.session)
        if not upcoming:
            await ctx.send("Sin partidos para parlay.", ephemeral=True)
            return
        await ctx.send(embed=discord.Embed(title="🏗️ Constructor de Parlays"), view=ParlayBuilderView(upcoming, ctx.author.id, self.bot), ephemeral=True)

    @commands.hybrid_command(name='mis_parlays')
    async def mis_parlays(self, ctx):
        """Tus parlays activos."""
        parlays = await database.get_user_active_parlays(ctx.author.id)
        if not parlays:
            await ctx.send("Sin parlays activos.", ephemeral=True)
            return
        embed = discord.Embed(title="🚀 Tus Parlays", color=discord.Color.gold())
        for p in parlays:
            text = "\n".join([f"{'✅' if s=='WON' else '❌' if s=='LOST' else '⏳'} {h} vs {a}" for h,a,pr,s in p['legs']])
            embed.add_field(name=f"ID: {p['id']} (${p['amount']:.2f})", value=text, inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    @tasks.loop(minutes=1)
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
            
            fifa_data = await api_football.fetch_fifa_live_scores(session=self.bot.session)
            fifa_live_ids = [str(m['id']) for m in fifa_data.get('matches', [])] if fifa_data else []

            matches = []
            for m_id in active_ids:
                match = await api_football.get_match_details(m_id, session=self.bot.session)
                if not match: continue
                matches.append(match)
                
                status = match['status']
                fifa_match = next((m for m in (fifa_data.get('matches', []) if fifa_data else []) if str(m['id']) == str(m_id)), None)
                if status != 'FINISHED' and fifa_match:
                    if fifa_match['status'] in ['FINISHED', 'TIMED', 'FT']:
                        status = 'FINISHED'
                        match['status'] = 'FINISHED'
                        match['score'] = fifa_match['score']

            for match in matches:
                m_id, status = match['id'], match['status']
                home, away = match['homeTeam']['name'], match['awayTeam']['name']
                
                match_minute = api_football.calculate_match_minute(match['utcDate'])
                print(f"📌 [LOG] {home} vs {away} | Estado: {status} | Minuto: {match_minute:.1f}'")
                
                channel_id_env = os.getenv('ANNOUNCEMENT_CHANNEL_ID')
                if channel_id_env and status in ['IN_PLAY', 'PAUSED', 'LIVE']:
                    try:
                        channel_id = int(str(channel_id_env).strip().strip('"').strip("'"))
                        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)

                        if channel:
                            this_fifa = next((m for m in (fifa_data.get('matches', []) if fifa_data else []) if str(m['id']) == str(m_id)), None)
                            score = f"{this_fifa['score']['fullTime']['home']}-{this_fifa['score']['fullTime']['away']}" if this_fifa else f"{match['score']['fullTime']['home']}-{match['score']['fullTime']['away']}"
                            
                            emoji_h = api_football.get_flag_emoji(home)
                            emoji_a = api_football.get_flag_emoji(away)
                            
                            live_info = await database.get_live_msg_info(m_id)
                            msg_id = live_info[0] if live_info else None
                            last_score = live_info[1] if live_info else None
                            
                            embed_live = discord.Embed(title=f"🏟️ EN VIVO: {emoji_h} {home} vs {away} {emoji_a}", description=f"Marcador Actual: **{score}**", color=discord.Color.red())
                            
                            if msg_id:
                                try:
                                    msg = await channel.fetch_message(msg_id)
                                    if score != last_score:
                                        await msg.edit(embed=embed_live)
                                        await database.update_live_msg_info(m_id, msg_id, score)
                                        print(f"📝 [MSG] Marcador editado: {home} {score} {away}")
                                    else:
                                        print(f"⏱️ [MSG] Marcador sin cambios ({score}).")
                                except discord.NotFound:
                                    new_msg = await channel.send(embed=embed_live)
                                    await database.update_live_msg_info(m_id, new_msg.id, score)
                                    print(f"📣 [MSG] Marcador recreado: {home} vs {away}")
                                except Exception: pass
                            else:
                                new_msg = await channel.send(embed=embed_live)
                                await database.update_live_msg_info(m_id, new_msg.id, score)
                                print(f"📣 [MSG] Nuevo marcador enviado: {home} vs {away}")
                    except Exception: pass

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
                        if payouts is None: continue # Ya fue procesado por otro hilo (ej: fast_score_update)

                        channel = self.bot.get_channel(int(channel_id_env)) or await self.bot.fetch_channel(int(channel_id_env))
                        if channel:
                            # Intentar obtener el marcador final
                            score = "N/A"
                            try:
                                score = f"{match['score']['fullTime']['home']}-{match['score']['fullTime']['away']}"
                            except: pass

                            winner_name = home if winner == 'HOME_TEAM' else away if winner == 'AWAY_TEAM' else "Empate"
                            embed_res = discord.Embed(title=f"🏁 Resultado: {home} vs {away}", description=f"El ganador fue: **{winner_name}** ({score})", color=discord.Color.gold())
                            summary = []
                            for p in payouts:
                                user = self.bot.get_user(p['user_id']) or await self.bot.fetch_user(p['user_id'])
                                name = user.mention if user else f"Usuario {p['user_id']}"
                                res_icon = "✅" if p['won'] else "❌"
                                summary.append(f"{res_icon} {name}: ${p['payout']:.2f}")
                            if summary: embed_res.add_field(name="Resumen de Cobros", value="\n".join(summary), inline=False)
                            await channel.send(embed=embed_res)
                            print(f"📢 [MSG] Anuncio enviado: {home} vs {away}")
                        await betting.resolve_parlays_for_match(self.bot, m_id, winner)
                        await database.add_or_update_match(m_id, home, away, status, winner)
        except Exception as e: print(f"ERROR: {e}")

    @check_matches.before_loop
    async def before_check_matches(self): await self.bot.wait_until_ready()

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
                print(f"Error al anunciar debug_resolve: {e}")

        await ctx.send(f"✅ Partido `{home_name} vs {away_name}` resuelto como `{winner}` y anunciado.", ephemeral=True)

    @commands.command(name='debug_finalizar')
    @commands.has_permissions(administrator=True)
    async def debug_finalizar_prefix(self, ctx, match_id: str, winner: str):
        """[ADMIN] Comando con prefijo (!) para forzar resolución manual."""
        await self.debug_resolve(ctx, match_id, winner)

async def setup(bot): await bot.add_cog(Betting(bot))
