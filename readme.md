# PZBET - World Cup Betting Bot

PZBET es un bot de Discord para apuestas deportivas de futbol con cuotas externas de Kalshi, cashout, marcadores en vivo y resolucion automatica de partidos.

## Caracteristicas

- **Cuotas Kalshi obligatorias**: si Kalshi tiene mercado para el partido y la seleccion, la apuesta usa ese multiplicador.
- **Sin cuotas locales**: si Kalshi no tiene cuota disponible, la apuesta no se registra.
- **Cuota congelada**: cada apuesta guarda el multiplicador exacto al momento de apostar.
- **Comando `/kalshi`**: permite consultar multiplicadores antes de apostar.
- **Parlays existentes**: se mantienen consulta y resolucion de parlays ya creados, pero no se crean nuevos mientras solo se usan cuotas Kalshi.
- **Cashout**: recuperacion parcial antes del minuto 90.
- **Candado minuto 90**: bloquea apuestas y cashouts al final del partido.
- **Marcadores en vivo**: actualizacion y anuncios de resultados.
- **SQLite persistente**: usuarios, apuestas, partidos, parlays e historial.

## Reglas de cuotas

1. Kalshi es la unica fuente para apuestas individuales.
2. Si Kalshi esta desactivado, caido o no encuentra mercado para la seleccion, la apuesta no se registra.
3. Las cuotas de Kalshi se usan libres, sin cap local de multiplicador.
4. La cuota final se congela al apostar y se muestra como `Fuente: Kalshi`.
5. `/kalshi` y `/kalshivivo` son informativos; la cuota oficial de la apuesta se fija cuando el usuario confirma el monto.

## Comandos principales

- `/join`: registra al usuario.
- `/balance`: muestra el balance.
- `/matches`: lista partidos disponibles para apostar.
- `/kalshi`: consulta multiplicadores Kalshi por partido.
- `/kalshivivo`: consulta multiplicadores Kalshi de partidos en vivo.
- `/apuestas`: muestra apuestas activas.
- `/mis_parlays`: muestra parlays activos existentes.
- `/cashout`: retira una apuesta activa con reembolso parcial.
- `/vivo`: muestra partidos en vivo disponibles.
- `/historial`: historial personal.
- `/historial_all`: historial global.
- `/reglas`: explica el sistema de apuestas.

## Instalacion

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Iniciar el bot:

```bash
python bot.py
```

## Variables de entorno

No incluyas tokens reales, URLs privadas ni secretos en este archivo.

```env
DISCORD_TOKEN=pon_tu_token_en_el_entorno
BOT_PREFIX=!
ANNOUNCEMENT_CHANNEL_ID=id_del_canal
COMPETITION_CODE=WC

KALSHI_ODDS_ENABLED=1
KALSHI_SERIES_TICKER=serie_de_kalshi
KALSHI_MATCH_MIN_CONFIDENCE=0.72
KALSHI_MAX_PAGES=3

MIN_MULTIPLIER=1.01
```

Variables opcionales:

- `RAILWAY_VOLUME_MOUNT_PATH`: ruta persistente para la base de datos en Railway u otro hosting.
- `KALSHI_CATEGORY`: filtro adicional de categoria si se necesita.
- `FIFA_API_BASE_URL`: solo configurarla en el entorno de despliegue si se usa un endpoint personalizado.
- `KALSHI_BASE_URL`: solo configurarla en el entorno de despliegue si se necesita sobrescribir el endpoint por defecto.

## Sincronizacion de comandos

El bot sincroniza comandos globales al iniciar. Si Discord muestra comandos duplicados, normalmente hay comandos locales del servidor mezclados con comandos globales.

Para limpiar comandos locales:

```text
!sync clear
```

Despues reinicia Discord o espera unos minutos. No ejecutes sincronizaciones globales repetidas salvo que sea necesario.

## Testing

Ejecutar toda la suite:

```bash
python -m unittest discover tests_simulacion
```

Pruebas cubiertas:

- Registro y balances.
- Apuestas con cuota congelada.
- Kalshi obligatorio y rechazo cuando no hay cuota.
- Resolucion de parlays existentes.
- Cashout.
- Resolucion automatica.
- Candado de duplicidad de pagos.
- Comandos restaurados.

## Estructura

- `bot.py`: entrada principal y sincronizacion de comandos.
- `api_football.py`: cliente de partidos y marcadores.
- `kalshi_odds.py`: matching y calculo de multiplicadores Kalshi.
- `database.py`: persistencia SQLite.
- `betting.py`: resolucion de pagos, parlays y roles.
- `cogs/general.py`: comandos generales.
- `cogs/betting_cog.py`: apuestas, cashout, Kalshi y resolucion.
- `tests_simulacion/`: pruebas automatizadas.
- `mantenimiento_db/`: utilidades de diagnostico y mantenimiento.

## Produccion

- Mantener secretos solo en variables de entorno del hosting.
- Verificar que el volumen persistente de la base de datos este configurado.
- Reiniciar el bot despues de cambios de comandos.
- Usar `/kalshi` para validar mercados antes de abrir apuestas reales.
- Revisar logs si Kalshi no responde; en ese caso las apuestas individuales se rechazan.
