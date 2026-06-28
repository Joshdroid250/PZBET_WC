import unittest

import kalshi_odds


class TestKalshiOddsMatching(unittest.TestCase):
    def test_matches_clear_team_market(self):
        events = [
            {
                'event_ticker': 'EVT',
                'title': 'Jordan vs Argentina',
                'markets': [
                    {
                        'ticker': 'MKT_ARG',
                        'title': 'Will Argentina beat Jordan?',
                        'yes_ask_dollars': '0.25',
                    }
                ],
            }
        ]

        result = kalshi_odds.match_market_for_prediction(events, 'Jordan', 'Argentina', 'AWAY_TEAM')

        self.assertIsNotNone(result)
        self.assertEqual(result['market_ticker'], 'MKT_ARG')
        self.assertEqual(result['multiplier'], 4.0)

    def test_does_not_match_if_event_missing_other_team(self):
        events = [
            {
                'event_ticker': 'EVT',
                'title': 'Brazil vs Argentina',
                'markets': [
                    {
                        'ticker': 'MKT_ARG',
                        'title': 'Will Argentina beat Brazil?',
                        'yes_ask_dollars': '0.25',
                    }
                ],
            }
        ]

        result = kalshi_odds.match_market_for_prediction(events, 'Jordan', 'Argentina', 'AWAY_TEAM')

        self.assertIsNone(result)

    def test_does_not_match_rival_market_for_prediction(self):
        events = [
            {
                'event_ticker': 'EVT',
                'title': 'Jordan vs Argentina',
                'markets': [
                    {
                        'ticker': 'MKT_JOR',
                        'title': 'Will Jordan beat Argentina?',
                        'yes_ask_dollars': '0.25',
                    }
                ],
            }
        ]

        result = kalshi_odds.match_market_for_prediction(events, 'Jordan', 'Argentina', 'AWAY_TEAM')

        self.assertIsNone(result)

    def test_draw_falls_back_to_local(self):
        result = kalshi_odds.match_market_for_prediction([], 'Jordan', 'Argentina', 'DRAW')

        self.assertIsNone(result)

    def test_matches_kxwcgame_by_ticker_suffix(self):
        events = [
            {
                'event_ticker': 'KXWCGAME-26JUN27JORARG',
                'title': 'Jordan vs Argentina',
                'sub_title': 'JOR vs ARG (Jun 27)',
                'markets': [
                    {
                        'ticker': 'KXWCGAME-26JUN27JORARG-JOR',
                        'title': 'Jordan vs Argentina Winner?',
                        'yes_ask_dollars': '0.01',
                    },
                    {
                        'ticker': 'KXWCGAME-26JUN27JORARG-ARG',
                        'title': 'Jordan vs Argentina Winner?',
                        'yes_ask_dollars': '1.00',
                    },
                    {
                        'ticker': 'KXWCGAME-26JUN27JORARG-TIE',
                        'title': 'Jordan vs Argentina Winner?',
                        'yes_ask_dollars': '0.01',
                    },
                ],
            }
        ]

        away = kalshi_odds.match_market_for_prediction(events, 'Jordan', 'Argentina', 'AWAY_TEAM')
        draw = kalshi_odds.match_market_for_prediction(events, 'Jordan', 'Argentina', 'DRAW')

        self.assertEqual(away['market_ticker'], 'KXWCGAME-26JUN27JORARG-ARG')
        self.assertEqual(away['multiplier'], 1.01)
        self.assertEqual(draw['market_ticker'], 'KXWCGAME-26JUN27JORARG-TIE')
        self.assertEqual(draw['multiplier'], 10.0)

    def test_get_multipliers_from_same_event_set(self):
        async def run():
            events = [
                {
                    'event_ticker': 'KXWCGAME-26JUN27JORARG',
                    'title': 'Jordan vs Argentina',
                    'sub_title': 'JOR vs ARG (Jun 27)',
                    'markets': [
                        {
                            'ticker': 'KXWCGAME-26JUN27JORARG-JOR',
                            'title': 'Jordan vs Argentina Winner?',
                            'yes_ask_dollars': '0.20',
                        },
                        {
                            'ticker': 'KXWCGAME-26JUN27JORARG-ARG',
                            'title': 'Jordan vs Argentina Winner?',
                            'yes_ask_dollars': '0.25',
                        },
                        {
                            'ticker': 'KXWCGAME-26JUN27JORARG-TIE',
                            'title': 'Jordan vs Argentina Winner?',
                            'yes_ask_dollars': '0.50',
                        },
                    ],
                }
            ]
            async def fake_fetch(session=None):
                return events
            original_enabled = kalshi_odds.ENABLED
            original_fetch = kalshi_odds.fetch_open_events
            kalshi_odds.ENABLED = True
            kalshi_odds.fetch_open_events = fake_fetch
            try:
                return await kalshi_odds.get_multipliers('Jordan', 'Argentina')
            finally:
                kalshi_odds.ENABLED = original_enabled
                kalshi_odds.fetch_open_events = original_fetch

        import asyncio
        result = asyncio.run(run())

        self.assertEqual(result['HOME_TEAM']['multiplier'], 5.0)
        self.assertEqual(result['AWAY_TEAM']['multiplier'], 4.0)
        self.assertEqual(result['DRAW']['multiplier'], 2.0)

    def test_status_available_without_matching_market(self):
        async def run():
            async def fake_fetch(session=None, limit=200):
                return {'available': True, 'events': []}
            original_enabled = kalshi_odds.ENABLED
            original_fetch = kalshi_odds.fetch_open_events_status
            kalshi_odds.ENABLED = True
            kalshi_odds.fetch_open_events_status = fake_fetch
            try:
                return await kalshi_odds.get_multiplier_status('Jordan', 'Argentina', 'AWAY_TEAM')
            finally:
                kalshi_odds.ENABLED = original_enabled
                kalshi_odds.fetch_open_events_status = original_fetch

        import asyncio
        result = asyncio.run(run())

        self.assertTrue(result['enabled'])
        self.assertTrue(result['available'])
        self.assertIsNone(result['match'])

    def test_status_unavailable_allows_local_fallback(self):
        async def run():
            async def fake_fetch(session=None, limit=200):
                return {'available': False, 'events': []}
            original_enabled = kalshi_odds.ENABLED
            original_fetch = kalshi_odds.fetch_open_events_status
            kalshi_odds.ENABLED = True
            kalshi_odds.fetch_open_events_status = fake_fetch
            try:
                return await kalshi_odds.get_multiplier_status('Jordan', 'Argentina', 'AWAY_TEAM')
            finally:
                kalshi_odds.ENABLED = original_enabled
                kalshi_odds.fetch_open_events_status = original_fetch

        import asyncio
        result = asyncio.run(run())

        self.assertTrue(result['enabled'])
        self.assertFalse(result['available'])
        self.assertIsNone(result['match'])


if __name__ == '__main__':
    unittest.main()
