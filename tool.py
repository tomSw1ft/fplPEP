import requests
import json
import os
import time
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional

# --- CONFIGURATION ---
NEXT_N_GW = 5
USE_THREAT_MODEL = True  # Toggle for xG/xA based model
BASE_URL = "https://fantasy.premierleague.com/api/"
CUSTOM_FDR_FILE = "custom_fdr.json"

# --- CONSTANTS ---


class FPLManager:
    CACHE_DURATION = 300  # 5 minutes

    def __init__(self):
        self.session = requests.Session()
        self.bootstrap_static_cache = None
        self.last_fetch_time = 0
        self.team_short_names = {}
        self.custom_fdr = self.load_custom_fdr()

        # Cache
        self.player_summary_cache = {}

        # Model Configuration (Default Parameters)
        self.model_config = {
            "form_weights": [1.0, 0.9, 0.8, 0.7, 0.6],
            "fixture_diff_factor": 0.05,
            "home_boost": 1.05,
            "away_penalty": 0.95,
            "bonus_multiplier": 1.1,
            "clean_sheet_base": 0.30,
        }

    def load_custom_fdr(self):
        if os.path.exists(CUSTOM_FDR_FILE):
            try:
                with open(CUSTOM_FDR_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading custom FDR: {e}")
        return {}

    def save_custom_fdr(self, new_settings=None):
        if new_settings:
            self.custom_fdr = new_settings
        try:
            with open(CUSTOM_FDR_FILE, "w") as f:
                json.dump(self.custom_fdr, f, indent=4)
        except Exception as e:
            print(f"Error saving custom FDR: {e}")

    def get_json(self, url):
        try:
            response = self.session.get(url)
            if response.status_code != 200:
                raise Exception(
                    f"API request failed for {url} with status {response.status_code}"
                )
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Network error fetching {url}: {e}")

    def get_bootstrap_static(self):
        """Fetches bootstrap-static data with caching."""
        current_time = time.time()
        if (
            self.bootstrap_static_cache
            and (current_time - self.last_fetch_time) < self.CACHE_DURATION
        ):
            return self.bootstrap_static_cache

        data = self.get_json(BASE_URL + "bootstrap-static/")
        self.bootstrap_static_cache = data
        self.last_fetch_time = current_time

        # Update short names cache
        if "teams" in data:
            self.team_short_names = {t["name"]: t["short_name"] for t in data["teams"]}

        return data

    def get_current_event_id(self):
        data = self.get_bootstrap_static()
        for event in data["events"]:
            if event["is_current"]:
                return event["id"]
        # Fallback if no current event (e.g. pre-season), try next
        for event in data["events"]:
            if event["is_next"]:
                return max(1, event["id"] - 1)
        return 1

    def get_next_event_id(self):
        """Efficiently retrieves the next event ID."""
        data = self.get_bootstrap_static()
        for event in data["events"]:
            if event["is_next"]:
                return event["id"]
        # Fallback
        current = self.get_current_event_id()
        return current + 1

    def get_team_picks(self, team_id, event_id):
        url = BASE_URL + f"entry/{team_id}/event/{event_id}/picks/"
        return self.get_json(url)

    def get_processed_teams(self):
        data = self.get_bootstrap_static()
        return {
            t["id"]: {
                "name": t["name"],
                "strength_d": t["strength_defence_home"]
                if t["id"]
                else t["strength_defence_away"],
                "strength_a": t["strength_attack_home"]
                if t["id"]
                else t["strength_attack_away"],
            }
            for t in data["teams"]
        }

    def fetch_and_filter_data(self, role_id, max_budget, include_ids=None):
        print("Fetching live FPL data...")
        data = self.get_bootstrap_static()

        # Process Teams
        teams = self.get_processed_teams()

        # Identify teams with a valid #1 Penalty Taker for promotion logic
        teams_with_p1 = {
            p["team"] for p in data["elements"] if p["penalties_order"] == 1
        }

        # Convert to DataFrame immediately
        df = pd.DataFrame(data["elements"])

        # Create mandatory set for fast lookup
        include_ids_set = set(include_ids) if include_ids else set()

        # Vectorized Filtering
        # 1. Mandatory Candidates (Always keep)
        mandatory_mask = df["id"].isin(include_ids_set)

        # 2. Standard Candidates (Apply filters)
        # Check Role (if role_id is provided)
        if role_id is not None:
            role_mask = df["element_type"] == role_id
        else:
            role_mask = pd.Series(True, index=df.index)

        # Check Budget, Status, Minutes
        standard_mask = (
            role_mask
            & ((df["now_cost"] / 10) <= max_budget)
            & (df["status"].isin(["a", "d"]))
            & (df["minutes"] > 200)
        )

        # Combine
        final_mask = mandatory_mask | standard_mask
        filtered_df = df[final_mask].copy()

        if filtered_df.empty:
            return (
                teams,
                pd.DataFrame(),
            )  # Return empty DF with correct columns if needed?

        # Vectorized Renaming and Calculations
        filtered_df["now_cost"] = filtered_df["now_cost"] / 10
        filtered_df["position"] = filtered_df["element_type"]

        # Penalty Order Logic (Apply Fallback)
        # If order is 2 and team has no #1, promote to 1
        # Helper function for apply (vectorizing conditional logic involving set lookups is tricky but apply is fine here)
        def adjust_penalties(row):
            if row["penalties_order"] == 2 and row["team"] not in teams_with_p1:
                return 1
            return row["penalties_order"]

        filtered_df["penalties_order"] = filtered_df.apply(adjust_penalties, axis=1)

        # Select and Rename Columns
        cols_to_keep = {
            "id": "id",
            "web_name": "web_name",
            "team": "team",
            "position": "position",
            "form": "form",
            "points_per_game": "points_per_game",
            "now_cost": "now_cost",
            "chance_of_playing_next_round": "chance_of_playing",
            "selected_by_percent": "selected_by_percent",
            "status": "status",
            "penalties_order": "penalties_order",
            "direct_freekicks_order": "direct_freekicks_order",
            "corners_and_indirect_freekicks_order": "corners_and_indirect_freekicks_order",
        }

        # Ensure type strictness for numeric cols
        filtered_df["form"] = pd.to_numeric(filtered_df["form"])
        filtered_df["points_per_game"] = pd.to_numeric(filtered_df["points_per_game"])
        filtered_df["selected_by_percent"] = pd.to_numeric(
            filtered_df["selected_by_percent"]
        )

        # Final subset
        result_df = filtered_df.rename(columns=cols_to_keep)[
            list(cols_to_keep.values())
        ]

        return teams, result_df

    def search_player(self, query):
        """Searches for players by name."""
        data = self.get_bootstrap_static()
        query = query.lower()
        results = []

        for p in data["elements"]:
            full_name = f"{p['first_name']} {p['second_name']}".lower()
            if query in p["web_name"].lower() or query in full_name:
                results.append(
                    {
                        "id": p["id"],
                        "web_name": p["web_name"],
                        "team": p["team"],
                        "position": p["element_type"],
                        "form": float(p["form"]),
                        "points_per_game": float(p["points_per_game"]),
                        "now_cost": p["now_cost"] / 10,
                        "chance_of_playing": p["chance_of_playing_next_round"],
                        "selected_by_percent": float(p["selected_by_percent"]),
                        "status": p["status"],
                        "penalties_order": p["penalties_order"],
                        "direct_freekicks_order": p["direct_freekicks_order"],
                        "corners_and_indirect_freekicks_order": p[
                            "corners_and_indirect_freekicks_order"
                        ],
                    }
                )
        return results

    def get_player_summary(self, element_id):
        """Fetches detailed summary for a specific player (fixtures, history)."""
        if element_id in self.player_summary_cache:
            return self.player_summary_cache[element_id]

        url = f"{BASE_URL}element-summary/{element_id}/"
        try:
            data = self.get_json(url)
            self.player_summary_cache[element_id] = (
                data.get("fixtures", []),
                data.get("history", []),
            )
            return self.player_summary_cache[element_id]
        except Exception as e:
            print(f"Error fetching summary for player {element_id}: {e}")
            return [], []

    def get_team_details(self, team_id):
        """Fetches team entry details including bank."""
        return self.get_json(BASE_URL + f"entry/{team_id}/")

    def get_all_team_fixtures(self, next_n_gw=None):
        """Fetches upcoming fixtures for all teams for FDR grid."""
        data = self.get_bootstrap_static()
        teams = self.get_processed_teams()

        all_fixtures = self.get_json(BASE_URL + "fixtures/")

        start_event = 1
        for event in data["events"]:
            if not event["finished"]:
                start_event = event["id"]
                break

        future_fixtures = [
            f for f in all_fixtures if f.get("event") and f["event"] >= start_event
        ]

        team_schedule = {t_id: [] for t_id in teams}

        for f in future_fixtures:
            if next_n_gw and f["event"] >= start_event + next_n_gw:
                continue

            h = f["team_h"]
            a = f["team_a"]

            diff_h = self.get_fixture_difficulty(f, h, teams)
            diff_a = self.get_fixture_difficulty(f, a, teams)

            event = f["event"]

            if h in team_schedule:
                team_schedule[h].append(
                    {
                        "event": event,
                        "opponent": teams[a]["name"],
                        "difficulty": diff_h,
                        "is_home": True,
                        "short_name": self.team_short_names.get(
                            teams[a]["name"], teams[a]["name"][:3].upper()
                        ),
                    }
                )

            if a in team_schedule:
                team_schedule[a].append(
                    {
                        "event": event,
                        "opponent": teams[h]["name"],
                        "difficulty": diff_a,
                        "is_home": False,
                        "short_name": self.team_short_names.get(
                            teams[h]["name"], teams[h]["name"][:3].upper()
                        ),
                    }
                )

        results = []
        for t_id, fixtures in team_schedule.items():
            fixtures.sort(key=lambda x: x["event"])
            if next_n_gw:
                fixtures = fixtures[:next_n_gw]

            total_diff = sum(f["difficulty"] for f in fixtures)

            results.append(
                {
                    "team_name": teams[t_id]["name"],
                    "fixtures": fixtures,
                    "total_difficulty": total_diff,
                }
            )

        return sorted(results, key=lambda x: x["total_difficulty"])

    def get_fixture_difficulty(self, fixture, team_id, teams):
        """Calculates fixture difficulty based on opponent strength."""
        if fixture["team_h"] == team_id:
            opponent_id = fixture["team_a"]
            is_home = True
        else:
            opponent_id = fixture["team_h"]
            is_home = False

        opponent = teams[opponent_id]
        opponent_name = opponent["name"]

        # Check Custom FDR first
        if self.custom_fdr and opponent_name in self.custom_fdr:
            # Custom FDR structure: "Arsenal": {"H": 5, "A": 4}
            # "H" means difficulty when Arsenal is HOME.
            # "A" means difficulty when Arsenal is AWAY.

            if is_home:
                # We are Home, Opponent is Away.
                # We want difficulty of Opponent (Away).
                custom_val = self.custom_fdr[opponent_name].get("A")
            else:
                # We are Away, Opponent is Home.
                # We want difficulty of Opponent (Home).
                custom_val = self.custom_fdr[opponent_name].get("H")

            if custom_val is not None:
                return int(custom_val)

        # Base difficulty from FDR (if available in future, currently using strength)
        # Using team strength directly

        if is_home:
            # We are home, opponent is away. Use opponent's away strength vs our home strength?
            # Simplified: Just use opponent overall strength
            opponent_strength = (opponent["strength_d"] + opponent["strength_a"]) / 2
        else:
            opponent_strength = (opponent["strength_d"] + opponent["strength_a"]) / 2

        # Normalize to 1-5 scale roughly
        # 1000 is avg.
        # < 1050: 2
        # 1050-1150: 3
        # 1150-1250: 4
        # > 1250: 5

        if opponent_strength < 1050:
            return 2
        elif opponent_strength < 1150:
            return 3
        elif opponent_strength < 1250:
            return 4
        else:
            return 5

    def _calculate_fixture_multiplier(self, difficulty):
        factor = self.model_config.get("fixture_diff_factor", 0.08)
        return 1.0 + ((3 - difficulty) * factor)

    def _calculate_matchup_multiplier(
        self, player, opponent_difficulty, my_team_difficulty
    ):
        # opponent_difficulty: 1 (Easy) to 5 (Hard). Represents Opponent Strength.
        # my_team_difficulty: 1 (Easy) to 5 (Hard). Represents My Team Strength.

        if player["position"] in [1, 2]:  # GK/DEF
            # We want Opponent to be Weak (Low Difficulty)
            if opponent_difficulty <= 2:
                # Weak Opponent
                if my_team_difficulty <= 2:
                    return 1.0  # Weak vs Weak -> Neutral
                else:
                    return 1.1  # Strong Defense vs Weak Attack -> Advantage
            elif opponent_difficulty >= 4:
                # Strong Opponent
                if my_team_difficulty >= 4:
                    return 1.0  # Strong Defense holds up -> Neutral
                else:
                    return 0.9  # Weak Defense vs Strong Attack -> Disadvantage
            else:
                return 1.0

        else:  # MID/FWD
            # We want Opponent to be Weak (Low Difficulty)
            if opponent_difficulty <= 2:
                # Weak Opponent Defense
                if my_team_difficulty <= 2:
                    return 1.0  # Weak Attack vs Weak Defense -> Neutral
                else:
                    return 1.1  # Strong Attack vs Weak Defense -> Advantage
            elif opponent_difficulty >= 4:
                # Strong Opponent Defense
                if my_team_difficulty >= 4:
                    return 1.0  # Strong Attack breaks through -> Neutral
                else:
                    return 0.9  # Weak Attack vs Strong Defense -> Disadvantage
            else:
                return 1.0

    def _calculate_weighted_form(self, history):
        """Calculates weighted form giving more importance to recent games."""
        if not history:
            return 0.0

        # Use last 5 games
        recent = history[-5:]
        # Weights (most recent first)
        weights = self.model_config.get("form_weights", [1.0, 0.9, 0.8, 0.7, 0.6])

        total_weighted_pts = 0
        total_weights = 0

        # Iterate backwards
        for i, game in enumerate(reversed(recent)):
            if i < len(weights):
                w = weights[i]
                total_weighted_pts += game["total_points"] * w
                total_weights += w

        return total_weighted_pts / total_weights if total_weights > 0 else 0.0

    def _calculate_weighted_metric(self, history, metric_key):
        """Calculates weighted average of a specific metric (e.g., expected_goals)."""
        if not history:
            return 0.0

        # Use last 5 games
        recent = history[-5:]
        weights = self.model_config.get("form_weights", [1.0, 0.9, 0.8, 0.7, 0.6])

        total_weighted = 0
        total_weights = 0

        for i, game in enumerate(reversed(recent)):
            if i < len(weights):
                w = weights[i]
                # Handle string values if necessary (API sometimes returns strings)
                val = float(game.get(metric_key, 0) or 0)
                total_weighted += val * w
                total_weights += w

        return total_weighted / total_weights if total_weights > 0 else 0.0

    def _calculate_weighted_minutes(self, history):
        """Calculates weighted average of minutes played."""
        return self._calculate_weighted_metric(history, "minutes")

    def _calculate_cs_probability(self, my_team_difficulty, opponent_difficulty):
        """Estimates Clean Sheet probability (0.0 to 1.0) using FDR."""
        # my_team_difficulty: Proxy for My Defense Strength (High = Strong)
        # opponent_difficulty: Proxy for Opponent Attack Strength (High = Strong)

        diff = my_team_difficulty - opponent_difficulty
        # Range: -4 to +4

        base_prob = self.model_config.get("clean_sheet_base", 0.30)
        adjustment = diff * 0.10

        prob = base_prob + adjustment
        return max(0.05, min(0.80, prob))

    def _calculate_save_points(self, my_team_difficulty, opponent_difficulty):
        """Estimates Save Points for GKs using FDR."""
        # More saves if My Defense is Weak (Low) and Opponent Attack is Strong (High)
        diff = opponent_difficulty - my_team_difficulty

        if diff >= 2:
            return 1.0  # ~3 saves
        elif diff > 0:
            return 0.5  # ~1-2 saves
        return 0.2

    def calculate_xp(self, player, teams, fixtures, history):
        total_xp = 0
        gw_points = {}
        breakdowns = {}  # New: Store breakdown per GW

        # 1. Weighted Form & Minutes
        weighted_form = self._calculate_weighted_form(history)
        expected_minutes = self._calculate_weighted_minutes(history)

        # Calculate expected appearance points based on minutes
        if expected_minutes >= 60:
            expected_app_points = 2.0
        elif expected_minutes > 0:
            expected_app_points = 1.0
        else:
            expected_app_points = 0.0

        # 2. Base Potential
        if USE_THREAT_MODEL:
            # THREAT MODEL: Based on xG and xA
            weighted_xg = self._calculate_weighted_metric(history, "expected_goals")
            weighted_xa = self._calculate_weighted_metric(history, "expected_assists")

            # Points per Goal
            pos = player["position"]
            if pos == 1 or pos == 2:  # GK/DEF
                pts_per_goal = 6
            elif pos == 3:  # MID
                pts_per_goal = 5
            else:  # FWD
                pts_per_goal = 4

            xp_goals = weighted_xg * pts_per_goal
            xp_assists = weighted_xa * 3

            # Bonus Potential & Explosiveness
            # Boosted to 1.3 to account for BPS and high-performing variance
            bonus_mult = self.model_config.get("bonus_multiplier", 1.3)
            base_attack_potential = (xp_goals + xp_assists) * bonus_mult

        else:
            # LEGACY MODEL: Based on Past Points
            # Scale PPG by expected minutes ratio (assuming 90 mins is standard)
            # If they usually play 90, ratio is 1.0. If they play 0, ratio is 0.0.
            minutes_ratio = min(1.0, expected_minutes / 90.0)

            base_attack_potential = (weighted_form * 0.6) + (
                float(player["points_per_game"]) * minutes_ratio * 0.4
            )

        upcoming = fixtures[:NEXT_N_GW]

        for f in upcoming:
            is_home = f["is_home"]
            opponent_id = f["team_a"] if is_home else f["team_h"]

            # Safety check for unknown teams
            if opponent_id not in teams:
                continue

            opponent = teams[opponent_id]
            # my_team = teams[player["team"]] # Unused

            # --- FIXTURE MODIFIERS ---
            # difficulty = Opponent Strength (Difficulty for Me)
            difficulty = self.get_fixture_difficulty(f, player["team"], teams)

            # my_team_difficulty = My Strength (Difficulty for Opponent)
            my_team_difficulty = self.get_fixture_difficulty(f, opponent_id, teams)

            fixture_mult = self._calculate_fixture_multiplier(difficulty)

            # --- MATCHUP MODIFIERS ---
            matchup_mult = self._calculate_matchup_multiplier(
                player, difficulty, my_team_difficulty
            )

            # --- HOME ADVANTAGE ---
            home_boost = self.model_config.get("home_boost", 1.1)
            away_penalty = self.model_config.get("away_penalty", 0.95)
            venue_mult = home_boost if is_home else away_penalty

            # --- POSITIONAL LOGIC ---

            # A. Clean Sheet Probability
            cs_prob = self._calculate_cs_probability(my_team_difficulty, difficulty)
            if is_home:
                cs_prob += 0.05

            # B. Expected Points Calculation
            gw_xp = 0

            # Breakdown components
            breakdown = {
                "opponent": opponent["name"],
                "is_home": is_home,
                "difficulty": difficulty,
                "base_attack": round(base_attack_potential, 2),
                "fixture_mult": round(fixture_mult, 2),
                "matchup_mult": round(matchup_mult, 2),
                "venue_mult": round(venue_mult, 2),
                "cs_prob": round(cs_prob, 2),
                "expected_mins": round(expected_minutes, 1),
                "app_points": 0.0,
                "save_points": 0.0,
                "clean_sheet_points": 0.0,
                "attack_points": 0.0,
            }

            if USE_THREAT_MODEL:
                # THREAT MODEL: Separate Appearance from Performance
                gw_xp += expected_app_points  # Unscaled by difficulty
                breakdown["app_points"] = expected_app_points

                performance_xp = 0
                if player["position"] == 1:  # GK
                    cs_pts = cs_prob * 4.0
                    save_pts = self._calculate_save_points(
                        my_team_difficulty, difficulty
                    )
                    performance_xp += cs_pts + save_pts
                    breakdown["clean_sheet_points"] = round(cs_pts, 2)
                    breakdown["save_points"] = round(save_pts, 2)

                elif player["position"] == 2:  # DEF
                    cs_pts = cs_prob * 4.0
                    att_pts = base_attack_potential * 0.1 * matchup_mult
                    performance_xp += cs_pts + att_pts
                    breakdown["clean_sheet_points"] = round(cs_pts, 2)
                    breakdown["attack_points"] = round(att_pts, 2)

                elif player["position"] == 3:  # MID
                    cs_pts = cs_prob * 1.0
                    att_pts = base_attack_potential * 0.8 * matchup_mult
                    performance_xp += cs_pts + att_pts
                    breakdown["clean_sheet_points"] = round(cs_pts, 2)
                    breakdown["attack_points"] = round(att_pts, 2)

                elif player["position"] == 4:  # FWD
                    att_pts = base_attack_potential * 1.0 * matchup_mult
                    performance_xp += att_pts
                    breakdown["attack_points"] = round(att_pts, 2)

                # Apply multipliers to performance only
                performance_xp *= fixture_mult * venue_mult
                gw_xp += performance_xp

            else:
                # LEGACY MODEL: Everything scaled (Appearance baked in)
                step_xp = 0
                if player["position"] == 1:  # GK
                    step_xp += cs_prob * 4.0
                    step_xp += self._calculate_save_points(
                        my_team_difficulty, difficulty
                    )
                elif player["position"] == 2:  # DEF
                    step_xp += cs_prob * 4.0
                    step_xp += base_attack_potential * 0.1 * matchup_mult
                elif player["position"] == 3:  # MID
                    step_xp += cs_prob * 1.0
                    step_xp += base_attack_potential * 0.8 * matchup_mult
                elif player["position"] == 4:  # FWD
                    step_xp += base_attack_potential * 1.0 * matchup_mult

                step_xp *= fixture_mult * venue_mult
                gw_xp += step_xp

            # --- SET PIECES ---
            # --- SET PIECES ---
            if player.get("penalties_order") == 1:
                gw_xp *= 1.15
                breakdown["pen_bonus"] = 1.15

            if (
                player.get("direct_freekicks_order") == 1
                or player.get("corners_and_indirect_freekicks_order") == 1
            ):
                gw_xp *= 1.05
                breakdown["set_piece_bonus"] = 1.05

            # Adjust for availability (e.g. 75% flag)
            chance = player["chance_of_playing"]
            if pd.isna(chance):
                chance = 100
            prob = chance / 100
            breakdown["chance_of_playing"] = chance

            final_gw_xp = gw_xp * prob
            total_xp += final_gw_xp

            breakdown["final_xp"] = round(final_gw_xp, 2)

            # Store per-GW points
            gw_event = f.get("event")
            if gw_event:
                gw_key = f"GW{gw_event}"
                gw_points[gw_key] = round(final_gw_xp, 2)
                breakdowns[gw_key] = breakdown

            # Enrich fixture data for GUI
            f["opponent"] = (
                opponent["short_name"] if "short_name" in opponent else opponent["name"]
            )
            f["xp"] = final_gw_xp

        return total_xp, gw_points, breakdowns

    def _calculate_cap_score(self, player, next_gw_xp, history):
        cap_score = next_gw_xp

        # 1. Explosiveness (Position Bias)
        if player["position"] in [3, 4]:
            cap_score *= 1.1

        # 2. Ownership (Safety)
        if player["selected_by_percent"] > 30.0:
            cap_score *= 1.05

        # 3. Minutes Security (Risk)
        recent_minutes = (
            [h["minutes"] for h in history[-3:]]
            if len(history) >= 3
            else [h["minutes"] for h in history]
        )
        avg_minutes = sum(recent_minutes) / len(recent_minutes) if recent_minutes else 0

        if avg_minutes < 60:
            cap_score *= 0.5

        return cap_score

    def _calculate_advanced_stats(
        self, player: Dict[str, Any], history: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Calculates advanced statistics based on player history."""
        last_5 = history[-5:] if len(history) >= 5 else history
        total_minutes_l5 = sum(h["minutes"] for h in last_5)
        max_minutes_l5 = len(last_5) * 90

        # 1. Minutes % (Last 5)
        mins_percent_l5 = (
            (total_minutes_l5 / max_minutes_l5 * 100) if max_minutes_l5 > 0 else 0
        )

        # 2. Avg Def Contributions per 90 (Last 5)
        total_def_l5 = sum(h.get("defensive_contribution", 0) for h in last_5)
        def_per_90 = (
            (total_def_l5 / total_minutes_l5 * 90) if total_minutes_l5 > 0 else 0
        )

        # 3. Points per 90 (Last 5)
        total_pts_l5 = sum(h["total_points"] for h in last_5)
        pts_per_90_l5 = (
            (total_pts_l5 / total_minutes_l5 * 90) if total_minutes_l5 > 0 else 0
        )

        # 4. Points per 90 per £m (Last 5)
        price = player["now_cost"]
        pts_per_90_per_m_l5 = (pts_per_90_l5 / price) if price > 0 else 0

        return {
            "mins_percent_l5": mins_percent_l5,
            "def_per_90": def_per_90,
            "pts_per_90_l5": pts_per_90_l5,
            "pts_per_90_per_m_l5": pts_per_90_per_m_l5,
        }

    def _optimize_lineup(
        self, squad_xp: List[Dict[str, Any]]
    ) -> Tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        Optional[Dict[str, Any]],
        Optional[Dict[str, Any]],
    ]:
        """Selects the best starting XI and captain/vice-captain."""
        # Sort by XP
        squad_xp.sort(key=lambda x: x["xp"], reverse=True)

        starters = []
        bench = []

        gks = [p for p in squad_xp if p["position"] == 1]
        defs = [p for p in squad_xp if p["position"] == 2]
        mids = [p for p in squad_xp if p["position"] == 3]
        fwds = [p for p in squad_xp if p["position"] == 4]

        # 1. GK
        if gks:
            starters.append(gks[0])
            if len(gks) > 1:
                bench.extend(gks[1:])

        # 2. Core Outfield (Best 3 DEF, 2 MID, 1 FWD)
        starters.extend(defs[:3])
        starters.extend(mids[:2])
        starters.extend(fwds[:1])

        remaining_outfield = defs[3:] + mids[2:] + fwds[1:]
        remaining_outfield.sort(key=lambda x: x["xp"], reverse=True)

        # 3. Fill remaining 4 spots
        n_def = len([p for p in starters if p["position"] == 2])
        n_mid = len([p for p in starters if p["position"] == 3])
        n_fwd = len([p for p in starters if p["position"] == 4])

        for p in remaining_outfield:
            if len(starters) == 11:
                bench.append(p)
                continue

            if p["position"] == 2 and n_def < 5:
                starters.append(p)
                n_def += 1
            elif p["position"] == 3 and n_mid < 5:
                starters.append(p)
                n_mid += 1
            elif p["position"] == 4 and n_fwd < 3:
                starters.append(p)
                n_fwd += 1
            else:
                bench.append(p)

        # 6. Captaincy
        starters.sort(key=lambda x: x["cap_score"], reverse=True)
        captain = starters[0] if starters else None
        vice_captain = starters[1] if len(starters) > 1 else None

        return starters, bench, captain, vice_captain

    def optimize_team(self, team_id):
        """Optimizes the lineup for a specific team ID."""
        # 1. Get current event to fetch *current* squad
        event_id = self.get_current_event_id()

        # 2. Fetch picks
        picks_data = self.get_team_picks(team_id, event_id)

        # 3. Extract IDs
        my_player_ids = [p["element"] for p in picks_data["picks"]]

        # 4. Optimize
        return self.optimize_specific_squad(my_player_ids)

    def calculate_squad_stats(
        self, my_player_ids: List[int], target_event: int = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Calculates XP and stats for a list of players for the next gameweek."""
        # 1. Get Context
        # event_id = self.get_current_event_id() # Not needed for next event stats
        if target_event:
            next_event = target_event
        else:
            next_event = self.get_next_event_id()

        print(f"Planning for Gameweek {next_event}...")

        # 2. Get All Data
        teams_data, df_all_players = self.fetch_and_filter_data(
            None, 999.0, include_ids=my_player_ids
        )

        if df_all_players.empty:
            return [], next_event

        # Filter for my players
        my_squad = df_all_players[df_all_players["id"].isin(my_player_ids)].copy()

        # 4. Calculate XP and Captaincy Score for all
        # 4. Calculate XP and Captaincy Score for all
        squad_xp = []
        for _, player in my_squad.iterrows():
            # Fetch full summary for history (minutes check)
            fixtures, history = self.get_player_summary(player["id"])

            # FILTER FIXTURES: Start from next_event (Target GW)
            relevant_fixtures = [f for f in fixtures if f.get("event", 0) >= next_event]

            xp, gw_points, breakdowns = self.calculate_xp(
                player, teams_data, relevant_fixtures, history
            )

            # Next GW XP for captaincy
            next_gw_key = f"GW{next_event}"
            next_gw_xp = gw_points.get(next_gw_key, 0.0)

            cap_score = self._calculate_cap_score(player, next_gw_xp, history)

            # Advanced Stats
            stats = self._calculate_advanced_stats(player, history)

            # Combine Data
            p_data = player.to_dict()
            p_data.update(stats)
            # CRITICAL FIX: Optimization uses "xp" key for sorting.
            # We want to optimize for the NEXT GAMEWEEK, not the total 5GW.
            p_data["xp"] = next_gw_xp
            p_data["total_xp"] = xp  # Store Total XP for 5GW
            p_data["cap_score"] = cap_score
            p_data["upcoming_fixtures"] = relevant_fixtures[:NEXT_N_GW]

            p_data["xp_breakdowns"] = breakdowns  # Store breakdowns

            # Add GW points
            for k, v in gw_points.items():
                p_data[k] = v

            squad_xp.append(p_data)

        return squad_xp, next_event

    def optimize_specific_squad(
        self, my_player_ids: List[int], target_event: int = None
    ) -> Tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        Optional[Dict[str, Any]],
        Optional[Dict[str, Any]],
        int,
    ]:
        """Optimizes the lineup for a specific list of player IDs."""
        squad_xp, next_event = self.calculate_squad_stats(my_player_ids, target_event)
        starters, bench, captain, vice_captain = self._optimize_lineup(squad_xp)

        return starters, bench, captain, vice_captain, next_event

    def get_captaincy_candidates(self, team_id):
        """Returns sorted list of captaincy candidates for a team."""
        # 1. Get current event to fetch *current* squad
        event_id = self.get_current_event_id()

        # 2. Fetch picks
        picks_data = self.get_team_picks(team_id, event_id)
        my_player_ids = [p["element"] for p in picks_data["picks"]]

        # 3. Calculate Stats
        squad_xp, next_event = self.calculate_squad_stats(my_player_ids)

        # 4. Sort by Cap Score
        # Filter for valid captains (playing etc) - usually everyone is valid but let's just sort
        candidates = sorted(squad_xp, key=lambda x: x["cap_score"], reverse=True)

        # Map 'web_name' to 'name' for GUI consistency if needed,
        # but GUI uses 'name' which comes from 'web_name' usually in my dict construction?
        # In fetch_and_filter_data: "web_name": p["web_name"]
        # But in optimize_specific_squad => p_data = player.to_dict() => keys are what dataframe has.
        # Dataframe has "web_name".
        # GUI CaptaincyFrame uses: p["name"]
        # So I need to ensure "name" key exists.

        for p in candidates:
            p["name"] = p["web_name"]
            p["team"] = p.get("team_name", "?")

        return candidates, next_event

    def get_model_performance(self, num_weeks=5, team_id=None):
        """
        Backtests the model for the last `num_weeks`.
        Compares predicted points vs actual points for the *actual* squad used in those gameweeks.
        """
        static_data = self.get_bootstrap_static()
        current_event = self.get_current_event_id()
        teams_data = self.get_processed_teams()

        # Identify relevant past gameweeks (finished)
        completed_events = [
            e
            for e in static_data["events"]
            if e["finished"] and e["id"] < current_event
        ]
        if not completed_events:
            return []

        target_events = sorted(completed_events, key=lambda x: x["id"], reverse=True)[
            :num_weeks
        ]
        target_events.reverse()  # Sort Chronologically

        results = []

        for event in target_events:
            gw = event["id"]
            print(f"Analyzing GW{gw}...")

            # 1. Get Squad for that Gameweek
            # If team_id is provided, fetch actual picks.
            if not team_id:
                return []

            try:
                picks_data = self.get_team_picks(team_id, gw)
                squad_ids = [p["element"] for p in picks_data["picks"]]
                captain_id = next(
                    (p["element"] for p in picks_data["picks"] if p["is_captain"]), None
                )
                # Handle Triple Captain? (active_chip == '3xc'). For simplicity, we ignore chips for now.
            except Exception as e:
                print(f"Error fetching picks for GW{gw}: {e}")
                continue

            # 2. Re-construct "Past State" for Players
            gw_total_predicted = 0.0
            gw_total_actual = 0.0

            # Fetch all needed players
            _, df_players = self.fetch_and_filter_data(
                None, 999.0, include_ids=squad_ids
            )

            for _, player in df_players.iterrows():
                fixtures, history = self.get_player_summary(player["id"])

                # Split History
                past_history = [h for h in history if h["round"] < gw]
                actual_games = [h for h in history if h["round"] == gw]
                actual_points = sum(h["total_points"] for h in actual_games)

                # Fabricate "Upcoming Fixture" for Calculate XP
                # Fabricate "Upcoming Fixture" for Calculate XP
                mock_upcoming = []
                for game in actual_games:
                    is_home = game["was_home"]
                    opponent_id = game["opponent_team"]

                    # We need to lookup difficulty using get_fixture_difficulty
                    # It requires a fixture object with 'team_h' and 'team_a'

                    mock_fixture_for_calc = {
                        "team_h": player["team"] if is_home else opponent_id,
                        "team_a": opponent_id if is_home else player["team"],
                    }

                    teams_processed = self.get_processed_teams()
                    difficulty = self.get_fixture_difficulty(
                        mock_fixture_for_calc, player["team"], teams_processed
                    )

                    mock_fixture = {
                        "event": game["round"],
                        "difficulty": difficulty,
                        "is_home": is_home,
                        "team_h": mock_fixture_for_calc["team_h"],
                        "team_a": mock_fixture_for_calc["team_a"],
                    }
                    mock_upcoming.append(mock_fixture)

                # If player didn't play (no history entry), mock_upcoming is empty -> XP 0.

                xp, _, _ = self.calculate_xp(
                    player, teams_data, mock_upcoming, past_history
                )

                # Multiplier
                multiplier = 1
                if player["id"] == captain_id:
                    multiplier = 2

                gw_total_predicted += xp * multiplier
                gw_total_actual += actual_points * multiplier

            results.append(
                {
                    "gameweek": gw,
                    "predicted": round(gw_total_predicted, 1),
                    "actual": round(gw_total_actual, 0),
                    "diff": round(gw_total_actual - gw_total_predicted, 1),
                }
            )

        return results
