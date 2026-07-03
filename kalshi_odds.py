import os
import re
import unicodedata
from difflib import SequenceMatcher

import aiohttp


BASE_URL = os.getenv('KALSHI_BASE_URL', 'https://external-api.kalshi.com/trade-api/v2')
ENABLED = os.getenv('KALSHI_ODDS_ENABLED', '0').lower() in ('1', 'true', 'yes', 'on')
MIN_CONFIDENCE = float(os.getenv('KALSHI_MATCH_MIN_CONFIDENCE', '0.72'))
MIN_MULTIPLIER = float(os.getenv('MIN_MULTIPLIER', '1.01'))
SERIES_TICKER = os.getenv('KALSHI_SERIES_TICKER', 'KXWCGAME')
CATEGORY = os.getenv('KALSHI_CATEGORY')
MAX_PAGES = int(os.getenv('KALSHI_MAX_PAGES', '3'))


ALIASES = {
    'usa': 'united states',
    'u s a': 'united states',
    'us': 'united states',
    'u s': 'united states',
    'united states of america': 'united states',
    'korea republic': 'south korea',
    'republic of korea': 'south korea',
    'cote d ivoire': 'ivory coast',
    'cote divoire': 'ivory coast',
    'ivorian coast': 'ivory coast',
    'bosnia herzegovina': 'bosnia and herzegovina',
    'bosnia herzogovina': 'bosnia and herzegovina',
    'herzegovina': 'bosnia and herzegovina',
    'cabo verde': 'cape verde',
    'turkiye': 'turkey',
    'tuerkiye': 'turkey',
    'uae': 'united arab emirates',
    'u a e': 'united arab emirates',
    'china pr': 'china',
    'pr china': 'china',
    'chinese pr': 'china',
    'iran islamic republic': 'iran',
    'islamic republic of iran': 'iran',
    'czechia': 'czech republic',
    'north macedonia': 'macedonia',
    'fyr macedonia': 'macedonia',
    'dr congo': 'democratic republic of congo',
    'd r congo': 'democratic republic of congo',
    'congo dr': 'democratic republic of congo',
    'congo democratic republic': 'democratic republic of congo',
    'congo democratic republic of': 'democratic republic of congo',
    'kyrgyz republic': 'kyrgyzstan',
    'syrian arab republic': 'syria',
    'russian federation': 'russia',
}


