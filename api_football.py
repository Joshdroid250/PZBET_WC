import aiohttp
import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv('FIFA_API_BASE_URL', 'https://fifaapi-v7l1.onrender.com/v4')

async def fetch_json(url, retries=2):
    """Auxiliar para realizar peticiones GET asíncronas con reintentos para errores 500."""
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        if attempt == retries - 1:
                            print("⚠️ API Rate Limit alcanzado. Esperando...")
                        await asyncio.sleep(2)
                        continue
                    elif response.status >= 500:
                        if attempt == retries - 1:
                            print(f"❌ Error de Servidor en API ({url}): {response.status}")
                        await asyncio.sleep(1) # Pequeña espera antes de reintentar
                        continue
                    else:
                        print(f"Error en API ({url}): {response.status}")
                        return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == retries - 1:
                print(f"📡 Error de conexión/tiempo en API: {e}")
            await asyncio.sleep(1)
            continue
        except Exception as e:
            print(f"❌ Error inesperado en fetch_json: {e}")
            return None
    return None

async def get_upcoming_matches(competition='WC'):
    url = f'{BASE_URL}/competitions/{competition}/matches?status=SCHEDULED'
    data = await fetch_json(url)
    return data.get('matches', []) if data else []

async def get_match_details(match_id):
    url = f'{BASE_URL}/matches/{match_id}'
    return await fetch_json(url)

async def get_finished_matches(competition='WC'):
    url = f'{BASE_URL}/competitions/{competition}/matches?status=FINISHED'
    data = await fetch_json(url)
    return data.get('matches', []) if data else []

async def fetch_fifa_live_scores():
    """Consulta el endpoint especial de la FIFA para marcadores en tiempo real."""
    url = f"{BASE_URL}/competitions/WC/matches?status=LIVE"
    return await fetch_json(url)

async def fetch_fifa_finished_matches():
    """Consulta el endpoint de la FIFA para partidos finalizados recientemente."""
    url = f"{BASE_URL}/competitions/WC/matches?status=FINISHED"
    return await fetch_json(url)

def get_flag_emoji(country_name):
    mapping = {
        'Argentina': '🇦🇷', 'Brazil': '🇧🇷', 'France': '🇫🇷', 'Spain': '🇪🇸', 'Germany': '🇩🇪',
        'Portugal': '🇵🇹', 'England': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'Mexico': '🇲🇽', 'USA': '🇺🇸', 'United States': '🇺🇸',
        'Netherlands': '🇳🇱', 'Belgium': '🇧🇪', 'Croatia': '🇭🇷', 'Morocco': '🇲🇦', 'Japan': '🇯🇵',
        'South Korea': '🇰🇷', 'Canada': '🇨🇦', 'Australia': '🇦🇺', 'Uruguay': '🇺🇾', 'Paraguay': '🇵🇾',
        'Ecuador': '🇪🇨', 'Switzerland': '🇨🇭', 'Denmark': '🇩🇰', 'Poland': '🇵🇱', 'Saudi Arabia': '🇸🇦',
        'Italy': '🇮🇹', 'Sweden': '🇸🇪', 'Ukraine': '🇺🇦', 'Wales': '🏴󠁧󠁢󠁷󠁬󠁳󠁿', 'Scotland': '🏴󠁧󠁢󠁳󠁣󠁴󠁿'
    }
    return mapping.get(country_name, '⚽')

def get_flag_url(country_name):
    mapping = {
        'Argentina': 'ar', 'Brazil': 'br', 'France': 'fr', 'Spain': 'es', 'Germany': 'de',
        'Portugal': 'pt', 'England': 'gb-eng', 'Mexico': 'mx', 'USA': 'us', 'United States': 'us',
        'Netherlands': 'nl', 'Belgium': 'be', 'Croatia': 'hr', 'Morocco': 'ma', 'Japan': 'jp',
        'South Korea': 'kr', 'Canada': 'ca', 'Australia': 'au', 'Uruguay': 'uy', 'Paraguay': 'py',
        'Ecuador': 'ec', 'Switzerland': 'ch', 'Denmark': 'dk', 'Poland': 'pl', 'Saudi Arabia': 'sa'
    }
    code = mapping.get(country_name)
    if code:
        return f"https://flagcdn.com/w160/{code}.png"
    return None

def calculate_match_minute(utc_date_str):
    try:
        now_utc = datetime.now(timezone.utc)
        start_dt = datetime.fromisoformat(utc_date_str.replace('Z', '+00:00'))
        elapsed = (now_utc - start_dt).total_seconds() / 60
        if elapsed < 0: return 0.0
        if elapsed < 50: return elapsed
        if 50 <= elapsed < 65: return 45.0
        return max(45.0, elapsed - 20.0)
    except:
        return 0.0
