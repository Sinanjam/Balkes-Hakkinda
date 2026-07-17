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


if __name__ == "__main__":
    unittest.main()
