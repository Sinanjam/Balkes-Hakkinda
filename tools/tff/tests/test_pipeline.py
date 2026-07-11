#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from discover_club_fixtures import archive_stage_sort_key, fixture_page_actions  # noqa: E402
from tff_factory import (  # noqa: E402
    extract_balkes_ids,
    professional_competition_status,
    remove_superseded_unplayed,
)
from tff_standings_builder import build_item_urls, try_official_stages  # noqa: E402


class FixtureDiscoveryTests(unittest.TestCase):
    def test_row_scoped_match_id_does_not_leak_from_neighbour(self) -> None:
        raw = """
        <table>
          <tr><td>BAŞKA TAKIM - DİĞER TAKIM</td><td><a href='?pageID=29&macId=100'>Detay</a></td></tr>
          <tr><td>BALIKESİRSPOR - RAKİP</td><td><a href='?pageID=29&macId=200'>Detay</a></td></tr>
        </table>
        """
        self.assertEqual(extract_balkes_ids(raw), ["200"])

    def test_numeric_linkbutton_postback_is_preferred(self) -> None:
        raw = """
        <table id='ctl00_MPane_m_28_398_ctnr_m_28_398_grdFikstur'>
          <tr><td class='pager'><a href="javascript:__doPostBack('ctl00$grid$ctl00$ctl03$ctl01$ctl02','')">2</a></td></tr>
        </table>
        """
        actions = fixture_page_actions(raw, 2)
        self.assertEqual(actions[0]["target"], "ctl00$grid$ctl00$ctl03$ctl01$ctl02")
        self.assertEqual(actions[0]["argument"], "")
        self.assertEqual(actions[0]["source"], "html_postback")

    def test_archive_stage_order_starts_with_numeric_group(self) -> None:
        stages = [{"label": "K2"}, {"label": "02"}]
        self.assertEqual(
            [item["label"] for item in sorted(stages, key=archive_stage_sort_key)],
            ["02", "K2"],
        )


class ProfessionalFilterTests(unittest.TestCase):
    def test_professional_team_is_accepted(self) -> None:
        self.assertEqual(
            professional_competition_status("Spor Toto 1. Lig (Profesyonel Takım)"),
            (True, "explicit_professional"),
        )

    def test_academy_and_paf_are_rejected(self) -> None:
        self.assertFalse(professional_competition_status("Elit U17 Ligi (Akademi U17 Takımı)")[0])
        self.assertFalse(professional_competition_status("U21 Ligi (PAF Takımı)")[0])

    def test_superseded_unplayed_league_fixture_is_removed(self) -> None:
        unplayed = {
            "id": "1", "date": "2018-09-17", "homeTeam": "Balıkesirspor",
            "awayTeam": "Ümraniyespor", "matchType": "league", "score": {"played": False},
        }
        played = {
            "id": "2", "date": "2018-11-28", "homeTeam": "Balıkesirspor",
            "awayTeam": "Ümraniyespor", "matchType": "league", "score": {"played": True},
        }
        kept, dropped = remove_superseded_unplayed([unplayed, played])
        self.assertEqual([item["id"] for item in kept], ["2"])
        self.assertEqual(dropped[0]["reason"], "superseded_unplayed_league_fixture")


class StandingsTests(unittest.TestCase):
    def test_duplicate_exact_target_url_is_fetched_once(self) -> None:
        item = {
            "targetPageID": "805",
            "targetGrupID": "210",
            "targetUrls": ["https://www.tff.org/Default.aspx?pageID=805&grupID=210"],
        }
        self.assertEqual(len(build_item_urls(item, 1)), 1)

    @patch("tff_standings_builder.try_official_weekly")
    def test_multi_stage_weeks_are_flattened_without_losing_stage_week(self, mocked) -> None:
        def snapshots(_item, _season, _root, _sleep, _force, max_week, _workers):
            return [
                {"week": week, "standings": [{"team": "Balıkesirspor", "isBalkes": True}]}
                for week in range(1, max_week + 1)
            ]

        mocked.side_effect = snapshots
        item = {
            "standingsStages": [
                {"id": "kademe", "label": "Kademe", "targetPageID": "805", "targetGrupID": "210", "maxWeek": 2},
                {"id": "klasman", "label": "Klasman", "targetPageID": "805", "targetGrupID": "216", "maxWeek": 1},
            ]
        }
        combined, reports = try_official_stages(item, "1996-1997", Path("/tmp/test"), 0, False, 2)
        self.assertEqual([item["week"] for item in combined], [1, 2, 3])
        self.assertEqual([item["stageWeek"] for item in combined], [1, 2, 1])
        self.assertEqual([item["stageId"] for item in combined], ["kademe", "kademe", "klasman"])
        self.assertEqual([item["weeksGenerated"] for item in reports], [2, 1])


if __name__ == "__main__":
    unittest.main()
