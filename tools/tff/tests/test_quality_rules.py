#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from quality_rules import official_standings_scope, standings_not_yet_expected  # noqa: E402


def match(day: str, *, played: bool = False, match_type: str = "league") -> dict:
    return {
        "matchType": match_type,
        "date": day,
        "score": {"played": played},
    }


class QualityRuleTests(unittest.TestCase):
    def test_all_future_unplayed_league_matches_are_pending(self) -> None:
        details = [match("2026-08-01"), match("2026-08-08")]
        self.assertTrue(
            standings_not_yet_expected(details, today=date(2026, 7, 17))
        )

    def test_played_match_requires_standings(self) -> None:
        details = [match("2026-08-01", played=True)]
        self.assertFalse(
            standings_not_yet_expected(details, today=date(2026, 9, 1))
        )

    def test_past_unplayed_match_is_not_hidden(self) -> None:
        details = [match("2020-08-01")]
        self.assertFalse(
            standings_not_yet_expected(details, today=date(2026, 7, 17))
        )

    def test_cup_fixture_alone_never_creates_pending_standings(self) -> None:
        self.assertFalse(
            standings_not_yet_expected(
                [match("2026-08-01", match_type="cup")],
                today=date(2026, 7, 17),
            )
        )

    def test_missing_match_type_uses_pipeline_league_default(self) -> None:
        details = [{"date": "2026-08-01", "score": {"played": False}}]
        self.assertTrue(
            standings_not_yet_expected(details, today=date(2026, 7, 17))
        )

    def test_official_table_can_exactly_include_playoff_matches(self) -> None:
        details = [
            {
                "matchType": "league",
                "score": {"played": True},
                "balkes": {"result": "W", "goalsFor": 2, "goalsAgainst": 0},
            },
            {
                "matchType": "playoff",
                "score": {"played": True},
                "balkes": {"result": "L", "goalsFor": 1, "goalsAgainst": 3},
            },
        ]
        scope = official_standings_scope(details, {
            "played": 2, "goalsFor": 3, "goalsAgainst": 3,
        })
        self.assertTrue(scope["exact"])
        self.assertEqual(scope["matchTypes"], ["league", "playoff"])

    def test_playoff_scope_does_not_hide_real_goal_difference(self) -> None:
        details = [
            {
                "matchType": "league",
                "score": {"played": True},
                "balkes": {"result": "W", "goalsFor": 2, "goalsAgainst": 0},
            },
            {
                "matchType": "playoff",
                "score": {"played": True},
                "balkes": {"result": "L", "goalsFor": 1, "goalsAgainst": 3},
            },
        ]
        scope = official_standings_scope(details, {
            "played": 2, "goalsFor": 99, "goalsAgainst": 3,
        })
        self.assertFalse(scope["exact"])
        self.assertEqual(scope["matchTypes"], ["league"])


if __name__ == "__main__":
    unittest.main()
