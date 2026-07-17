#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from archive_rules import select_reconciled_stage_set  # noqa: E402


class ArchiveRuleTests(unittest.TestCase):
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
