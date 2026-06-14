import aiohttp
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('FOOTBALL_API_KEY')
BASE_URL = 'https://api.football-data.org/v4'

async def fetch_json(url):
    """Auxiliar para realizar peticiones GET asíncronas con manejo de desconexión."""
    headers = {'X-Auth-Token': API_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:
                    print("⚠️ API Rate Limit alcanzado. Esperando...")
                    return None
                else:
                    print(f"Error en API ({url}): {response.status}")
                    return None
    except aiohttp.ClientError as e:
        print(f"📡 Error de conexión (reintentando en próximo ciclo): {e}")
        return None
    except asyncio.TimeoutError:
        print(f"⏱️ Tiempo de espera agotado para la API: {url}")
        return None
    except Exception as e:
        print(f"❌ Error inesperado en fetch_json: {e}")
        return None

async def get_upcoming_matches(competition='PL'):
    url = f'{BASE_URL}/competitions/{competition}/matches?status=SCHEDULED'
    data = await fetch_json(url)
    return data.get('matches', []) if data else []

async def get_match_details(match_id):
    url = f'{BASE_URL}/matches/{match_id}'
    return await fetch_json(url)

async def get_finished_matches(competition='PL'):
    url = f'{BASE_URL}/competitions/{competition}/matches?status=FINISHED'
    data = await fetch_json(url)
    return data.get('matches', []) if data else []

async def fetch_fifa_live_scores():
    """Consulta el endpoint especial de la FIFA para marcadores en tiempo real."""
    url = "https://fifaapi-v7l1.onrender.com/v4/competitions/WC/matches?status=LIVE"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    return await response.json()
                return None
    except:
        return None

async def fetch_fifa_finished_matches():
    """Consulta el endpoint de la FIFA para partidos finalizados recientemente."""
    url = "https://fifaapi-v7l1.onrender.com/v4/competitions/WC/matches?status=FINISHED"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    return await response.json()
                return None
    except:
        return None

def get_flag_emoji(country_name):
    # Mapeo de nombres de países a emojis de banderas
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
    # Mapeo básico de nombres de la API a códigos de país
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

from datetime import datetime, timezone

def calculate_match_minute(utc_date_str):
    """Calcula el minuto estimado del partido considerando entretiempo y pequeños retrasos."""
    try:
        now_utc = datetime.now(timezone.utc)
        start_dt = datetime.fromisoformat(utc_date_str.replace('Z', '+00:00'))
        elapsed = (now_utc - start_dt).total_seconds() / 60
        
        # Si el partido no ha empezado
        if elapsed < 0: return 0.0
        
        # Primer tiempo (0-45) + 5 min de posible retraso/adición
        if elapsed < 50:
            return elapsed
        
        # Entretiempo (aprox 15 min)
        if 50 <= elapsed < 65:
            return 45.0
            
        # Segundo tiempo: restamos 15 min de entretiempo
        # También restamos 5 min adicionales por retrasos promedio para ser más precisos
        # (Total -20 min para partidos de más de 65 min desde el inicio programado)
        return max(45.0, elapsed - 20.0)
    except:
        return 0.0
