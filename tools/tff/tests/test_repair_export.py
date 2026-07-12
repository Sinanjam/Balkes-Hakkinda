#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from repair_export import (  # noqa: E402
    assign_league_rounds,
    clean_person_name,
    rebuild_players_index,
    repair_detail_people,
)


class PersonNameRepairTests(unittest.TestCase):
    def test_minute_suffixes_are_removed_without_touching_shirt_numbers(self) -> None:
        self.assertEqual(clean_person_name("ALİ VELİ,90+"), "ALİ VELİ")
        self.assertEqual(clean_person_name("ALİ VELİ 45+2"), "ALİ VELİ")
        self.assertEqual(clean_person_name("ALİ VELİ, 12. dk"), "ALİ VELİ")
        self.assertEqual(clean_person_name("Ronaldo 7"), "Ronaldo 7")

    def test_detail_players_are_rebuilt_after_cleaning(self) -> None:
        detail = {
            "lineups": {
                "home": {
                    "team": "Balıkesirspor",
                    "starting11": [{"name": "Ali,90+"}],
                    "substitutes": [],
                    "technicalStaff": [],
                },
                "away": {
                    "team": "Rakip",
                    "starting11": [],
                    "substitutes": [],
                    "technicalStaff": [],
                },
            },
            "events": [],
            "detailCompleteness": {},
        }
        changed = repair_detail_people(detail)
        self.assertEqual(changed, 1)
        self.assertEqual(detail["lineups"]["home"]["starting11"][0]["name"], "Ali")
        self.assertEqual(detail["players"][0]["name"], "Ali")
        self.assertEqual(detail["detailCompleteness"]["players"], 1)


class RoundRepairTests(unittest.TestCase):
    def test_multi_stage_rounds_keep_stage_week_and_global_week(self) -> None:
        details = [
            {"id": "1", "date": "1996-09-01", "matchType": "league"},
            {"id": "2", "date": "1996-09-08", "matchType": "league"},
            {"id": "3", "date": "1997-02-01", "matchType": "league"},
            {"id": "4", "date": "1997-03-01", "matchType": "cup", "standingsWeek": 7},
        ]
        registry_item = {
            "knownFixtures": [
                {"id": "1", "week": 1},
                {"id": "2", "week": 2},
                {"id": "3", "week": 1},
            ],
            "standingsStages": [
                {"id": "kademe", "label": "Kademe", "maxWeek": 2, "expectedMatches": 2},
                {"id": "klasman", "label": "Klasman", "maxWeek": 1, "expectedMatches": 1},
            ],
        }
        report = assign_league_rounds(details, registry_item, [])
        self.assertEqual([item["week"] for item in details[:3]], [1, 2, 3])
        self.assertEqual([item["stageWeek"] for item in details[:3]], [1, 2, 1])
        self.assertEqual([item["stageId"] for item in details[:3]], ["kademe", "kademe", "klasman"])
        self.assertNotIn("standingsWeek", details[3])
        self.assertEqual(details[3]["roundType"], "cup")
        self.assertEqual(report["fallbackWeeks"], 0)


class PlayerIndexCompatibilityTests(unittest.TestCase):
    def test_legacy_and_snake_case_stats_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            season_dir = root / "seasons" / "2020-2021"
            matches_dir = season_dir / "matches"
            matches_dir.mkdir(parents=True)
            (season_dir / "matches_index.json").write_text(
                json.dumps([{"id": "10", "season": "2020-2021"}]),
                encoding="utf-8",
            )
            detail = {
                "id": "10",
                "season": "2020-2021",
                "date": "2020-09-01",
                "lineups": {
                    "home": {
                        "team": "Balıkesirspor",
                        "starting11": [{"name": "Ali", "tffPersonId": "1"}],
                        "substitutes": [{"name": "Veli", "tffPersonId": "2"}],
                    },
                    "away": {"team": "Rakip", "starting11": [], "substitutes": []},
                },
                "substitutions": [{
                    "team": "Balıkesirspor",
                    "playerIn": "Veli",
                    "playerInTffPersonId": "2",
                    "playerOut": "Ali",
                    "playerOutTffPersonId": "1",
                }],
                "goals": [{
                    "team": "Balıkesirspor",
                    "player": "Veli",
                    "tffPersonId": "2",
                    "type": "goal",
                    "goalType": "Penaltı",
                }],
                "cards": [{
                    "team": "Balıkesirspor",
                    "player": "Ali",
                    "tffPersonId": "1",
                    "type": "yellow_card",
                }],
                "events": [],
            }
            (matches_dir / "10.json").write_text(json.dumps(detail), encoding="utf-8")
            players = rebuild_players_index(root)

        by_name = {player["name"]: player for player in players}
        self.assertEqual(by_name["Ali"]["starts"], 1)
        self.assertEqual(by_name["Ali"]["substituted_out"], 1)
        self.assertEqual(by_name["Ali"]["yellow_cards"], 1)
        self.assertEqual(by_name["Veli"]["bench"], 1)
        self.assertEqual(by_name["Veli"]["substituted_in"], 1)
        self.assertEqual(by_name["Veli"]["appearances"], 1)
        self.assertEqual(by_name["Veli"]["goals"], 1)
        self.assertEqual(by_name["Veli"]["penalty_goals"], 1)
        self.assertEqual(by_name["Veli"]["subbedIn"], 1)
        self.assertEqual(by_name["Veli"]["match_ids"], ["10"])


if __name__ == "__main__":
    unittest.main()
