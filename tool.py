import json
import os
import requests
import pandas as pd
import time
from typing import List, Dict, Any, Optional, Tuple

# --- CONFIGURATION ---
NEXT_N_GW = 5
BASE_URL = "https://fantasy.premierleague.com/api/"
CUSTOM_FDR_FILE = "custom_fdr.json"

TEAM_SHORT_NAMES = {
    "Arsenal": "ARS",
    "Aston Villa": "AVL",
    "Bournemouth": "BOU",
    "Brentford": "BRE",
    "Brighton": "BHA",
    "Chelsea": "CHE",
    "Crystal Palace": "CRY",
    "Everton": "EVE",
    "Fulham": "FUL",
    "Ipswich": "IPS",
    "Leicester": "LEI",
    "Liverpool": "LIV",
    "Man City": "MCI",
    "Man Utd": "MNU",
    "Newcastle": "NEW",
    "Nott'm Forest": "NFO",
    "Southampton": "SOU",
    "Spurs": "TOT",
    "West Ham": "WHU",
    "Wolves": "WOL",
}


class FPLManager:
    def __init__(self):
        self.session = requests.Session()
        self.bootstrap_static_cache = None
        self.last_fetch_time = 0
        self.CACHE_DURATION = 300  # 5 minutes
        self.custom_fdr = self.load_custom_fdr()

    def load_custom_fdr(self):
        if os.path.exists(CUSTOM_FDR_FILE):
            try:
                with open(CUSTOM_FDR_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading custom FDR: {e}")
        return {}

    def save_custom_fdr(self, data):
        self.custom_fdr = data
        try:
            with open(CUSTOM_FDR_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving custom FDR: {e}")

    def get_fixture_difficulty(self, fixture, team_id, teams_data):
        """
        Calculates difficulty for team_id in a specific fixture.
        Checks for custom overrides first.
        """
        is_home = fixture["team_h"] == team_id
        opponent_id = fixture["team_a"] if is_home else fixture["team_h"]

        # Default API difficulty
        if "team_h_difficulty" in fixture:
            default_diff = (
                fixture["team_h_difficulty"]
                if is_home
                else fixture["team_a_difficulty"]
            )
        else:
            # Fallback for player summary fixtures
            default_diff = fixture.get("difficulty", 3)

        # Check for Custom Override
        if opponent_id not in teams_data:
            return default_diff

        opponent_name = teams_data[opponent_id]["name"]

        if opponent_name in self.custom_fdr:
            strength_type = "A" if is_home else "H"
            return int(self.custom_fdr[opponent_name].get(strength_type, default_diff))

        return default_diff

    def get_json(self, url):
        """Helper to fetch JSON from API."""
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

        # Process Players
        players = []
        for p in data["elements"]:
            # FILTER: Status 'a' (Available) or 'd' (Doubtful - 75%), Role match, and Budget match
            # We strictly exclude 'i' (Injured) and 's' (Suspended) unless in include_ids

            # Check if this player is in our mandatory include list
            is_mandatory = include_ids and (p["id"] in include_ids)

            # Role check: If role_id is None (ANY), we skip the type check
            is_role_match = (role_id is None) or (p["element_type"] == role_id)

            # Standard filters
            passes_filters = (
                is_role_match
                and (p["now_cost"] / 10 <= max_budget)
                and (p["status"] in ["a", "d"])
                and (p["minutes"] > 200)
            )

            if is_mandatory or passes_filters:
                players.append(
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
                    }
                )

        return teams, pd.DataFrame(players)

    def get_fixtures(self, player_id):
        return self.get_json(BASE_URL + f"element-summary/{player_id}/")["fixtures"]

    def get_all_team_fixtures(self, next_n_gw=None):
        """Fetches upcoming fixtures for all teams for FDR grid."""
        data = self.get_bootstrap_static()
        teams = {t["id"]: t for t in data["teams"]}

        # We need to build a schedule.
        # The bootstrap-static data has 'events' but not a simple "next 5 fixtures for team X" list easily accessible without parsing.
        # However, we can use the 'fixtures' endpoint or parse 'elements' fixtures if we want to avoid 20 calls.
        # BUT, the most reliable way for *teams* is the fixtures endpoint.
        # To avoid 20 API calls, we can fetch ALL fixtures and filter.

        all_fixtures = self.get_json(BASE_URL + "fixtures/")

        # Filter for future
        # Find the first unfinished event to ensure we only show upcoming fixtures
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

            # Use Custom Difficulty
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
                        "short_name": TEAM_SHORT_NAMES.get(
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
                        "short_name": TEAM_SHORT_NAMES.get(
                            teams[h]["name"], teams[h]["name"][:3].upper()
                        ),
                    }
                )

        # Sort by event
        results = []
        for t_id, fixtures in team_schedule.items():
            fixtures.sort(key=lambda x: x["event"])
            # Keep only next N
            if next_n_gw:
                fixtures = fixtures[:next_n_gw]

            # Calculate total difficulty (lower is better)
            total_diff = sum(f["difficulty"] for f in fixtures)

            results.append(
                {
                    "team_name": teams[t_id]["name"],
                    "fixtures": fixtures,
                    "total_difficulty": total_diff,
                }
            )

        return sorted(results, key=lambda x: x["total_difficulty"])

    def _calculate_fixture_multiplier(self, difficulty):
        return 1.0 + ((3 - difficulty) * 0.08)

    def _calculate_matchup_multiplier(self, player, opponent, my_team):
        if player["position"] in [1, 2]:  # GK/DEF
            # We want Opponent Attack (strength_a) to be LOW
            if opponent["strength_a"] < 1050:
                # Opponent attack is weak. Do we have a weak defense?
                if my_team["strength_d"] < 1050:
                    return 1.0  # Weak vs Weak -> Neutral
                else:
                    return 1.1  # Good/Normal Defense vs Weak Attack -> Advantage
            else:
                # Opponent attack is decent/strong. Do we have a strong defense?
                if my_team["strength_d"] > 1250:
                    return 1.0  # Strong Defense holds up -> Neutral
                else:
                    return 0.9  # Normal/Weak Defense vs Strong Attack -> Disadvantage

        else:  # MID/FWD
            # We want Opponent Defense (strength_d) to be LOW
            if opponent["strength_d"] < 1050:
                # Opponent defense is weak. Do we have a weak attack?
                if my_team["strength_a"] < 1050:
                    return 1.0  # Weak vs Weak -> Neutral
                else:
                    return 1.1  # Good/Normal Attack vs Weak Defense -> Advantage
            else:
                # Opponent defense is decent/strong. Do we have a strong attack?
                if my_team["strength_a"] > 1250:
                    return 1.0  # Strong Attack breaks through -> Neutral
                else:
                    return 0.9  # Normal/Weak Attack vs Strong Defense -> Disadvantage

    def calculate_xp(self, player, teams, fixtures):
        total_xp = 0
        gw_points = {}

        base_potential = (player["form"] * 0.4) + (player["points_per_game"] * 0.6)

        upcoming = fixtures[:NEXT_N_GW]

        for f in upcoming:
            is_home = f["is_home"]
            opponent_id = f["team_a"] if is_home else f["team_h"]

            # Safety check for unknown teams
            if opponent_id not in teams:
                continue

            opponent = teams[opponent_id]

            # --- FIXTURE MODIFIERS ---
            # Use Custom Difficulty
            difficulty = self.get_fixture_difficulty(f, player["team"], teams)
            fixture_mult = self._calculate_fixture_multiplier(difficulty)

            # --- MATCHUP MODIFIERS ---
            my_team = teams[player["team"]]
            matchup_mult = self._calculate_matchup_multiplier(player, opponent, my_team)

            # --- HOME ADVANTAGE ---
            venue_mult = 1.1 if is_home else 0.95

            gw_xp = base_potential * fixture_mult * venue_mult * matchup_mult

            # Adjust for availability (e.g. 75% flag)
            chance = player["chance_of_playing"]
            if pd.isna(chance):
                chance = 100
            prob = chance / 100

            final_gw_xp = gw_xp * prob
            total_xp += final_gw_xp

            # Store per-GW points
            gw_event = f.get("event")
            if gw_event:
                gw_points[f"GW{gw_event}"] = round(final_gw_xp, 2)

        return total_xp, gw_points

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

    def optimize_specific_squad(
        self, my_player_ids: List[int]
    ) -> Tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        Optional[Dict[str, Any]],
        Optional[Dict[str, Any]],
        int,
    ]:
        """Optimizes the lineup for a specific list of player IDs."""
        # 1. Get Context
        event_id = self.get_current_event_id()

        # Re-fetching bootstrap to get 'next' event specifically for planning
        static_data = self.get_bootstrap_static()
        next_event = None
        for event in static_data["events"]:
            if event["is_next"]:
                next_event = event["id"]
                break

        if not next_event:
            next_event = event_id + 1

        print(f"Planning for Gameweek {next_event}...")

        # 2. Get All Data
        teams_data, df_all_players = self.fetch_and_filter_data(
            None, 999.0, include_ids=my_player_ids
        )

        # Filter for my players
        my_squad = df_all_players[df_all_players["id"].isin(my_player_ids)].copy()

        # 4. Calculate XP and Captaincy Score for all 15
        squad_xp = []
        for _, player in my_squad.iterrows():
            # Fetch full summary for history (minutes check)
            summary = self.get_json(BASE_URL + f"element-summary/{player['id']}/")
            fixtures = summary["fixtures"]
            history = summary["history"]

            xp, gw_points = self.calculate_xp(player, teams_data, fixtures)

            # Extract just the next GW points for the lineup decision
            next_gw_key = f"GW{next_event}"
            next_gw_xp = gw_points.get(next_gw_key, 0)

            # --- CAPTAINCY SCORE CALCULATION ---
            cap_score = self._calculate_cap_score(player, next_gw_xp, history)

            # --- STATS CALCULATION ---
            stats = self._calculate_advanced_stats(player, history)

            # --- NEXT FIXTURE (For Pitch View) ---
            next_fixture = "?"
            for f in fixtures:
                if f.get("event") == next_event:
                    is_home = f["is_home"]
                    opponent_id = f["team_a"] if is_home else f["team_h"]
                    opponent_name = teams_data[opponent_id]["name"]
                    opponent_short = TEAM_SHORT_NAMES.get(
                        opponent_name, opponent_name[:3].upper()
                    )
                    ha = "(H)" if is_home else "(A)"
                    next_fixture = f"{opponent_short}{ha}"
                    break

            # 5. Upcoming Fixtures Data
            upcoming_fixtures_data = []
            for f in fixtures[:NEXT_N_GW]:
                event = f.get("event")
                if not event:
                    continue

                is_home = f["is_home"]
                opponent_id = f["team_a"] if is_home else f["team_h"]
                if opponent_id not in teams_data:
                    continue

                opponent_name = teams_data[opponent_id]["name"]
                opponent_short = TEAM_SHORT_NAMES.get(
                    opponent_name, opponent_name[:3].upper()
                )
                ha = "(H)" if is_home else "(A)"

                gw_key = f"GW{event}"
                xp_val = gw_points.get(gw_key, 0)

                upcoming_fixtures_data.append(
                    {"event": event, "opponent": f"{opponent_short}{ha}", "xp": xp_val}
                )

            player_data = {
                "id": player["id"],
                "name": player["web_name"],
                "team": teams_data[player["team"]]["name"],
                "position": player["position"],  # 1=GK, 2=DEF, 3=MID, 4=FWD
                "xp": next_gw_xp,
                "total_xp": xp,
                "price": player["now_cost"],
                "cap_score": cap_score,
                "next_fixture": next_fixture,
                "form": player["form"],
                "selected_by_percent": player["selected_by_percent"],
                "upcoming_fixtures": upcoming_fixtures_data,
            }
            player_data.update(stats)
            squad_xp.append(player_data)

        # 5. Optimize Lineup
        starters, bench, captain, vice_captain = self._optimize_lineup(squad_xp)

        return starters, bench, captain, vice_captain, next_event

    def optimize_team(self, team_id):
        print(f"Optimizing team {team_id}...")

        # 1. Get Context
        event_id = self.get_current_event_id()

        # 2. Get My Team
        picks_data = self.get_team_picks(team_id, event_id)
        if not picks_data:
            raise Exception("Could not fetch team data.")

        my_player_ids = [p["element"] for p in picks_data["picks"]]

        return self.optimize_specific_squad(my_player_ids)

    def get_captaincy_candidates(self, team_id):
        """Returns detailed stats for top 5 captaincy options."""
        # Reuse optimization logic to get XP and Cap Scores
        starters, bench, _, _, next_event = self.optimize_team(team_id)

        all_players = starters + bench
        # Sort by Cap Score
        all_players.sort(key=lambda x: x["cap_score"], reverse=True)

        top_candidates = all_players[:5]

        return top_candidates, next_event

    def search_player(self, query):
        data = self.get_bootstrap_static()
        results = []
        query = query.lower()

        teams = {t["id"]: t["name"] for t in data["teams"]}

        for p in data["elements"]:
            if (
                query in p["web_name"].lower()
                or query in p["first_name"].lower()
                or query in p["second_name"].lower()
            ):
                # Return full player object plus team name for display
                p_full = p.copy()
                p_full["team_name"] = teams[p["team"]]
                # Normalize cost
                p_full["now_cost"] = p["now_cost"] / 10
                results.append(p_full)

                if len(results) >= 20:
                    break

        return results


