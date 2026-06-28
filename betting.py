import database
import os

# Cantidad que el bot "apuesta" simbólicamente para que siempre haya premio
HOUSE_INJECTION = float(os.getenv('HOUSE_INJECTION', '500.0'))

def get_multiplier_bar(multiplier, max_val=10.0, length=10):
    """Genera una barra visual tipo [███░░░] basada en el multiplicador."""
    filled = int((multiplier / max_val) * length)
    filled = max(1, min(filled, length)) # Al menos 1 bloque si hay apuesta
    bar = "█" * filled + "░" * (length - filled)
    return f"[`{bar}`]"

async def resolve_match_bets(bot, match_id, actual_winner, *score_args):
    """
    actual_winner: 'HOME_TEAM', 'AWAY_TEAM', or 'DRAW'
    Returns: list of payouts if resolved now, None if already resolved, [] if resolved now but no bets.
    """
    # --- CANDADO DE SEGURIDAD ---
    # Si el partido ya aparece como FINISHED en la DB, no procesar de nuevo.
    if await database.is_match_resolved(match_id):
        print(f"⚠️ [SEGURIDAD] Intento de doble pago detectado para partido {match_id}. Abortando.")
        return None
    
    bets = await database.get_active_bets_for_match(match_id)
    if not bets:
        await database.mark_all_bets_resolved_empty(match_id)
        # Marcamos el partido como FINISHED para evitar que otros hilos intenten procesarlo
        # Obtenemos info básica para el update
        m_info = await database.get_match_by_id(match_id)
        if m_info:
            await database.add_or_update_match(match_id, m_info[1], m_info[2], 'FINISHED', actual_winner)
        return []

    # El pozo total incluye lo que apostó la gente + la inyección del bot
    total_user_pool = sum(bet[2] for bet in bets)
    total_effective_pool = total_user_pool + HOUSE_INJECTION
    
    winning_bets = [bet for bet in bets if bet[3] == actual_winner]
    winning_user_pool = sum(bet[2] for bet in winning_bets)

    payouts = []

    if winning_user_pool > 0:
        fallback_payout_ratio = total_effective_pool / winning_user_pool
        if fallback_payout_ratio > 10.0: fallback_payout_ratio = 10.0

        for bet_id, user_id, amount, prediction, locked_multiplier in bets:
            is_winner = (prediction == actual_winner)
            payout_ratio = locked_multiplier if locked_multiplier else fallback_payout_ratio
            winnings = database.round_money(amount * payout_ratio) if is_winner else 0.0
            
            if is_winner:
                await database.update_balance(user_id, winnings)
                # Actualizar roles tras ganar
                await update_user_roles(bot, user_id)
            
            await database.mark_bet_resolved_by_id(bet_id, winnings, is_winner)
            
            payouts.append({
                'user_id': user_id,
                'amount_bet': amount,
                'payout': winnings,
                'won': is_winner,
                'prediction': prediction
            })
    else:
        # Si nadie acertó, el dinero se queda en la "casa" (no hay ganadores)
        for bet_id, user_id, amount, prediction, locked_multiplier in bets:
            await database.mark_bet_resolved_by_id(bet_id, 0.0, False)
            payouts.append({
                'user_id': user_id,
                'amount_bet': amount,
                'payout': 0.0,
                'won': False,
                'refunded': False,
                'prediction': prediction
            })

    # IMPORTANTE: Marcamos el partido como FINISHED inmediatamente después de procesar pagos
    m_info = await database.get_match_by_id(match_id)
    if m_info:
        await database.add_or_update_match(match_id, m_info[1], m_info[2], 'FINISHED', actual_winner)

    return payouts

