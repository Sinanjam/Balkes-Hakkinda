#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from quality_rules import standings_not_yet_expected  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
