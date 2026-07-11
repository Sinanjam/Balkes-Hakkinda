#!/usr/bin/env python3
"""Üretilen TFF JSON ağacının uygulamaya verilmeden önce kalite kapısı."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from tff_factory import is_balkes, now, read_json, write_json


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="generated/tff-data")
    parser.add_argument("--report", default="generated/tff-data/reports/validation.json")
    parser.add_argument("--strict", action="store_true", help="Puan tablosu eksik sezonu da hata say")
    args = parser.parse_args()

    root = Path(args.data_root)
    manifest = read_json(root / "manifest.json", {}) or {}
    seasons = as_list(manifest.get("availableSeasons"))
    errors: list[str] = []
    warnings: list[str] = []
    season_reports: list[dict[str, Any]] = []
    all_match_ids: set[str] = set()
    total_matches = 0
    total_weeks = 0
    quality_counts: Counter[str] = Counter()

    if not seasons:
        errors.append("manifest.json içinde availableSeasons boş.")

    for entry in seasons:
        season = str(entry.get("id") or entry.get("name") or "")
        season_dir = root / "seasons" / season
        index = read_json(season_dir / "matches_index.json", None)
        details_ok = 0
        details_complete = 0
        season_errors: list[str] = []
        season_warnings: list[str] = []
        if not isinstance(index, list):
            season_errors.append("matches_index.json eksik veya dizi değil")
            index = []

        ids: set[str] = set()
        for match in index:
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
            home, away = detail.get("homeTeam", ""), detail.get("awayTeam", "")
            if not home or not away:
                season_errors.append(f"takımlar eksik: {match_id}")
                continue
            if not (is_balkes(home) or is_balkes(away)):
                season_errors.append(f"Balıkesirspor olmayan maç: {match_id}")
                continue
            if not detail.get("date"):
                season_errors.append(f"tarih eksik: {match_id}")
                continue
            details_ok += 1
            quality = str(detail.get("quality") or "unknown")
            quality_counts[quality] += 1
            completeness = detail.get("detailCompleteness") or {}
            if any(int(completeness.get(key) or 0) > 0 for key in (
                "starting11Home", "starting11Away", "goals", "cards", "substitutions"
            )):
                details_complete += 1

        if int(entry.get("matchCount") or len(index)) != len(index):
            season_warnings.append(
                f"manifest matchCount={entry.get('matchCount')} fakat indeks={len(index)}"
            )

        standings = read_json(season_dir / "standings_by_week.json", [])
        standings = standings if isinstance(standings, list) else []
        valid_weeks = 0
        valid_week_numbers: list[int] = []
        last_week = 0
        for snapshot in standings:
            week = int(snapshot.get("week") or 0)
            rows = as_list(snapshot.get("standings"))
            if week <= 0 or not rows:
                continue
            teams = [str(row.get("team") or "").strip() for row in rows]
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
            if not any(is_balkes(row.get("team", "")) for row in rows):
                season_warnings.append(f"{week}. hafta tablosunda Balıkesirspor yok")
                continue
            valid_weeks += 1
            valid_week_numbers.append(week)

        if valid_week_numbers:
            expected = set(range(1, max(valid_week_numbers) + 1))
            missing_weeks = sorted(expected - set(valid_week_numbers))
            if missing_weeks:
                message = "puan tablosu eksik haftalar: " + ", ".join(map(str, missing_weeks))
                (season_errors if args.strict else season_warnings).append(message)

        if index and valid_weeks == 0:
            message = f"{season}: maç var fakat haftalık puan tablosu üretilemedi"
            (season_errors if args.strict else season_warnings).append(message)

        total_matches += len(index)
        total_weeks += valid_weeks
        errors.extend(f"{season}: {message}" for message in season_errors)
        warnings.extend(f"{season}: {message}" for message in season_warnings)
        season_reports.append({
            "season": season,
            "matches": len(index),
            "detailsValid": details_ok,
            "detailsWithEventsOrLineups": details_complete,
            "standingsWeeks": valid_weeks,
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
            "matches": total_matches,
            "standingsWeeks": total_weeks,
            "quality": dict(sorted(quality_counts.items())),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
        "seasons": season_reports,
    }
    write_json(args.report, report)
    print(
        f"Doğrulama: durum={report['status']} sezon={len(seasons)} "
        f"maç={total_matches} puanHaftası={total_weeks} "
        f"hata={len(errors)} uyarı={len(warnings)}",
        flush=True,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
