#!/usr/bin/env python3
from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from discover_club_fixtures import (  # noqa: E402
    archive_group_is_selected,
    archive_stage_sort_key,
    fixture_page_actions,
    extract_fixture_result,
    expected_standings_matches_from_item,
    max_numbered_league_fixture_week,
    page_mentions_season,
    reconcile_archive_stages,
    seed_with_preserved_unselected_runtime,
    standalone_archive_stages,
)
from tff_factory import (  # noqa: E402
    extract_balkes_ids,
    match_override_for,
    professional_competition_status,
    remove_superseded_unplayed,
)
from tff_standings_builder import (  # noqa: E402
    build_item_urls,
    parse_official_standings,
    try_official_stages,
    try_official_weekly,
    update_season_files,
)
from validate_export import intentionally_skipped, validate_discovery  # noqa: E402


class FixtureDiscoveryTests(unittest.TestCase):
    def test_repair_seasons_pin_permanent_archive_targets(self) -> None:
        registry = json.loads((TOOLS / "balkes_tff_seed_registry.json").read_text(encoding="utf-8"))
        by_season = {item["season"]: item for item in registry["seasons"]}
        self.assertEqual(
            (by_season["2025-2026"]["targetPageID"], by_season["2025-2026"]["targetGrupID"]),
            ("1770", "2786"),
        )
        self.assertEqual(
            (by_season["2006-2007"]["targetPageID"], by_season["2006-2007"]["targetGrupID"]),
            ("575", "15"),
        )

    def test_leading_fixture_column_is_parsed_as_week(self) -> None:
        raw = """
        <table id='ctl00_MPane_m_28_398_ctnr_m_28_398_grdFikstur'>
          <tr><td>17</td><td>BALIKESİRSPOR 2-0 RAKİP</td>
              <td><a href='?pageID=29&amp;macId=123'>Detay</a></td></tr>
        </table>
        """
        result = extract_fixture_result(raw, "2006-2007", "http://www.tff.org/Default.aspx?pageID=28")
        self.assertEqual(result["fixtures"][0]["week"], 17)

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

    def test_standings_target_must_mention_requested_season(self) -> None:
        raw = "<html><title>2025-2026 Sezonu</title><body>Balıkesirspor</body></html>"
        self.assertTrue(page_mentions_season(raw, "2025-2026"))
        self.assertFalse(page_mentions_season(raw, "2009-2010"))

    def test_archive_group_selection_marker_is_checked(self) -> None:
        raw = """
        <a href='Default.aspx?pageID=806&grupID=229' style='background:#a10102'>02</a>
        <a href='Default.aspx?pageID=806&grupID=233'>F</a>
        """
        self.assertTrue(archive_group_is_selected(raw, "229"))
        self.assertFalse(archive_group_is_selected(raw, "233"))
        self.assertFalse(archive_group_is_selected(raw, "999"))

    def test_standings_count_keeps_playoff_as_secondary_scope(self) -> None:
        item = {
            "knownFixtures": [
                {"id": "1", "week": 1, "rowText": "1 BALIKESİRSPOR 1-0 RAKİP TFF 3. Lig 04"},
                {"id": "2", "week": 30, "rowText": "30 RAKİP 0-1 BALIKESİRSPOR TFF 3. Lig 04"},
                {"id": "3", "week": 0, "rowText": "BALIKESİRSPOR 2-1 RAKİP 3. Lig Play Off Müsabakaları"},
                {"id": "4", "week": 0, "rowText": "BALIKESİRSPOR 1-2 RAKİP Ziraat Türkiye Kupası"},
            ]
        }
        self.assertEqual(
            expected_standings_matches_from_item(item),
            {"league": 2, "playoff": 1, "standings": 3},
        )
        self.assertEqual(max_numbered_league_fixture_week(item), 30)

    def test_targeted_discovery_preserves_unselected_runtime_seasons(self) -> None:
        seed = {
            "policy": "fresh-policy",
            "runOrder": ["2025-2026", "2010-2011"],
            "seasons": [
                {
                    "season": "2025-2026",
                    "targetPageID": "1770",
                    "targetGrupID": "2786",
                    "knownFixtures": [],
                },
                {"season": "2010-2011", "knownFixtures": []},
            ],
        }
        existing = {
            "policy": "old-policy",
            "runtimeOnly": True,
            "runOrder": ["2010-2011", "2025-2026", "2009-2010"],
            "seasons": [
                {
                    "season": "2025-2026",
                    "targetPageID": "971",
                    "knownFixtures": [{"id": "kept-selected"}],
                    "standingsStages": [{"id": "stale-current-page-stage"}],
                },
                {
                    "season": "2010-2011",
                    "knownFixtures": [{"id": "kept"}],
                    "standingsStages": [{"id": "kept-stage"}],
                },
                {"season": "2009-2010", "knownFixtures": [{"id": "also-kept"}]},
            ],
        }

        merged = seed_with_preserved_unselected_runtime(seed, existing, ["2025-2026"])
        by_season = {item["season"]: item for item in merged["seasons"]}

        self.assertEqual(merged["policy"], "fresh-policy")
        self.assertTrue(merged["runtimeOnly"])
        self.assertEqual(by_season["2025-2026"]["targetPageID"], "1770")
        self.assertEqual(by_season["2025-2026"]["knownFixtures"], [{"id": "kept-selected"}])
        self.assertNotIn("standingsStages", by_season["2025-2026"])
        self.assertEqual(by_season["2010-2011"]["knownFixtures"], [{"id": "kept"}])
        self.assertEqual(by_season["2010-2011"]["standingsStages"], [{"id": "kept-stage"}])
        self.assertEqual(by_season["2009-2010"]["knownFixtures"], [{"id": "also-kept"}])
        self.assertEqual(merged["runOrder"], ["2025-2026", "2010-2011", "2009-2010"])


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

    def test_verified_match_override_is_scoped_to_season_and_id(self) -> None:
        seed = {"seasons": [{"season": "1995-1996", "matchOverrides": {
            "47516": {"matchType": "playoff"}
        }}]}
        self.assertEqual(match_override_for(seed, "1995-1996", "47516")["matchType"], "playoff")
        self.assertEqual(match_override_for(seed, "1996-1997", "47516"), {})


