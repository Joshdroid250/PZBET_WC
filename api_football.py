import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('FOOTBALL_API_KEY')
BASE_URL = 'https://api.football-data.org/v4'

def get_upcoming_matches(competition='PL'):
    url = f'{BASE_URL}/competitions/{competition}/matches?status=SCHEDULED'
    headers = {'X-Auth-Token': API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('matches', [])
    else:
        print(f"Error fetching matches: {response.status_code} - {response.text}")
        return []

def get_match_details(match_id):
    url = f'{BASE_URL}/matches/{match_id}'
    headers = {'X-Auth-Token': API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching match details: {response.status_code} - {response.text}")
        return None

def get_finished_matches(competition='PL'):
    url = f'{BASE_URL}/competitions/{competition}/matches?status=FINISHED'
    headers = {'X-Auth-Token': API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('matches', [])
    else:
        print(f"Error fetching finished matches: {response.status_code} - {response.text}")
        return []

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
    # Usamos flagpedia.net que es muy confiable para imágenes
    # Necesitamos un mapeo básico de nombres de la API a códigos de país
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
