#!/usr/bin/env python3
"""Mevcut TFF çıktısından altyapı, yinelenen ve artık dosyaları temizler."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from tff_factory import (
    build_manifest,
    index_from_detail,
    is_balkes,
    match_signature,
    norm,
    now,
    professional_competition_status,
    read_json,
    rebuild_global_indexes,
    remove_superseded_unplayed,
    write_json,
)


SANITIZER_VERSION = "v1-professional-team-only"


def season_summary(details: list[dict[str, Any]], previous: dict[str, Any]) -> dict[str, Any]:
    wins = draws = losses = goals_for = goals_against = 0
    types: Counter[str] = Counter()
    for detail in details:
        types[str(detail.get("matchType") or "league")] += 1
        balkes = detail.get("balkes") or {}
        result = str(balkes.get("result") or "")
        wins += result == "W"
        draws += result == "D"
        losses += result == "L"
        if balkes.get("goalsFor") is not None:
            goals_for += int(balkes.get("goalsFor") or 0)
        if balkes.get("goalsAgainst") is not None:
            goals_against += int(balkes.get("goalsAgainst") or 0)
    summary: dict[str, Any] = {
        "matches": len(details),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goalsFor": goals_for,
        "goalsAgainst": goals_against,
        "goalDifference": goals_for - goals_against,
        "matchTypes": dict(types),
    }
    for key in ("points", "rawPoints", "pointsDeducted", "finalRank"):
        if key in previous:
            summary[key] = previous[key]
    return summary


def sanitize_season(season_dir: Path, dry_run: bool) -> dict[str, Any]:
    season = season_dir.name
    index = read_json(season_dir / "matches_index.json", [])
    index = index if isinstance(index, list) else []
    matches_dir = season_dir / "matches"
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for item in index:
        match_id = str(item.get("id") or "") if isinstance(item, dict) else ""
        detail = read_json(matches_dir / f"{match_id}.json", None) if match_id else None
        if not isinstance(detail, dict):
            rejected.append({"id": match_id, "reason": "detail_missing"})
            continue
        if not (is_balkes(detail.get("homeTeam")) or is_balkes(detail.get("awayTeam"))):
            rejected.append({"id": match_id, "reason": "balkes_not_found"})
            continue
        professional, evidence = professional_competition_status(detail.get("competition"))
        if not professional:
            rejected.append({"id": match_id, "reason": f"non_professional:{evidence}"})
            continue
        detail["teamLevel"] = "professional"
        detail["teamLevelEvidence"] = evidence
        accepted.append(detail)

    by_signature: dict[str, dict[str, Any]] = {}
    duplicate_drops: list[dict[str, str]] = []
    for detail in accepted:
        signature = match_signature(detail)
        current = by_signature.get(signature)
        if current is None:
            by_signature[signature] = detail
            continue
        keep, drop = current, detail
        if len(json.dumps(detail, ensure_ascii=False)) > len(json.dumps(current, ensure_ascii=False)):
            keep, drop = detail, current
            by_signature[signature] = detail
        duplicate_drops.append({
            "id": str(drop.get("id") or ""),
            "reason": "duplicate_match_signature",
            "kept": str(keep.get("id") or ""),
        })

    cleaned, superseded = remove_superseded_unplayed(list(by_signature.values()))
    cleaned.sort(key=lambda value: (str(value.get("date") or ""), int(str(value.get("id") or 0))))
    keep_ids = {str(detail.get("id")) for detail in cleaned}
    all_files = list(matches_dir.glob("*.json"))
    pruned_files = [path for path in all_files if path.stem not in keep_ids]

    if not dry_run:
        for detail in cleaned:
            write_json(matches_dir / f"{detail['id']}.json", detail)
        for path in pruned_files:
            path.unlink()
        write_json(season_dir / "matches_index.json", [index_from_detail(detail) for detail in cleaned])
        season_json = read_json(season_dir / "season.json", {}) or {"id": season, "name": season}
        season_json["summary"] = season_summary(cleaned, season_json.get("summary") or {})
        season_json["sanitizedAt"] = now()
        season_json["sanitizerVersion"] = SANITIZER_VERSION
        write_json(season_dir / "season.json", season_json)

    return {
        "season": season,
        "before": len(index),
        "after": len(cleaned),
        "nonProfessionalOrInvalidDropped": len(rejected),
        "duplicatesDropped": len(duplicate_drops),
        "supersededDropped": len(superseded),
        "filesPruned": len(pruned_files),
        "rejected": rejected,
        "duplicateDetails": duplicate_drops + superseded,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="generated/tff-data")
    parser.add_argument("--report", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.data_root)
    report_path = Path(args.report) if args.report else root / "reports" / "sanitization.json"
    results = [
        sanitize_season(path, args.dry_run)
        for path in sorted((root / "seasons").iterdir(), reverse=True)
        if path.is_dir() and (path / "matches_index.json").exists()
    ] if (root / "seasons").exists() else []

    if not args.dry_run:
        build_manifest(root, [item["season"] for item in results])
        rebuild_global_indexes(root)
        manifest = read_json(root / "manifest.json", {}) or {}
        data_report = read_json(root / "data_report.json", {}) or {}
        data_report["generatedAt"] = now()
        data_report["sanitizerVersion"] = SANITIZER_VERSION
        data_report["seasons"] = manifest.get("availableSeasons", [])
        data_report["totalAppMatches"] = sum(
            int(item.get("matchCount") or 0)
            for item in manifest.get("availableSeasons", [])
            if isinstance(item, dict)
        )
        data_report["playersIndexed"] = len(read_json(root / "players_index.json", []) or [])
        data_report["opponentsIndexed"] = len(read_json(root / "opponents_index.json", []) or [])
        write_json(root / "data_report.json", data_report)

    report = {
        "generatedAt": now(),
        "version": SANITIZER_VERSION,
        "dryRun": bool(args.dry_run),
        "summary": {
            "seasons": len(results),
            "matchesBefore": sum(item["before"] for item in results),
            "matchesAfter": sum(item["after"] for item in results),
            "nonProfessionalOrInvalidDropped": sum(item["nonProfessionalOrInvalidDropped"] for item in results),
            "duplicatesDropped": sum(item["duplicatesDropped"] for item in results),
            "supersededDropped": sum(item["supersededDropped"] for item in results),
            "filesPruned": sum(item["filesPruned"] for item in results),
        },
        "seasons": results,
    }
    write_json(report_path, report)
    summary = report["summary"]
    print(
        f"Temizlik: sezon={summary['seasons']} maç={summary['matchesBefore']}->{summary['matchesAfter']} "
        f"altyapı/geçersiz={summary['nonProfessionalOrInvalidDropped']} "
        f"yinelenen={summary['duplicatesDropped'] + summary['supersededDropped']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
