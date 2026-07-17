#!/usr/bin/env python3
"""Üretilen TFF JSON ağacı için güçlü bütünlük ve kapsama kalite kapısı."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from quality_rules import official_standings_scope, standings_not_yet_expected
from tff_factory import (
    is_balkes,
    norm,
    now,
    professional_competition_status,
    read_json,
    write_json,
)


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def registry_items(path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    registry = read_json(path, {}) or {}
    items = {
        str(item.get("season")): item
        for item in as_list(registry.get("seasons"))
        if isinstance(item, dict) and item.get("season")
    }
    order = [str(value) for value in as_list(registry.get("runOrder")) if str(value) in items]
    return order, items


def intentionally_skipped(item: dict[str, Any]) -> bool:
    # ``skipTff`` eski sabit-hedef toplayıcının bu sezonu atlaması için
    # kullanılıyordu. Yeni kulüp-fikstürü keşfi 1997-2001 arasındaki
    # profesyonel sezonları da bulabildiği için bu alan artık sezonun bütünüyle
    # beklenmediği anlamına gelmez.
    if bool(item.get("amateurSeason")) or bool(item.get("noTffRecord")):
        return True
    status = norm(item.get("professionalStatus") or item.get("level") or "")
    return status == "amateur" or "amator" in status


def recompute_summary(details: list[dict[str, Any]]) -> dict[str, int]:
    wins = draws = losses = goals_for = goals_against = 0
    for detail in details:
        balkes = detail.get("balkes") or {}
        result = str(balkes.get("result") or "")
        wins += result == "W"
        draws += result == "D"
        losses += result == "L"
        if balkes.get("goalsFor") is not None:
            goals_for += as_int(balkes.get("goalsFor"))
        if balkes.get("goalsAgainst") is not None:
            goals_against += as_int(balkes.get("goalsAgainst"))
    return {
        "matches": len(details),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goalsFor": goals_for,
        "goalsAgainst": goals_against,
        "goalDifference": goals_for - goals_against,
    }


def normalized_target_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    query = urlencode(sorted((key.lower(), val) for key, val in parse_qsl(parsed.query)))
    return urlunparse(("", parsed.netloc.lower(), parsed.path.lower(), "", query, ""))


def validate_discovery(path: Path, strict: bool) -> tuple[list[str], list[str], dict[str, Any]]:
    discovery = read_json(path, None)
    if not isinstance(discovery, dict):
        return [], ["Kulüp fikstürü keşif raporu bulunamadı."], {"available": False}

    errors: list[str] = []
    warnings: list[str] = []
    hard_errors = as_list(discovery.get("errors"))
    for item in hard_errors:
        if isinstance(item, dict):
            errors.append(f"Keşif {item.get('season')}: {item.get('error')}")

    partial = as_list(discovery.get("paginationFailures"))
    if not partial:
        partial = [
            {
                "season": item.get("season"),
                "pagesFetched": item.get("fixturePages"),
                "pagesExpected": item.get("fixturePagesExpected"),
                "error": item.get("paginationError"),
            }
            for item in as_list(discovery.get("results"))
            if isinstance(item, dict) and not item.get("error")
            and not item.get("paginationComplete", True)
        ]
    for item in partial:
        message = (
            f"Keşif {item.get('season')}: fikstür kısmi "
            f"({item.get('pagesFetched')}/{item.get('pagesExpected')} sayfa); "
            f"{item.get('error') or 'sayfalama tamamlanamadı'}"
        )
        (errors if strict else warnings).append(message)

    requested = as_int(discovery.get("seasonsRequested"))
    succeeded = as_int(discovery.get("seasonsSucceeded"))
    if requested and succeeded < requested and not hard_errors:
        warnings.append(f"Keşif kapsamı eksik: {succeeded}/{requested} sezon başarılı.")

    target_seasons: defaultdict[str, set[str]] = defaultdict(set)
    duplicate_stage_signatures = 0
    for item in as_list(discovery.get("standingsTargets")):
        if not isinstance(item, dict):
            continue
        season = str(item.get("season") or "")
        urls = [item.get("targetUrl")]
        signatures: defaultdict[str, list[str]] = defaultdict(list)
        for stage in as_list(item.get("stages")):
            if not isinstance(stage, dict):
                continue
            urls.append(stage.get("targetUrl"))
            signature = str(stage.get("standingsSignature") or "")
            if signature:
                signatures[signature].append(str(stage.get("id") or stage.get("label") or "?"))
        for url in urls:
            normalized = normalized_target_url(url)
            if normalized and season:
                target_seasons[normalized].add(season)
        for stage_ids in signatures.values():
            if len(stage_ids) > 1:
                duplicate_stage_signatures += 1
                errors.append(
                    f"Keşif {season}: aynı resmi puan tablosu birden fazla aşama sayıldı "
                    f"({', '.join(stage_ids)})."
                )

    reused_targets = {
        url: sorted(seasons)
        for url, seasons in target_seasons.items()
        if len(seasons) > 1
    }
    for url, seasons in reused_targets.items():
        errors.append(
            "Keşif sezonları aynı puan hedefini paylaşıyor: "
            f"{', '.join(seasons)} -> {url}"
        )
    return errors, warnings, {
        "available": True,
        "requested": requested,
        "succeeded": succeeded,
        "withMatches": as_int(discovery.get("seasonsWithMatches")),
        "hardErrors": len(hard_errors),
        "partialPagination": len(partial),
        "reusedStandingsTargets": len(reused_targets),
        "duplicateStageSignatures": duplicate_stage_signatures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="generated/tff-data")
    parser.add_argument("--report", default="generated/tff-data/reports/validation.json")
    parser.add_argument("--registry", default="tools/tff/balkes_tff_seed_registry.json")
    parser.add_argument("--discovery-report", default="", help="Boşsa data-root/reports altı kullanılır")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Eksik sezon/puan tablosu/sayfalama uyarılarını da hata say",
    )
    args = parser.parse_args()

    root = Path(args.data_root)
    discovery_path = (
        Path(args.discovery_report)
        if args.discovery_report
        else root / "reports" / "club_fixture_discovery.json"
    )
    manifest = read_json(root / "manifest.json", {}) or {}
    seasons = as_list(manifest.get("availableSeasons"))
    errors: list[str] = []
    warnings: list[str] = []
    season_reports: list[dict[str, Any]] = []
    all_match_ids: set[str] = set()
    total_matches = 0
    total_weeks = 0
    quality_counts: Counter[str] = Counter()
    contamination_count = 0
    stale_file_count = 0

    discovery_errors, discovery_warnings, discovery_summary = validate_discovery(
        discovery_path, args.strict
    )
    errors.extend(discovery_errors)
    warnings.extend(discovery_warnings)

    registry_order, registry_by_season = registry_items(Path(args.registry))
    manifest_ids = {
        str(entry.get("id") or entry.get("name") or "")
        for entry in seasons
        if isinstance(entry, dict)
    }
    missing_expected = [
        season
        for season in registry_order
        if season not in manifest_ids and not intentionally_skipped(registry_by_season[season])
    ]
    for season in missing_expected:
        message = f"{season}: registry çalıştırma sırasında bekleniyor fakat manifestte veri yok."
        (errors if args.strict else warnings).append(message)

    if not seasons:
        errors.append("manifest.json içinde availableSeasons boş.")

    for entry in seasons:
        if not isinstance(entry, dict):
            errors.append("manifestte nesne olmayan sezon girdisi var.")
            continue
        season = str(entry.get("id") or entry.get("name") or "")
        season_dir = root / "seasons" / season
        index = read_json(season_dir / "matches_index.json", None)
        details_ok = 0
        details_complete = 0
        season_errors: list[str] = []
        season_warnings: list[str] = []
        valid_details: list[dict[str, Any]] = []
        competition_counts: Counter[str] = Counter()
        type_counts: Counter[str] = Counter()
        exact_signatures: defaultdict[str, list[str]] = defaultdict(list)
        league_pairs: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

        if not isinstance(index, list):
            season_errors.append("matches_index.json eksik veya dizi değil")
            index = []

        ids: set[str] = set()
        for match in index:
            if not isinstance(match, dict):
                season_errors.append("indekste nesne olmayan maç var")
                continue
            match_id = str(match.get("id") or "")
            if not match_id:
                season_errors.append("kimliği olmayan maç")
                continue
            if match_id in ids:
                season_errors.append(f"yinelenen maç kimliği: {match_id}")
            ids.add(match_id)
            if match_id in all_match_ids:
                season_errors.append(f"başka sezonda da bulunan maç kimliği: {match_id}")
            all_match_ids.add(match_id)

            detail_path = season_dir / "matches" / f"{match_id}.json"
            detail = read_json(detail_path, None)
            if not isinstance(detail, dict):
                season_errors.append(f"detay dosyası yok: {match_id}")
                continue
            home, away = str(detail.get("homeTeam") or ""), str(detail.get("awayTeam") or "")
            if not home or not away:
                season_errors.append(f"takımlar eksik: {match_id}")
                continue
            if not (is_balkes(home) or is_balkes(away)):
                season_errors.append(f"Balıkesirspor olmayan maç: {match_id}")
                continue
            if not detail.get("date"):
                season_errors.append(f"tarih eksik: {match_id}")
                continue
            professional, evidence = professional_competition_status(detail.get("competition"))
            if not professional:
                contamination_count += 1
                season_errors.append(
                    f"profesyonel A takım dışı kayıt: {match_id} "
                    f"({detail.get('competition')}; {evidence})"
                )
                continue

            details_ok += 1
            valid_details.append(detail)
            quality = str(detail.get("quality") or "unknown")
            quality_counts[quality] += 1
            competition_counts[str(detail.get("competition") or "Bilinmeyen")] += 1
            match_type = str(detail.get("matchType") or "league")
            type_counts[match_type] += 1
            completeness = detail.get("detailCompleteness") or {}
            if any(as_int(completeness.get(key)) > 0 for key in (
                "starting11Home", "starting11Away", "goals", "cards", "substitutions"
            )):
                details_complete += 1

            signature = "|".join([
                str(detail.get("date") or ""), norm(home), norm(away), match_type,
            ])
            exact_signatures[signature].append(match_id)
            if match_type == "league":
                league_pairs[
                    norm(detail.get("competition")) + "|" + norm(home) + "|" + norm(away)
                ].append(detail)

        for signature, match_ids in exact_signatures.items():
            if len(match_ids) > 1:
                season_errors.append(
                    f"aynı tarih/takım eşleşmesi yinelenmiş: {','.join(match_ids)} ({signature})"
                )
        for pair, matches in league_pairs.items():
            if len(matches) < 2:
                continue
            played = [m for m in matches if (m.get("score") or {}).get("played")]
            unplayed = [m for m in matches if not (m.get("score") or {}).get("played")]
            ids_for_pair = ",".join(str(m.get("id")) for m in matches)
            if played and unplayed:
                season_errors.append(
                    f"oynanan maç yanında silinmemiş ertelenmiş fikstür: {ids_for_pair} ({pair})"
                )
            elif len(played) > 1:
                season_warnings.append(f"aynı iç/dış saha lig eşleşmesi birden fazla: {ids_for_pair}")

        detail_files = {path.stem: path for path in (season_dir / "matches").glob("*.json")}
        stale_ids = sorted(set(detail_files) - ids)
        stale_file_count += len(stale_ids)
        if stale_ids:
            season_warnings.append(
                f"indekste olmayan {len(stale_ids)} artık detay dosyası var; örnek={','.join(stale_ids[:8])}"
            )
            for stale_id in stale_ids:
                stale = read_json(detail_files[stale_id], {}) or {}
                professional, _ = professional_competition_status(stale.get("competition"))
                if not professional:
                    contamination_count += 1
                    season_errors.append(f"artık dosyada altyapı/amateur kayıt var: {stale_id}")
                    break

        if as_int(entry.get("matchCount") or len(index)) != len(index):
            season_errors.append(
                f"manifest matchCount={entry.get('matchCount')} fakat indeks={len(index)}"
            )
        if len(index) > 65:
            season_errors.append(f"bir A takım sezonu için olağandışı maç sayısı: {len(index)}")
        league_count = type_counts.get("league", 0)
        league_played = sum(
            1 for detail in valid_details
            if detail.get("matchType") == "league" and (detail.get("score") or {}).get("played")
        )
        if league_count > 46:
            season_errors.append(f"olağandışı lig maçı sayısı: {league_count}")
        elif 0 < league_count < 10:
            season_warnings.append(f"lig verisi büyük olasılıkla eksik: yalnızca {league_count} maç")

        expected_matches = as_int((registry_by_season.get(season) or {}).get("expectedLeagueMatches"))
        if expected_matches and league_count != expected_matches:
            message = f"beklenen lig maçı={expected_matches}, bulunan={league_count}"
            (season_errors if args.strict else season_warnings).append(message)

        season_json = read_json(season_dir / "season.json", {}) or {}
        summary = season_json.get("summary") or {}
        computed = recompute_summary(valid_details)
        for key in ("matches", "wins", "draws", "losses", "goalsFor", "goalsAgainst", "goalDifference"):
            if key in summary and as_int(summary.get(key)) != computed[key]:
                severity = season_errors if key == "matches" else season_warnings
                severity.append(
                    f"season.json summary.{key}={summary.get(key)}, maçlardan hesaplanan={computed[key]}"
                )

        standings = read_json(season_dir / "standings_by_week.json", [])
        standings = standings if isinstance(standings, list) else []
        valid_weeks = 0
        valid_week_numbers: list[int] = []
        last_week = 0
        last_balkes: dict[str, Any] | None = None
        stage_balkes: dict[str, dict[str, Any]] = {}
        stage_snapshots: dict[str, dict[str, Any]] = {}
        for snapshot in standings:
            if not isinstance(snapshot, dict):
                continue
            week = as_int(snapshot.get("week"))
            rows = as_list(snapshot.get("standings"))
            if week <= 0 or not rows:
                continue
            teams = [str(row.get("team") or "").strip() for row in rows if isinstance(row, dict)]
            unique_teams = {team.casefold() for team in teams if team}
            if len(unique_teams) < 4:
                season_warnings.append(
                    f"{week}. hafta tablosu tam lig tablosu değil: yalnızca {len(unique_teams)} takım"
                )
                continue
            if len(unique_teams) != len([team for team in teams if team]):
                season_warnings.append(f"{week}. hafta tablosunda yinelenen takım var")
                continue
            if week < last_week:
                season_warnings.append("puan tablosu haftaları sıralı değil")
            last_week = week
            balkes_row = next(
                (row for row in rows if isinstance(row, dict) and is_balkes(row.get("team", ""))),
                None,
            )
            if not balkes_row:
                season_warnings.append(f"{week}. hafta tablosunda Balıkesirspor yok")
                continue
            valid_weeks += 1
            valid_week_numbers.append(week)
            last_balkes = balkes_row
            if snapshot.get("stageId"):
                stage_id = str(snapshot["stageId"])
                stage_balkes[stage_id] = balkes_row
                stage_snapshots[stage_id] = snapshot

        if valid_week_numbers:
            expected_weeks = set(range(1, max(valid_week_numbers) + 1))
            missing_weeks = sorted(expected_weeks - set(valid_week_numbers))
            if missing_weeks:
                message = "puan tablosu eksik haftalar: " + ", ".join(map(str, missing_weeks))
                (season_errors if args.strict else season_warnings).append(message)

        standings_pending = standings_not_yet_expected(valid_details)
        if league_count and valid_weeks == 0:
            if standings_pending:
                season_warnings.append(
                    "henüz oynanmış lig maçı yok; puan tablosu bu aşamada beklenmiyor"
                )
            else:
                message = "lig maçı var fakat haftalık puan tablosu üretilemedi"
                (season_errors if args.strict else season_warnings).append(message)
        standings_match_types: list[str] = []
        if last_balkes:
            table_played = 0
            if stage_balkes:
                configured = {
                    str(stage.get("id")): stage
                    for stage in (registry_by_season.get(season) or {}).get("standingsStages", [])
                    if isinstance(stage, dict) and stage.get("id")
                }
                stage_ids = sorted(
                    stage_balkes,
                    key=lambda value: as_int((stage_snapshots.get(value) or {}).get("stageNumber")),
                )
                stage_played = 0
                table_goals_for = 0
                table_goals_against = 0
                for stage_id in stage_ids:
                    row = stage_balkes[stage_id]
                    snapshot = stage_snapshots.get(stage_id) or {}
                    carried = as_int(snapshot.get("stageCarriedMatches"))
                    effective_played = as_int(row.get("played")) - carried
                    expected = as_int((configured.get(stage_id) or {}).get("expectedMatches"))
                    if not expected:
                        expected = as_int(snapshot.get("stageExpectedMatches"))
                    if expected and effective_played != expected:
                        season_errors.append(
                            f"{stage_id} son tablosu ek oynanan={effective_played}, beklenen={expected}"
                        )
                    stage_played += effective_played
                    raw_goals_for = as_int(row.get("goalsFor"))
                    raw_goals_against = as_int(row.get("goalsAgainst"))
                    if carried:
                        table_goals_for = raw_goals_for
                        table_goals_against = raw_goals_against
                    else:
                        table_goals_for += raw_goals_for
                        table_goals_against += raw_goals_against
                table_played = stage_played
            else:
                table_played = as_int(last_balkes.get("played"))
                table_goals_for = as_int(last_balkes.get("goalsFor"))
                table_goals_against = as_int(last_balkes.get("goalsAgainst"))

            scope = official_standings_scope(valid_details, {
                "played": table_played,
                "goalsFor": table_goals_for,
                "goalsAgainst": table_goals_against,
            })
            standings_match_types = list(scope["matchTypes"])
            compared = scope["totals"]
            if table_played != compared["played"]:
                if stage_balkes:
                    season_errors.append(
                        f"resmi aşamalarda toplam oynanan={table_played}, "
                        f"maç indeksinde oynanan lig maçı={compared['played']}"
                    )
                else:
                    season_errors.append(
                        f"resmi son tabloda oynanan={table_played}, "
                        f"maç indeksinde oynanan lig maçı={compared['played']}"
                    )
            if compared["goalsFor"] != table_goals_for:
                season_warnings.append(
                    f"lig gol toplamı uyuşmuyor: maçlar={compared['goalsFor']}, "
                    f"tablo={table_goals_for}"
                )
            if compared["goalsAgainst"] != table_goals_against:
                season_warnings.append(
                    f"yenilen gol toplamı uyuşmuyor: maçlar={compared['goalsAgainst']}, "
                    f"tablo={table_goals_against}"
                )

        # Geçmişte kalmış oynanmamış tekil kayıtları silmeyiz; inceleme için işaretleriz.
        past_unplayed = [
            detail for detail in valid_details
            if not (detail.get("score") or {}).get("played")
            and str(detail.get("date") or "9999-12-31") < date.today().isoformat()
        ]
        if past_unplayed:
            season_warnings.append(
                f"geçmiş tarihli oynanmamış {len(past_unplayed)} kayıt var; "
                f"örnek={','.join(str(item.get('id')) for item in past_unplayed[:8])}"
            )

        total_matches += len(index)
        total_weeks += valid_weeks
        errors.extend(f"{season}: {message}" for message in season_errors)
        warnings.extend(f"{season}: {message}" for message in season_warnings)
        season_reports.append({
            "season": season,
            "matches": len(index),
            "leagueMatches": league_count,
            "leaguePlayedMatches": league_played,
            "detailsValid": details_ok,
            "detailsWithEventsOrLineups": details_complete,
            "standingsWeeks": valid_weeks,
            "standingsPending": standings_pending,
            "officialStandingsMatchTypes": standings_match_types,
            "competitions": dict(competition_counts.most_common()),
            "matchTypes": dict(type_counts),
            "staleDetailFiles": len(stale_ids),
            "errors": season_errors,
            "warnings": season_warnings,
        })

    if total_matches == 0:
        errors.append("Hiç maç üretilmedi.")

    report = {
        "generatedAt": now(),
        "status": "error" if errors else "ok_with_warnings" if warnings else "ok",
        "summary": {
            "seasons": len(seasons),
            "registryExpectedSeasons": len(registry_order),
            "missingExpectedSeasons": len(missing_expected),
            "matches": total_matches,
            "standingsWeeks": total_weeks,
            "quality": dict(sorted(quality_counts.items())),
            "nonProfessionalRecords": contamination_count,
            "staleDetailFiles": stale_file_count,
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "discovery": discovery_summary,
        "errors": errors,
        "warnings": warnings,
        "missingExpectedSeasons": missing_expected,
        "seasons": season_reports,
    }
    write_json(args.report, report)
    print(
        f"Doğrulama: durum={report['status']} sezon={len(seasons)} "
        f"maç={total_matches} puanHaftası={total_weeks} "
        f"altyapı={contamination_count} hata={len(errors)} uyarı={len(warnings)}",
        flush=True,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