class StandingsTests(unittest.TestCase):
    @staticmethod
    def standings_table(team_prefix: str, include_balkes: bool) -> str:
        teams = [f"{team_prefix}{index}" for index in range(1, 9)]
        if include_balkes:
            teams[3] = "Balıkesirspor"
        rows = "".join(
            f"<tr><td>{index}.{team}</td><td>1</td><td>1</td><td>0</td><td>0</td>"
            f"<td>2</td><td>0</td><td>2</td><td>3</td></tr>"
            for index, team in enumerate(teams, 1)
        )
        return "<table><tr><th>Takım</th><th>O</th><th>G</th><th>B</th><th>M</th>" \
               "<th>A</th><th>Y</th><th>AV</th><th>P</th></tr>" + rows + "</table>"

    def test_group_scoped_parser_does_not_leak_from_other_module(self) -> None:
        raw = (
            "<div id='first_ctnr_div'><a href='?grupID=233'>F</a>"
            + self.standings_table("Final", True)
            + "</div><div id='second_ctnr_div'><a href='?grupID=229'>02</a>"
            + self.standings_table("Kademe", False)
            + "</div>"
        )
        global_rows = parse_official_standings(raw)
        scoped_rows = parse_official_standings(raw, "229")
        self.assertTrue(any(row.get("isBalkes") for row in global_rows))
        self.assertFalse(any(row.get("isBalkes") for row in scoped_rows))
        self.assertEqual(parse_official_standings(raw, module_id="missing"), [])

    def test_same_display_name_with_distinct_tff_ids_is_not_deduplicated(self) -> None:
        teams = ["Göztepe A.Ş.", "Göztepe A.Ş."] + [f"Takım {value}" for value in range(3, 9)]
        rows = "".join(
            "<tr><td>{rank}.</td><td><a href='?pageID=28&kulupID={team_id}'>{team}</a></td>"
            "<td>1</td><td>1</td><td>0</td><td>0</td><td>2</td><td>0</td><td>2</td><td>3</td></tr>".format(
                rank=index,
                team_id=100 + index,
                team=team,
            )
            for index, team in enumerate(teams, 1)
        )
        raw = (
            "<table><tr><th>Sıra</th><th>Takım</th><th>O</th><th>G</th><th>B</th><th>M</th>"
            "<th>A</th><th>Y</th><th>AV</th><th>P</th></tr>" + rows + "</table>"
        )
        parsed = parse_official_standings(raw)
        self.assertEqual(len(parsed), 8)
        self.assertEqual([row["teamId"] for row in parsed[:2]], ["101", "102"])

    def test_group_less_promotion_module_becomes_a_separate_stage(self) -> None:
        module_id = "ctl00_MPane_m_980_5402_ctnr_div"
        raw = (
            f"<div id='{module_id}'><div class='moduleTitle'>Yükselme Grubu</div>"
            "<a href='?pageID=980&hafta=1'>1</a><a href='?pageID=980&hafta=18'>18</a>"
            + self.standings_table("Final", True)
            + "</div><div id='ctl00_MPane_m_980_6193_ctnr_div'>"
            "<div class='moduleTitle'>Kademe Grupları</div><a href='?grupID=605'>01</a>"
            + self.standings_table("Kademe", True)
            + "</div>"
        )
        stages = standalone_archive_stages(raw, "980", "http://www.tff.org/Default.aspx?pageID=980")
        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0]["targetModuleID"], module_id)
        self.assertEqual(stages[0]["maxWeek"], 18)

    def test_cumulative_klasman_table_is_converted_to_incremental_stage(self) -> None:
        stages = [
            {"id": "kademe", "label": "02", "expectedMatches": 18, "teamCount": 10},
            {"id": "klasman", "label": "K2", "expectedMatches": 32, "teamCount": 8},
            {"id": "wrong", "label": "Yükselme Grubu", "expectedMatches": 18, "teamCount": 10},
        ]
        selected = reconcile_archive_stages(stages, 32)
        self.assertEqual([stage["id"] for stage in selected], ["kademe", "klasman"])
        self.assertEqual(selected[1]["expectedMatches"], 14)
        self.assertEqual(selected[1]["carriedMatches"], 18)
        self.assertEqual(selected[1]["maxWeek"], 14)

    def test_direct_archive_group_uses_fixture_week_instead_of_odd_row_count(self) -> None:
        selected = reconcile_archive_stages(
            [{"id": "group-03", "label": "03", "expectedMatches": 30, "teamCount": 15}],
            30,
            30,
            30,
        )
        self.assertEqual(selected[0]["maxWeek"], 30)
        self.assertEqual(selected[0]["officialMatchTypes"], ["league"])

    def test_archive_group_can_be_proven_as_league_plus_playoff(self) -> None:
        selected = reconcile_archive_stages(
            [{"id": "group-04", "label": "04", "expectedMatches": 32, "teamCount": 16}],
            30,
            32,
            30,
        )
        self.assertEqual(selected[0]["expectedMatches"], 32)
        self.assertEqual(selected[0]["officialMatchTypes"], ["league", "playoff"])

    def test_duplicate_exact_target_url_is_fetched_once(self) -> None:
        item = {
            "targetPageID": "805",
            "targetGrupID": "210",
            "targetUrls": ["https://www.tff.org/Default.aspx?pageID=805&grupID=210"],
        }
        self.assertEqual(len(build_item_urls(item, 1)), 1)

    @patch("tff_standings_builder.fetch_official_week")
    def test_partial_parallel_result_gets_one_serial_fresh_recovery(self, mocked) -> None:
        calls: list[tuple[int, bool]] = []

        def fetch(_item, _season, _root, _sleep, force, week):
            calls.append((week, force))
            if week == 2 and not force:
                return week, None
            return week, {
                "week": week,
                "standings": [{
                    "team": "Balıkesirspor",
                    "isBalkes": True,
                    "played": week,
                    "points": week,
                    "goalDifference": week,
                }],
                "warnings": [],
            }

        mocked.side_effect = fetch
        snapshots = try_official_weekly(
            {"targetPageID": "575", "targetGrupID": "15"},
            "2006-2007",
            Path("/tmp/test"),
            0,
            False,
            3,
            workers=1,
        )
        self.assertEqual([snapshot["week"] for snapshot in snapshots], [1, 2, 3])
        self.assertIn((2, True), calls)

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

    def test_season_summary_handles_cumulative_second_stage(self) -> None:
        def row(played: int, won: int, drawn: int, lost: int, gf: int, ga: int, points: int) -> dict:
            return {
                "team": "Balıkesirspor", "isBalkes": True, "rank": 1,
                "played": played, "won": won, "drawn": drawn, "lost": lost,
                "goalsFor": gf, "goalsAgainst": ga, "goalDifference": gf - ga,
                "points": points, "rawPoints": points, "pointsDeducted": 0,
            }

        snapshots = [
            {"week": 18, "stageId": "kademe", "stageLabel": "Kademe", "stageNumber": 1,
             "stageCarriedMatches": 0, "standings": [row(18, 7, 2, 9, 27, 34, 23)]},
            {"week": 32, "stageId": "klasman", "stageLabel": "Klasman", "stageNumber": 2,
             "stageCarriedMatches": 18, "standings": [row(32, 14, 5, 13, 44, 46, 47)]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            update_season_files(root, "2008-2009", snapshots)
            season = json.loads((root / "seasons/2008-2009/season.json").read_text())
        self.assertEqual(season["leagueSummary"]["played"], 32)
        self.assertEqual(season["leagueStages"][1]["played"], 14)
        self.assertTrue(season["leagueStages"][1]["officialTableIsCumulative"])


class ValidationTests(unittest.TestCase):
    def test_legacy_skip_flag_does_not_hide_professional_season(self) -> None:
        self.assertFalse(intentionally_skipped({
            "skipTff": True,
            "professionalStatus": "professional",
        }))
        self.assertTrue(intentionally_skipped({
            "skipTff": True,
            "noTffRecord": True,
            "professionalStatus": "amateur",
        }))

    def test_cross_season_standings_target_reuse_is_an_error(self) -> None:
        report = {
            "seasonsRequested": 2,
            "seasonsSucceeded": 2,
            "standingsTargets": [
                {"season": "2009-2010", "targetUrl": "http://www.tff.org/Default.aspx?pageID=971&grupID=2605"},
                {"season": "1990-1991", "targetUrl": "https://www.tff.org/Default.aspx?grupID=2605&pageID=971"},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "discovery.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            errors, _warnings, summary = validate_discovery(path, strict=False)
        self.assertEqual(summary["reusedStandingsTargets"], 1)
        self.assertTrue(any("aynı puan hedefini" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
