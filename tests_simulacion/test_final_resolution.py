import unittest


FIFA_FINISHED_JSON = {
    "matches": [
        {
            "id": "znr9ser4v1de",
            "status": "FINISHED",
            "homeTeam": {"name": "Mexico"},
            "awayTeam": {"name": "South Africa"},
            "score": {
                "winner": "HOME_TEAM",
                "fullTime": {"home": 2, "away": 0},
            },
        },
        {
            "id": "m889n7jrhmto",
            "status": "FINISHED",
            "homeTeam": {"name": "Haiti"},
            "awayTeam": {"name": "Scotland"},
            "score": {
                "winner": "AWAY_TEAM",
                "fullTime": {"home": 0, "away": 1},
            },
        },
    ]
}

INTERNAL_DB_MATCHES = [
    ("znr9ser4v1de", "Mexico", "South Africa"),
    ("m889n7jrhmto", "Haiti", "Scotland"),
    ("other_id", "Netherlands", "Japan"),
]


class TestFinalMatchResolution(unittest.TestCase):
    def test_payout_logic_simulation(self):
        fifa_matches = FIFA_FINISHED_JSON["matches"]
        resolved_count = 0

        for f_match in fifa_matches:
            f_id = f_match["id"]
            f_status = f_match["status"]
            f_winner = f_match["score"]["winner"]

            internal_match = next((m for m in INTERNAL_DB_MATCHES if m[0] == f_id), None)

            if internal_match and f_status == "FINISHED":
                resolved_count += 1
                self.assertIn(f_winner, ["HOME_TEAM", "AWAY_TEAM", "DRAW"])

                if f_id == "znr9ser4v1de":
                    self.assertEqual(f_winner, "HOME_TEAM")
                if f_id == "m889n7jrhmto":
                    self.assertEqual(f_winner, "AWAY_TEAM")

        self.assertEqual(resolved_count, 2)


if __name__ == "__main__":
    unittest.main()
