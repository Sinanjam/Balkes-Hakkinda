#!/usr/bin/env python3
"""Yerel TFF çıktısının yayımlanmaya hazır olup olmadığını tek raporda toplar."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quality_rules import as_match_date, standings_not_yet_expected


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def source_url(detail: dict[str, Any]) -> str:
    source = detail.get("source")
    if isinstance(source, dict):
        return str(source.get("url") or "")
    return str(source or "")


def lineup_counts(detail: dict[str, Any]) -> tuple[int, int]:
    lineups = detail.get("lineups") if isinstance(detail.get("lineups"), dict) else {}
    home = lineups.get("home") if isinstance(lineups.get("home"), dict) else {}
    away = lineups.get("away") if isinstance(lineups.get("away"), dict) else {}
    return len(as_list(home.get("starting11"))), len(as_list(away.get("starting11")))


def unique_messages(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        key = value.strip().rstrip(".").casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="TFF senkron tamamlanma kalite kapısı")
    parser.add_argument("--data-root", default="generated/tff-data")
    parser.add_argument("--report", default="generated/tff-data/reports/completion.json")
    args = parser.parse_args()

    root = Path(args.data_root)
    reports = root / "reports"
    manifest = read_json(root / "manifest.json", {}) or {}
    validation = read_json(reports / "validation.json", None)
    repair = read_json(reports / "repair_validation.json", None)
    discovery = read_json(reports / "club_fixture_discovery.json", None)
    seasons = as_list(manifest.get("availableSeasons"))

    errors: list[str] = []
    warnings: list[str] = []
    quality: Counter[str] = Counter()
    season_reports: list[dict[str, Any]] = []
    total_matches = total_league = total_league_played = total_weeks = 0
    core_complete = full_lineups = with_events = with_officials = 0
    source_limited: list[dict[str, str]] = []
    pending_standings: list[dict[str, Any]] = []

    if not isinstance(validation, dict):
        errors.append("reports/validation.json bulunamadı veya okunamadı.")
    elif validation.get("status") == "error" or as_int((validation.get("summary") or {}).get("errors")):
        validation_errors = [str(value) for value in as_list(validation.get("errors")) if value]
        errors.extend(validation_errors or ["Sıkı genel doğrulama hata verdi."])
    if isinstance(validation, dict):
        warnings.extend(str(value) for value in as_list(validation.get("warnings")) if value)

    if not isinstance(repair, dict):
        errors.append("reports/repair_validation.json bulunamadı veya okunamadı.")
    elif repair.get("status") != "ok":
        errors.append("Maç haftası/oyuncu indeksi onarım doğrulaması hata verdi.")

    if not isinstance(discovery, dict):
        errors.append("Kulüp fikstürü keşif raporu bulunamadı.")
    else:
        requested = as_int(discovery.get("seasonsRequested"))
        succeeded = as_int(discovery.get("seasonsSucceeded"))
        partial = as_list(discovery.get("paginationFailures"))
        if requested <= 0 or succeeded != requested:
            errors.append(f"Sezon keşfi tamamlanmadı: {succeeded}/{requested}.")
        if partial:
            errors.append(f"{len(partial)} sezonda fikstür sayfalaması yarım kaldı.")

    if not seasons:
        errors.append("manifest.json içinde yayımlanabilir sezon yok.")

    for entry in seasons:
        if not isinstance(entry, dict):
            errors.append("Manifestte nesne olmayan sezon girdisi var.")
            continue
        season = str(entry.get("id") or entry.get("name") or "")
        season_dir = root / "seasons" / season
        index = read_json(season_dir / "matches_index.json", None)
        if not isinstance(index, list):
            errors.append(f"{season}: matches_index.json eksik.")
            index = []

        season_league = season_league_played = season_core = season_lineups = season_events = 0
        season_source_limited = 0
        season_details: list[dict[str, Any]] = []
        missing_round_ids: list[str] = []
        for item in index:
            if not isinstance(item, dict):
                errors.append(f"{season}: bozuk maç indeks girdisi.")
                continue
            match_id = str(item.get("id") or "")
            detail = read_json(season_dir / "matches" / f"{match_id}.json", None)
            if not isinstance(detail, dict):
                errors.append(f"{season}/{match_id}: maç detayı eksik.")
                continue

            season_details.append(detail)
            total_matches += 1
            match_type = str(detail.get("matchType") or "league")
            score = detail.get("score") if isinstance(detail.get("score"), dict) else {}
            if match_type == "league":
                total_league += 1
                season_league += 1
                if score.get("played"):
                    total_league_played += 1
                    season_league_played += 1
                if as_int(detail.get("week")) <= 0 or as_int(detail.get("standingsWeek")) <= 0:
                    missing_round_ids.append(match_id)

            missing_core = [
                key for key, value in (
                    ("id", detail.get("id")),
                    ("season", detail.get("season")),
                    ("date", detail.get("date")),
                    ("homeTeam", detail.get("homeTeam")),
                    ("awayTeam", detail.get("awayTeam")),
                    ("competition", detail.get("competition")),
                    ("source.url", source_url(detail)),
                ) if not value
            ]
            if missing_core:
                errors.append(f"{season}/{match_id}: temel alan eksik: {', '.join(missing_core)}.")
            else:
                core_complete += 1
                season_core += 1

            home_lineup, away_lineup = lineup_counts(detail)
            if home_lineup >= 11 and away_lineup >= 11:
                full_lineups += 1
                season_lineups += 1
            events = as_list(detail.get("events"))
            if events:
                with_events += 1
                season_events += 1
            if as_list(detail.get("officials")) or as_list(detail.get("referees")):
                with_officials += 1

            match_quality = str(detail.get("quality") or "unknown")
            quality[match_quality] += 1
            if score.get("played") and home_lineup == 0 and away_lineup == 0 and not events:
                season_source_limited += 1
                source_limited.append({
                    "season": season,
                    "matchId": match_id,
                    "reason": "TFF maç sayfasında kadro ve olay bölümü yayımlanmamış",
                    "sourceUrl": source_url(detail),
                })

        if missing_round_ids:
            errors.append(
                f"{season}: {len(missing_round_ids)} lig maçında doğrulanmış hafta eksik; "
                f"örnek={','.join(missing_round_ids[:10])}."
            )

        standings_pending = standings_not_yet_expected(season_details)
        standings = read_json(season_dir / "standings_by_week.json", None)
        if season_league and not isinstance(standings, list) and not standings_pending:
            errors.append(f"{season}: standings_by_week.json eksik.")
        if not isinstance(standings, list):
            standings = []
        valid_weeks = sum(
            1 for snapshot in as_list(standings)
            if isinstance(snapshot, dict)
            and as_int(snapshot.get("week")) > 0
            and as_list(snapshot.get("standings"))
        )
        if season_league and valid_weeks == 0:
            if standings_pending:
                fixture_dates = sorted(
                    match_day.isoformat()
                    for detail in season_details
                    if detail.get("matchType") == "league"
                    if (match_day := as_match_date(detail.get("date"))) is not None
                )
                pending_standings.append({
                    "season": season,
                    "leagueMatches": season_league,
                    "firstFixtureDate": fixture_dates[0] if fixture_dates else None,
                })
                warnings.append(
                    f"{season}: henüz oynanmış lig maçı yok; "
                    "puan tablosu bu aşamada beklenmiyor."
                )
            else:
                errors.append(f"{season}: geçerli haftalık puan tablosu yok.")
        total_weeks += valid_weeks
        if as_int(entry.get("matchCount")) != len(index):
            errors.append(
                f"{season}: manifest maç sayısı={entry.get('matchCount')}, indeks={len(index)}."
            )
        season_reports.append({
            "season": season,
            "matches": len(index),
            "leagueMatches": season_league,
            "leaguePlayedMatches": season_league_played,
            "coreComplete": season_core,
            "matchesWithFullLineups": season_lineups,
            "matchesWithEvents": season_events,
            "sourceLimitedMatches": season_source_limited,
            "standingsWeeks": valid_weeks,
        })

    expected_total = sum(
        as_int(entry.get("matchCount")) for entry in seasons if isinstance(entry, dict)
    )
    if total_matches != expected_total:
        errors.append(f"Toplam maç sayısı uyuşmuyor: okunan={total_matches}, manifest={expected_total}.")
    if source_limited:
        warnings.append(
            f"{len(source_limited)} maçta TFF kaynak sayfası kadro/olay ayrıntısı yayımlamıyor; "
            "bu kayıtlar uydurulmadan kaynak kısıtı olarak bırakıldı."
        )

    errors = unique_messages(errors)
    warnings = unique_messages(warnings)

    if errors:
        status = "error"
    elif source_limited:
        status = "clean_with_source_limits"
    elif warnings:
        status = "clean_with_warnings"
    else:
        status = "clean"

    report = {
        "generatedAt": now(),
        "status": status,
        "readyToPublish": not errors,
        "summary": {
            "seasons": len(seasons),
            "matches": total_matches,
            "leagueMatches": total_league,
            "leaguePlayedMatches": total_league_played,
            "standingsWeeks": total_weeks,
            "pendingStandingsSeasons": len(pending_standings),
            "coreComplete": core_complete,
            "matchesWithFullLineups": full_lineups,
            "matchesWithEvents": with_events,
            "matchesWithOfficials": with_officials,
            "sourceLimitedMatches": len(source_limited),
            "quality": dict(sorted(quality.items())),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
        "pendingStandings": pending_standings,
        "sourceLimitedMatches": source_limited,
        "seasons": season_reports,
    }
    write_json(Path(args.report), report)
    print(
        "Tamamlanma: "
        f"durum={report['status']} sezon={len(seasons)} maç={total_matches} "
        f"puanHaftası={total_weeks} kaynakKısıtı={len(source_limited)} hata={len(errors)}",
        flush=True,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
