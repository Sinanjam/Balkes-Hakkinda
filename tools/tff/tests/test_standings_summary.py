#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from tff_standings_builder import update_manifest, update_season_files  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def row(played: int, gf: int, ga: int, won: int, drawn: int, lost: int) -> dict:
    points = won * 3 + drawn
    return {
        "team": "Balıkesirspor",
        "isBalkes": True,
        "rank": 5,
        "played": played,
        "won": won,
        "drawn": drawn,
        "lost": lost,
        "goalsFor": gf,
        "goalsAgainst": ga,
        "goalDifference": gf - ga,
        "points": points,
        "rawPoints": points,
        "pointsDeducted": 0,
    }


class StandingsSummaryTests(unittest.TestCase):
    def test_postseason_table_preserves_league_only_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            season = root / "seasons" / "2025-2026"
            write_json(root / "manifest.json", {
                "availableSeasons": [{"id": "2025-2026", "summary": {}}],
            })
            write_json(season / "season.json", {
                "id": "2025-2026",
                "summary": {"matches": 2},
            })
            write_json(season / "matches_index.json", [
                {
                    "id": "1",
                    "matchType": "league",
                    "score": {"played": True},
                    "balkes": {"result": "W", "goalsFor": 2, "goalsAgainst": 0},
                },
                {
                    "id": "2",
                    "matchType": "playoff",
                    "score": {"played": True},
                    "balkes": {"result": "L", "goalsFor": 1, "goalsAgainst": 3},
                },
            ])
            snapshots = [
                {"week": 1, "standings": [row(1, 2, 0, 1, 0, 0)]},
                {"week": 2, "standings": [row(2, 3, 3, 1, 0, 1)]},
            ]
            update_season_files(root, "2025-2026", snapshots)
            update_manifest(root, ["2025-2026"])
            season_json = json.loads((season / "season.json").read_text(encoding="utf-8"))
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(season_json["leagueSummary"]["played"], 1)
        self.assertEqual(season_json["leagueSummary"]["goalsFor"], 2)
        self.assertEqual(season_json["officialStandingsSummary"]["played"], 2)
        self.assertEqual(
            season_json["officialStandingsMatchTypes"],
            ["league", "playoff"],
        )
        self.assertEqual(
            manifest["availableSeasons"][0]["officialStandingsMatchTypes"],
            ["league", "playoff"],
        )


if __name__ == "__main__":
    unittest.main()