def get_user_requirements():
    """
    Interactive prompts to filter players by Role and Budget.
    """
    print("\n--- FPL TRANSFER RECOMMENDER ---")

    # 1. Select Role
    role_map = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
    while True:
        role_input = (
            input("Which role do you need? (GK / DEF / MID / FWD): ").upper().strip()
        )
        if role_input in role_map:
            selected_role_id = role_map[role_input]
            break
        print("Invalid selection. Please type GK, DEF, MID, or FWD.")

    # 2. Select Budget
    while True:
        try:
            budget_input = input(
                f"What is your max budget for this {role_input}? (e.g., 6.0): "
            )
            max_budget = float(budget_input)
            break
        except ValueError:
            print("Please enter a valid number (e.g., 5.5).")

    return selected_role_id, max_budget, role_input


def main():
    manager = FPLManager()

    # 1. Get User Input
    role_id, max_budget, role_name = get_user_requirements()

    # 2. Get Data
    teams, df_players = manager.fetch_and_filter_data(role_id, max_budget)

    if df_players.empty:
        print(f"No players found for {role_name} under £{max_budget}m.")
        return

    # 3. Sort by Form to limit API calls (Analyze top 20 candidates)
    candidates = df_players.sort_values(by="form", ascending=False).head(30)

    results = []
    print(f"\nAnalyzing top 20 {role_name} candidates under £{max_budget}m...")
    print("(This may take 10-15 seconds)...")

    for _, player in candidates.iterrows():
        try:
            time.sleep(0.05)  # Be polite to API
            fixtures = manager.get_fixtures(player["id"])
            xp, gw_points = manager.calculate_xp(player, teams, fixtures)

            row = {
                "Name": player["web_name"],
                "Team": teams[player["team"]]["name"],
                "Price": f"£{player['now_cost']}m",
                "Form": player["form"],
                "Predicted_Pts": round(xp, 2),
            }
            # Add per-GW columns
            row.update(gw_points)
            results.append(row)
        except Exception as e:
            print(f"Error processing player {player['web_name']}: {e}")
            continue

    # 4. Show Results
    final_df = (
        pd.DataFrame(results).sort_values(by="Predicted_Pts", ascending=False).head(10)
    )

    print(f"\n--- TOP 10 REPLACEMENTS FOR GABRIEL ({role_name}) ---")
    # Clean table output
    # Fill NaN with - for missing gameweeks if any
    print(final_df.fillna("-").to_string(index=False))

    # Recommendation logic
    if not final_df.empty:
        top_pick = final_df.iloc[0]
        print(
            f"\n💡 ALGORITHM RECOMMENDATION: Transfer in **{top_pick['Name']}** ({top_pick['Team']})"
        )


if __name__ == "__main__":
    main()