def normalize_name(value):
    value = (value or '').lower()
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^a-z0-9 ]+', ' ', value)
    value = re.sub(r'\b(fc|cf|team|national|men|women|womens|mens)\b', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip()
    for alias, canonical in sorted(ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        value = re.sub(rf'\b{re.escape(alias)}\b', canonical, value)
    return value


def _text_blob(*parts):
    return normalize_name(' '.join(str(p or '') for p in parts))


def _contains_or_similar(text, name):
    text = normalize_name(text)
    name = normalize_name(name)
    if not name:
        return 0.0
    if name in text:
        return 1.0
    return SequenceMatcher(None, name, text).ratio()


def _price_to_multiplier(price):
    try:
        probability = float(price)
    except (TypeError, ValueError):
        return None
    if probability <= 0:
        return None
    return round(max(MIN_MULTIPLIER, 1.0 / probability), 2)


def _market_yes_price(market):
    for key in ('yes_ask_dollars', 'last_price_dollars', 'yes_bid_dollars'):
        multiplier = _price_to_multiplier(market.get(key))
        if multiplier:
            return multiplier
    return None


def _affirmative_team_text(text):
    text = normalize_name(text)
    patterns = (
        r'\bwill\s+(.+?)\s+(?:beat|defeat|win|advance|qualify)\b',
        r'\b(.+?)\s+to\s+(?:beat|defeat|win|advance|qualify)\b',
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return normalize_name(match.group(1))
    return text


def _event_team_codes(event):
    sub_title = event.get('sub_title') or ''
    match = re.search(r'\b([A-Z]{2,4})\s+vs\s+([A-Z]{2,4})\b', sub_title)
    if not match:
        return {}

    title = event.get('title') or ''
    teams_part = title.split(':', 1)[0]
    if ' vs ' not in teams_part:
        return {}

    home_name, away_name = [normalize_name(part) for part in teams_part.split(' vs ', 1)]
    return {
        match.group(1): home_name,
        match.group(2): away_name,
        'TIE': 'draw',
    }


def _market_suffix(market):
    ticker = market.get('ticker') or ''
    if '-' not in ticker:
        return None
    return ticker.rsplit('-', 1)[-1]


def match_market_for_prediction(events, home_team, away_team, prediction):
    target_team = 'draw' if prediction == 'DRAW' else home_team if prediction == 'HOME_TEAM' else away_team
    other_team = away_team if prediction == 'HOME_TEAM' else home_team
    best = None

    for event in events:
        event_blob = _text_blob(event.get('title'), event.get('sub_title'), event.get('category'))
        event_score = min(_contains_or_similar(event_blob, home_team), _contains_or_similar(event_blob, away_team))
        if event_score < MIN_CONFIDENCE:
            continue

        code_map = _event_team_codes(event)
        for market in event.get('markets') or []:
            market_blob = _text_blob(
                market.get('title'),
                market.get('subtitle'),
                market.get('yes_sub_title'),
                market.get('rules_primary'),
            )
            suffix_team = code_map.get(_market_suffix(market))
            if suffix_team:
                target_score = _contains_or_similar(suffix_team, target_team)
                other_score = 0.0 if prediction == 'DRAW' else _contains_or_similar(suffix_team, other_team)
            else:
                affirmative_blob = _affirmative_team_text(market.get('yes_sub_title') or market.get('title') or '')
                target_score = max(
                    _contains_or_similar(affirmative_blob, target_team),
                    _contains_or_similar(market_blob, target_team) * 0.8,
                )
                other_score = 0.0 if prediction == 'DRAW' else max(
                    _contains_or_similar(affirmative_blob, other_team),
                    _contains_or_similar(market_blob, other_team) * 0.8,
                )
            confidence = min(event_score, target_score)

            if confidence < MIN_CONFIDENCE or other_score > target_score:
                continue

            multiplier = _market_yes_price(market)
            if not multiplier:
                continue

            candidate = {
                'multiplier': multiplier,
                'confidence': round(confidence, 3),
                'event_ticker': event.get('event_ticker'),
                'market_ticker': market.get('ticker'),
                'title': market.get('title') or event.get('title'),
            }
            if not best or candidate['confidence'] > best['confidence']:
                best = candidate

    return best


async def fetch_open_events(session=None, limit=200):
    result = await fetch_open_events_status(session=session, limit=limit)
    return result['events']


async def fetch_open_events_status(session=None, limit=200):
    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession()
    events = []
    cursor = None
    try:
        for _ in range(MAX_PAGES):
            params = {'status': 'open', 'with_nested_markets': 'true', 'limit': str(limit)}
            if cursor:
                params['cursor'] = cursor
            if SERIES_TICKER:
                params['series_ticker'] = SERIES_TICKER

            async with session.get(
                f'{BASE_URL}/events',
                params=params,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as response:
                if response.status != 200:
                    return {'available': False, 'events': events}
                data = await response.json()
                batch = data.get('events') or []
                if CATEGORY:
                    batch = [event for event in batch if normalize_name(event.get('category')) == normalize_name(CATEGORY)]
                events.extend(batch)
                cursor = data.get('cursor')
                if not cursor or not batch:
                    break
        return {'available': True, 'events': events}
    except Exception:
        return {'available': False, 'events': events}
    finally:
        if owns_session:
            await session.close()


async def get_multiplier(home_team, away_team, prediction, session=None):
    if not ENABLED:
        return None
    events = await fetch_open_events(session=session)
    return match_market_for_prediction(events, home_team, away_team, prediction)


async def get_multiplier_status(home_team, away_team, prediction, session=None):
    if not ENABLED:
        return {'enabled': False, 'available': False, 'match': None}
    result = await fetch_open_events_status(session=session)
    match = match_market_for_prediction(result['events'], home_team, away_team, prediction)
    return {'enabled': True, 'available': result['available'], 'match': match}


async def get_multipliers(home_team, away_team, session=None):
    if not ENABLED:
        return {}
    events = await fetch_open_events(session=session)
    return {
        prediction: match_market_for_prediction(events, home_team, away_team, prediction)
        for prediction in ('HOME_TEAM', 'DRAW', 'AWAY_TEAM')
    }
