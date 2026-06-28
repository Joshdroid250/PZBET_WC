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


if __name__ == '__main__':
    unittest.main()
