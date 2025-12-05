import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import sys
import os

# Add parent directory to path to import tool
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import FPLManager


class TestFPLManager(unittest.TestCase):
    def setUp(self):
        self.manager = FPLManager()

    @patch("tool.FPLManager.get_bootstrap_static")
    def test_fetch_and_filter_data(self, mock_get_static):
        # Mock data
        mock_data = {
            "elements": [
                {
                    "id": 1,
                    "web_name": "Player A",
                    "team": 1,
                    "element_type": 1,  # GK
                    "form": "5.0",
                    "points_per_game": "4.5",
                    "now_cost": 50,
                    "chance_of_playing_next_round": 100,
                    "selected_by_percent": "10.0",
                    "status": "a",
                    "minutes": 500,
                    "penalties_order": None,
                    "direct_freekicks_order": None,
                    "corners_and_indirect_freekicks_order": None,
                },
                {
                    "id": 2,
                    "web_name": "Player B",
                    "team": 1,
                    "element_type": 3,  # MID
                    "form": "2.0",
                    "points_per_game": "3.0",
                    "now_cost": 120,  # Expensive
                    "chance_of_playing_next_round": 100,
                    "selected_by_percent": "50.0",
                    "status": "a",
                    "minutes": 1000,
                    "penalties_order": 1,
                    "direct_freekicks_order": None,
                    "corners_and_indirect_freekicks_order": None,
                },
            ],
            "teams": [
                {
                    "id": 1,
                    "name": "Team 1",
                    "strength_defence_home": 1000,
                    "strength_defence_away": 1000,
                    "strength_attack_home": 1000,
                    "strength_attack_away": 1000,
                }
            ],
        }
        mock_get_static.return_value = mock_data

        # Test Budget Filter
        teams, df = self.manager.fetch_and_filter_data(role_id=None, max_budget=6.0)
        self.assertIn(1, df["id"].values)
        self.assertNotIn(2, df["id"].values)  # Too expensive

        # Test Role Filter
        teams, df = self.manager.fetch_and_filter_data(role_id=3, max_budget=15.0)
        self.assertNotIn(1, df["id"].values)  # GK specific
        self.assertIn(2, df["id"].values)  # MID

    def test_calculate_xp(self):
        # Setup basic player and context
        player = {
            "id": 1,
            "team": 1,
            "position": 3,  # MID
            "points_per_game": 5.0,
            "form": 5.0,
            "chance_of_playing": 100,
            "penalties_order": 1,
        }
        teams = {
            1: {"name": "My Team", "strength_a": 1000, "strength_d": 1000},
            2: {"name": "Opponent", "strength_a": 1000, "strength_d": 1000},
        }
        # Mock easy fixture
        fixtures = [
            {"team_h": 1, "team_a": 2, "is_home": True, "difficulty": 2, "event": 10},
        ]
        history = [
            {
                "total_points": 5,
                "minutes": 90,
                "expected_goals": 0.5,
                "expected_assists": 0.2,
            },
            {
                "total_points": 5,
                "minutes": 90,
                "expected_goals": 0.5,
                "expected_assists": 0.2,
            },
            {
                "total_points": 5,
                "minutes": 90,
                "expected_goals": 0.5,
                "expected_assists": 0.2,
            },
        ]

        # Use Threat Model (default)
        xp, gw_points, breakdowns = self.manager.calculate_xp(
            player, teams, fixtures, history
        )

        # Expect positive XP
        self.assertGreater(xp, 0)
        self.assertIn("GW10", gw_points)

        # Verify Penalty Bonus applied (1.15x multiplier check implies strictly greater than base logic)
        # Just ensure it runs without error and returns reasonable structure
        self.assertIsInstance(gw_points, dict)
        self.assertIsInstance(breakdowns, dict)

    def test_optimize_lineup(self):
        # Create a mock squad of 15 players
        # 2 GK, 5 DEF, 5 MID, 3 FWD
        squad = []
        # GKs
        squad.append(
            {"id": 1, "web_name": "GK1", "position": 1, "xp": 4.0, "cap_score": 4.0}
        )
        squad.append(
            {"id": 2, "web_name": "GK2", "position": 1, "xp": 3.0, "cap_score": 3.0}
        )
        # DEFs
        for i in range(5):
            squad.append(
                {
                    "id": 10 + i,
                    "web_name": f"DEF{i}",
                    "position": 2,
                    "xp": 3.0 + i,
                    "cap_score": 3.0 + i,
                }
            )
        # MIDs
        for i in range(5):
            squad.append(
                {
                    "id": 20 + i,
                    "web_name": f"MID{i}",
                    "position": 3,
                    "xp": 4.0 + i,
                    "cap_score": 5.0 + i,
                }
            )
        # FWDs
        for i in range(3):
            squad.append(
                {
                    "id": 30 + i,
                    "web_name": f"FWD{i}",
                    "position": 4,
                    "xp": 5.0 + i,
                    "cap_score": 6.0 + i,
                }
            )

        starters, bench, cap, vice = self.manager._optimize_lineup(squad)

        self.assertEqual(len(starters), 11)
        self.assertEqual(len(bench), 4)

        # Check mandatory positions
        n_gk = len([p for p in starters if p["position"] == 1])
        n_def = len([p for p in starters if p["position"] == 2])
        n_fwd = len([p for p in starters if p["position"] == 4])

        self.assertEqual(n_gk, 1)
        self.assertGreaterEqual(n_def, 3)
        self.assertGreaterEqual(n_fwd, 1)

        self.assertIsNotNone(cap)
        self.assertIsNotNone(vice)

        # Check Captain has highest cap_score
        # MID4 has score 9.0 (5.0+4), FWD2 has 8.0 (6.0+2)
        self.assertEqual(cap["web_name"], "MID4")


if __name__ == "__main__":
    unittest.main()
