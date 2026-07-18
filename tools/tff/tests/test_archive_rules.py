#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from archive_rules import reconciled_stage_max_week, select_reconciled_stage_set  # noqa: E402


class ArchiveRuleTests(unittest.TestCase):
    def test_direct_group_uses_numbered_fixture_week_over_odd_team_guess(self) -> None:
        stage = {"label": "03", "teamCount": 15}
        self.assertEqual(reconciled_stage_max_week(stage, 30, 30), 30)

    def test_playoff_total_does_not_shrink_direct_group_fixture_week(self) -> None:
        stage = {"label": "04", "teamCount": 16}
        self.assertEqual(reconciled_stage_max_week(stage, 32, 30), 32)

    def test_direct_numbered_group_beats_unrelated_stage_combination(self) -> None:
        direct = [{"label": "03", "expectedMatches": 30, "maxWeek": 30}]
        wrong_combo = [
            {"label": "Kademe", "expectedMatches": 20, "maxWeek": 20},
            {"label": "Klasman", "expectedMatches": 10, "maxWeek": 12},
        ]
        self.assertEqual(select_reconciled_stage_set([wrong_combo, direct]), direct)

    def test_real_kademe_klasman_keeps_more_chronology(self) -> None:
        cumulative_only = [
            {"label": "Klasman K2", "expectedMatches": 32, "maxWeek": 32},
        ]
        real_stages = [
            {"label": "Kademe 02", "expectedMatches": 18, "maxWeek": 18},
            {"label": "Klasman K2", "expectedMatches": 14, "maxWeek": 14},
        ]
        self.assertEqual(
            select_reconciled_stage_set([cumulative_only, real_stages]),
            real_stages,
        )


if __name__ == "__main__":
    unittest.main()
