#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
SCRIPT = TOOLS / "validate_export.py"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class FutureSeasonValidationTests(unittest.TestCase):
    def test_strict_validation_accepts_not_started_league(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            season = root / "seasons" / "2026-2027"
            report = root / "reports" / "validation.json"
            registry = root / "registry.json"
            discovery = root / "reports" / "club_fixture_discovery.json"

            write_json(root / "manifest.json", {
                "availableSeasons": [{"id": "2026-2027", "matchCount": 1}],
            })
            write_json(registry, {"runOrder": [], "seasons": []})
            write_json(discovery, {
                "seasonsRequested": 1,
                "seasonsSucceeded": 1,
                "seasonsWithMatches": 1,
                "errors": [],
                "paginationFailures": [],
                "standingsTargets": [],
            })
            write_json(season / "matches_index.json", [{"id": "future-1"}])
            write_json(season / "matches" / "future-1.json", {
                "id": "future-1",
                "season": "2026-2027",
                "date": (date.today() + timedelta(days=30)).isoformat(),
                "homeTeam": "Balıkesirspor",
                "awayTeam": "Rakip",
                "competition": "TFF 3. Lig",
                "matchType": "league",
                "week": 1,
                "standingsWeek": 1,
                "score": {"played": False, "home": None, "away": None},
                "quality": "B",
            })
            write_json(season / "season.json", {"summary": {"matches": 1}})
            write_json(season / "standings_by_week.json", [])

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--data-root",
                    str(root),
                    "--report",
                    str(report),
                    "--registry",
                    str(registry),
                    "--discovery-report",
                    str(discovery),
                    "--strict",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            payload = json.loads(report.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["summary"]["errors"], 0)
        self.assertTrue(payload["seasons"][0]["standingsPending"])
        self.assertTrue(
            any("puan tablosu bu aşamada beklenmiyor" in value for value in payload["warnings"])
        )

    def test_strict_validation_accepts_official_table_with_playoffs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            season = root / "seasons" / "2025-2026"
            report = root / "reports" / "validation.json"
            registry = root / "registry.json"
            discovery = root / "reports" / "club_fixture_discovery.json"

            write_json(root / "manifest.json", {
                "availableSeasons": [{"id": "2025-2026", "matchCount": 2}],
            })
            write_json(registry, {"runOrder": [], "seasons": []})
            write_json(discovery, {
                "seasonsRequested": 1,
                "seasonsSucceeded": 1,
                "seasonsWithMatches": 1,
                "errors": [],
                "paginationFailures": [],
                "standingsTargets": [],
            })
            details = [
                {
                    "id": "league-1",
                    "season": "2025-2026",
                    "date": "2025-09-01",
                    "homeTeam": "Balıkesirspor",
                    "awayTeam": "Lig Rakibi",
                    "competition": "TFF 3. Lig",
                    "matchType": "league",
                    "score": {"played": True, "home": 2, "away": 0},
                    "balkes": {"result": "W", "goalsFor": 2, "goalsAgainst": 0},
                    "quality": "A",
                },
                {
                    "id": "playoff-1",
                    "season": "2025-2026",
                    "date": "2026-04-01",
                    "homeTeam": "Play-off Rakibi",
                    "awayTeam": "Balıkesirspor",
                    "competition": "TFF 3. Lig Play Off",
                    "matchType": "playoff",
                    "score": {"played": True, "home": 3, "away": 1},
                    "balkes": {"result": "L", "goalsFor": 1, "goalsAgainst": 3},
                    "quality": "A",
                },
            ]
            write_json(season / "matches_index.json", [{"id": value["id"]} for value in details])
            for detail in details:
                write_json(season / "matches" / f"{detail['id']}.json", detail)
            write_json(season / "season.json", {"summary": {"matches": 2}})
            other_rows = [
                {"team": "Rakip A"},
                {"team": "Rakip B"},
                {"team": "Rakip C"},
            ]
            write_json(season / "standings_by_week.json", [
                {
                    "week": 1,
                    "standings": [
                        {"team": "Balıkesirspor", "played": 1, "goalsFor": 2, "goalsAgainst": 0},
                        *other_rows,
                    ],
                },
                {
                    "week": 2,
                    "standings": [
                        {"team": "Balıkesirspor", "played": 2, "goalsFor": 3, "goalsAgainst": 3},
                        *other_rows,
                    ],
                },
            ])

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--data-root",
                    str(root),
                    "--report",
                    str(report),
                    "--registry",
                    str(registry),
                    "--discovery-report",
                    str(discovery),
                    "--strict",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            payload = json.loads(report.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["summary"]["errors"], 0)
        self.assertEqual(
            payload["seasons"][0]["officialStandingsMatchTypes"],
            ["league", "playoff"],
        )


if __name__ == "__main__":
    unittest.main()
