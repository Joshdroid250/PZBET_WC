import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api_football


class TestTeamFlags(unittest.TestCase):
    def test_team_flag_emoji_uses_fifa_tla(self):
        team = {
            "name": "Korea Republic",
            "tla": "KOR",
            "crest": "https://api.fifa.com/api/v3/picture/flags-{format}-{size}/KOR",
        }

        self.assertEqual(
            api_football.get_team_flag_emoji(team),
            api_football.get_flag_emoji("South Korea"),
        )

    def test_team_flag_url_uses_fifa_crest(self):
        team = {
            "name": "Korea Republic",
            "tla": "KOR",
            "crest": "https://api.fifa.com/api/v3/picture/flags-{format}-{size}/KOR",
        }

        self.assertEqual(
            api_football.get_team_flag_url(team),
            "https://api.fifa.com/api/v3/picture/flags-png-w160/KOR",
        )


if __name__ == "__main__":
    unittest.main()
