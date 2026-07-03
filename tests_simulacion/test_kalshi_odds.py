import unittest

import kalshi_odds
from cogs import betting_cog


class TestKalshiOddsMatching(unittest.TestCase):
    def test_quote_label_formatting(self):
        self.assertEqual(betting_cog._with_quote('Canada', 1.5), 'Canada [x1.50]')
        self.assertEqual(betting_cog._with_quote('Canada', None), 'Canada')

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
        self.assertEqual(draw['multiplier'], 100.0)

    def test_matches_cote_d_ivoire_to_ivory_coast(self):
        events = [
            {
                'event_ticker': 'KXWCGAME-26JUN30CIVNOR',
                'title': 'Ivory Coast vs Norway',
                'sub_title': 'CIV vs NOR (Jun 30)',
                'markets': [
                    {
                        'ticker': 'KXWCGAME-26JUN30CIVNOR-CIV',
                        'title': 'Ivory Coast vs Norway Winner?',
                        'yes_ask_dollars': '0.40',
                    },
                    {
                        'ticker': 'KXWCGAME-26JUN30CIVNOR-NOR',
                        'title': 'Ivory Coast vs Norway Winner?',
                        'yes_ask_dollars': '0.50',
                    },
                ],
            }
        ]

        home = kalshi_odds.match_market_for_prediction(events, "Côte d'Ivoire", 'Norway', 'HOME_TEAM')
        away = kalshi_odds.match_market_for_prediction(events, "Côte d'Ivoire", 'Norway', 'AWAY_TEAM')

        self.assertEqual(home['market_ticker'], 'KXWCGAME-26JUN30CIVNOR-CIV')
        self.assertEqual(home['multiplier'], 2.5)
        self.assertEqual(away['market_ticker'], 'KXWCGAME-26JUN30CIVNOR-NOR')
        self.assertEqual(away['multiplier'], 2.0)

    def test_matches_united_states_to_usa_and_bosnia_variants(self):
        events = [
            {
                'event_ticker': 'KXWCGAME-26JUL01USABIH',
                'title': 'USA vs Bosnia Herzegovina',
                'sub_title': 'USA vs BIH (Jul 1)',
                'markets': [
                    {
                        'ticker': 'KXWCGAME-26JUL01USABIH-USA',
                        'title': 'USA vs Bosnia Herzegovina Winner?',
                        'yes_ask_dollars': '0.25',
                    },
                    {
                        'ticker': 'KXWCGAME-26JUL01USABIH-BIH',
                        'title': 'USA vs Bosnia Herzegovina Winner?',
                        'yes_ask_dollars': '0.50',
                    },
                ],
            }
        ]

        home = kalshi_odds.match_market_for_prediction(events, 'United States', 'Herzegovina', 'HOME_TEAM')
        away = kalshi_odds.match_market_for_prediction(events, 'United States', 'Bosnia and Herzegovina', 'AWAY_TEAM')

        self.assertEqual(home['market_ticker'], 'KXWCGAME-26JUL01USABIH-USA')
        self.assertEqual(home['multiplier'], 4.0)
        self.assertEqual(away['market_ticker'], 'KXWCGAME-26JUL01USABIH-BIH')
        self.assertEqual(away['multiplier'], 2.0)

    def test_matches_cabo_verde_to_cape_verde(self):
        events = [
            {
                'event_ticker': 'KXWCGAME-26JUL03ARGCPV',
                'title': 'Argentina vs Cape Verde',
                'sub_title': 'ARG vs CPV (Jul 3)',
                'markets': [
                    {
                        'ticker': 'KXWCGAME-26JUL03ARGCPV-ARG',
                        'title': 'Argentina vs Cape Verde Winner?',
                        'yes_ask_dollars': '0.20',
                    },
                    {
                        'ticker': 'KXWCGAME-26JUL03ARGCPV-CPV',
                        'title': 'Argentina vs Cape Verde Winner?',
                        'yes_ask_dollars': '0.40',
                    },
                    {
                        'ticker': 'KXWCGAME-26JUL03ARGCPV-TIE',
                        'title': 'Argentina vs Cape Verde Winner?',
                        'yes_ask_dollars': '0.50',
                    },
                ],
            }
        ]

        home = kalshi_odds.match_market_for_prediction(events, 'Argentina', 'Cabo Verde', 'HOME_TEAM')
        away = kalshi_odds.match_market_for_prediction(events, 'Argentina', 'Cabo Verde', 'AWAY_TEAM')
        draw = kalshi_odds.match_market_for_prediction(events, 'Argentina', 'Cabo Verde', 'DRAW')

        self.assertEqual(home['market_ticker'], 'KXWCGAME-26JUL03ARGCPV-ARG')
        self.assertEqual(home['multiplier'], 5.0)
        self.assertEqual(away['market_ticker'], 'KXWCGAME-26JUL03ARGCPV-CPV')
        self.assertEqual(away['multiplier'], 2.5)
        self.assertEqual(draw['market_ticker'], 'KXWCGAME-26JUL03ARGCPV-TIE')
        self.assertEqual(draw['multiplier'], 2.0)

    def test_matches_turkiye_to_turkey(self):
        events = [
            {
                'event_ticker': 'KXWCGAME-26JUL03TURUSA',
                'title': 'Turkey vs USA',
                'sub_title': 'TUR vs USA (Jul 3)',
                'markets': [
                    {
                        'ticker': 'KXWCGAME-26JUL03TURUSA-TUR',
                        'title': 'Turkey vs USA Winner?',
                        'yes_ask_dollars': '0.25',
                    },
                    {
                        'ticker': 'KXWCGAME-26JUL03TURUSA-USA',
                        'title': 'Turkey vs USA Winner?',
                        'yes_ask_dollars': '0.50',
                    },
                ],
            }
        ]

        home = kalshi_odds.match_market_for_prediction(events, 'Türkiye', 'USA', 'HOME_TEAM')
        away = kalshi_odds.match_market_for_prediction(events, 'Türkiye', 'USA', 'AWAY_TEAM')

        self.assertEqual(home['market_ticker'], 'KXWCGAME-26JUL03TURUSA-TUR')
        self.assertEqual(home['multiplier'], 4.0)
        self.assertEqual(away['market_ticker'], 'KXWCGAME-26JUL03TURUSA-USA')
        self.assertEqual(away['multiplier'], 2.0)

    def test_normalizes_common_fifa_country_variants(self):
        cases = {
            'United States of America': 'united states',
            'Republic of Korea': 'south korea',
            'Türkiye': 'turkey',
            'China PR': 'china',
            'Iran Islamic Republic': 'iran',
            'UAE': 'united arab emirates',
            'Kyrgyz Republic': 'kyrgyzstan',
            'Syrian Arab Republic': 'syria',
            'Russian Federation': 'russia',
            'Congo DR': 'democratic republic of congo',
        }

        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(kalshi_odds.normalize_name(source), expected)

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

    def test_status_unavailable_blocks_bet(self):
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
