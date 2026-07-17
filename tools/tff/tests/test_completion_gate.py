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
SCRIPT = TOOLS / "completion_gate.py"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class CompletionGateTests(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        season = root / "seasons" / "2025-2026"
        write_json(root / "manifest.json", {
            "availableSeasons": [{"id": "2025-2026", "matchCount": 1}],
        })
        write_json(root / "reports" / "validation.json", {
            "status": "ok", "summary": {"errors": 0},
        })
        write_json(root / "reports" / "repair_validation.json", {"status": "ok"})
        write_json(root / "reports" / "club_fixture_discovery.json", {
            "seasonsRequested": 1,
            "seasonsSucceeded": 1,
            "paginationFailures": [],
        })
        write_json(season / "matches_index.json", [{"id": "1"}])
        write_json(season / "matches" / "1.json", {
            "id": "1",
            "season": "2025-2026",
            "date": "2025-09-01",
            "homeTeam": "Balıkesirspor",
            "awayTeam": "Rakip",
            "competition": "3. Lig",
            "matchType": "league",
            "week": 1,
            "standingsWeek": 1,
            "score": {"played": True, "home": 1, "away": 0},
            "source": {"url": "https://www.tff.org/mac/1"},
            "quality": "A",
            "lineups": {
                "home": {"starting11": [{"name": str(i)} for i in range(11)]},
                "away": {"starting11": [{"name": str(i)} for i in range(11)]},
            },
            "events": [{"type": "goal"}],
            "officials": [{"role": "Hakem", "name": "Hakem"}],
        })
        write_json(season / "standings_by_week.json", [{
            "week": 1,
            "standings": [{"team": "Balıkesirspor"}, {"team": "Rakip"}],
        }])

    def run_gate(self, root: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
        report = root / "reports" / "completion.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--data-root", str(root), "--report", str(report)],
            text=True,
            capture_output=True,
            check=False,
        )
        return result, json.loads(report.read_text(encoding="utf-8"))

    def test_clean_complete_tree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            result, report = self.run_gate(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report["status"], "clean")
        self.assertTrue(report["readyToPublish"])
        self.assertEqual(report["summary"]["coreComplete"], 1)

    def test_missing_detail_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "seasons" / "2025-2026" / "matches" / "1.json").unlink()
            result, report = self.run_gate(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["status"], "error")
        self.assertFalse(report["readyToPublish"])
        self.assertTrue(any("maç detayı eksik" in value for value in report["errors"]))

    def test_source_limited_detail_is_reported_without_inventing_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            detail_path = root / "seasons" / "2025-2026" / "matches" / "1.json"
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            detail["lineups"] = {}
            detail["events"] = []
            detail["quality"] = "B"
            write_json(detail_path, detail)
            result, report = self.run_gate(root)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["status"], "clean_with_source_limits")
        self.assertEqual(report["summary"]["sourceLimitedMatches"], 1)

    def test_future_unplayed_season_does_not_require_standings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            detail_path = root / "seasons" / "2025-2026" / "matches" / "1.json"
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            detail["date"] = (date.today() + timedelta(days=30)).isoformat()
            detail["score"] = {"played": False, "home": None, "away": None}
            detail["lineups"] = {}
            detail["events"] = []
            write_json(detail_path, detail)
            write_json(root / "seasons" / "2025-2026" / "standings_by_week.json", [])
            result, report = self.run_gate(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(report["readyToPublish"])
        self.assertEqual(report["status"], "clean_with_warnings")
        self.assertEqual(report["summary"]["leaguePlayedMatches"], 0)
        self.assertEqual(report["summary"]["pendingStandingsSeasons"], 1)
        self.assertEqual(report["pendingStandings"][0]["leagueMatches"], 1)

    def test_historical_unplayed_season_still_requires_standings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            detail_path = root / "seasons" / "2025-2026" / "matches" / "1.json"
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            detail["date"] = "2020-09-01"
            detail["score"] = {"played": False, "home": None, "away": None}
            write_json(detail_path, detail)
            write_json(root / "seasons" / "2025-2026" / "standings_by_week.json", [])
            result, report = self.run_gate(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any("geçerli haftalık puan tablosu yok" in value for value in report["errors"]))

    def test_validation_errors_are_forwarded_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            write_json(root / "reports" / "validation.json", {
                "status": "error",
                "summary": {"errors": 1},
                "errors": ["Keşif 2026-2027: örnek gerçek hata"],
            })
            result, report = self.run_gate(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Keşif 2026-2027: örnek gerçek hata", report["errors"])
        self.assertNotIn("Sıkı genel doğrulama hata verdi.", report["errors"])


if __name__ == "__main__":
    unittest.main()