async def resolve_parlays_for_match(bot, match_id, winner):
    """Actualiza y resuelve los parlays que incluyan este partido."""
    import database
    import discord
    import os
    
    parlay_ids = await database.get_active_parlay_ids()
    print(f"DEBUG: Procesando parlays para partido {match_id}. Parlays activos: {parlay_ids}")
    
    for p_id in parlay_ids:
        legs = await database.get_parlay_legs(p_id)
        print(f"DEBUG: Revisando parlay {p_id}, piernas: {legs}")
        
        for leg_m_id, pred, leg_status in legs:
            # Asegurar comparación numérica
            if str(leg_m_id) == str(match_id) and leg_status == 'PENDING':
                print(f"DEBUG: Coincidencia en parlay {p_id}, pierna {leg_m_id}. Predicción: {pred}, Resultado: {winner}")
                
                new_status = 'WON' if pred == winner else 'LOST'
                await database.update_parlay_leg_status(p_id, match_id, new_status)
                print(f"DEBUG: Estado de pierna actualizado a {new_status}")
                
                # Re-consultar todas las piernas para ver si el parlay cerró
                all_legs = await database.get_parlay_legs(p_id)
                parlay_status = "PENDING"
                payout = 0.0
                p_user_id = None
                
                if any(l[2] == 'LOST' for l in all_legs):
                    parlay_status = "LOST"
                    await database.resolve_parlay(p_id, 0.0, False)
                    print(f"DEBUG: Parlay {p_id} marcado como PERDIDO")
                    # Necesitamos el user_id para la notificación
                    async with database.aiosqlite.connect(database.DB_PATH) as db:
                        async with db.execute('SELECT user_id FROM parlays WHERE parlay_id = ?', (p_id,)) as cursor:
                            row = await cursor.fetchone()
                            if row: p_user_id = row[0]
                elif all(l[2] == 'WON' for l in all_legs):
                    parlay_status = "WON"
                    # Obtener monto para calcular premio
                    async with database.aiosqlite.connect(database.DB_PATH) as db:
                        async with db.execute('SELECT amount, user_id FROM parlays WHERE parlay_id = ?', (p_id,)) as cursor:
                            row = await cursor.fetchone()
                            amt, p_user_id = row
                    payout = database.round_money(amt * (2 ** len(all_legs)))
                    await database.resolve_parlay(p_id, payout, True)
                    print(f"DEBUG: Parlay {p_id} marcado como GANADO. Pago: ${payout}")

                # Notificar si se cerró
                if parlay_status != "PENDING":
                    channel_id = os.getenv('ANNOUNCEMENT_CHANNEL_ID')
                    if channel_id:
                        channel = bot.get_channel(int(channel_id))
                        if not channel:
                            try: channel = await bot.fetch_channel(int(channel_id))
                            except: channel = None
                        
                        if channel:
                            user = bot.get_user(p_user_id) if p_user_id else None
                            if not user and p_user_id:
                                try: user = await bot.fetch_user(p_user_id)
                                except: user = None
                                
                            name = user.mention if user else f"Usuario {p_user_id}"
                            if parlay_status == "WON":
                                embed_p = discord.Embed(title="🚀 ¡PARLAY GANADO!", color=discord.Color.gold())
                                embed_p.description = f"🔥 {name} ha acertado todas sus combinaciones y se lleva **${payout:.2f}**!"
                                await channel.send(embed=embed_p)
                            else:
                                # Notificación opcional de pérdida
                                embed_p = discord.Embed(title="❌ Parlay Perdido", color=discord.Color.red())
                                embed_p.description = f"Lo siento {name}, una de tus combinaciones del Parlay {p_id} ha fallado."
                                await channel.send(embed=embed_p)
                break # Ya procesamos el match_id en este parlay

async def update_user_roles(bot, user_id):
    """Actualiza los roles del usuario basados en su balance actual."""
    import database
    import discord
    balance = await database.get_user_balance(user_id)
    if balance is None: return

    settings = await database.get_all_settings()
    
    # Mapeo de llaves internas a IDs de Discord guardados
    role_map = {
        'broke': int(settings.get('role_broke', 0)),
        'gambler': int(settings.get('role_gambler', 0)),
        'pro': int(settings.get('role_pro', 0))
    }
    
    thresholds = {
        'gambler': float(settings.get('threshold_gambler', 500.0)),
        'pro': float(settings.get('threshold_pro', 2000.0))
    }

    # Determinar rango
    target_key = 'broke'
    if balance >= thresholds['pro']: target_key = 'pro'
    elif balance >= thresholds['gambler']: target_key = 'gambler'

    # Aplicar en todos los guilds donde esté el bot
    for guild in bot.guilds:
        member = guild.get_member(user_id)
        if not member:
            try: member = await guild.fetch_member(user_id)
            except: continue
        
        if member:
            roles_to_remove = [guild.get_role(role_map[k]) for k in role_map if k != target_key and role_map[k] != 0]
            role_to_add = guild.get_role(role_map[target_key])
            
            try:
                # Limpiar nulos y roles que no existen
                roles_to_remove = [r for r in roles_to_remove if r is not None]
                if roles_to_remove: await member.remove_roles(*roles_to_remove)
                if role_to_add: await member.add_roles(role_to_add)
            except Exception as e:
                print(f"Error actualizando roles para {user_id} en {guild.name}: {e}")
