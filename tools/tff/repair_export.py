#!/usr/bin/env python3
"""TFF uygulama çıktısını yayın öncesi onarır ve uyumluluk kapısından geçirir.

Bu araç yalnızca daha önce doğrulanmış TFF maç JSON'larını işler. Ağ isteği
atmaz, yeni maç üretmez ve kupa/play-off karşılaşmalarına sahte lig haftası
vermez.
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from tff_factory import (
    build_players_index_for_match,
    index_from_detail,
    is_balkes,
    norm,
    now,
    read_json,
    write_json,
)


PERSON_SUFFIX_PATTERNS = (
    re.compile(r"\s*,\s*\d{1,3}(?:\+\d*)?\s*$", re.I),
    re.compile(r"\s+\d{1,3}\+\d*\s*$", re.I),
    re.compile(r"\s*,?\s*\d{1,3}\s*\.\s*(?:dk|dakika)\b.*$", re.I),
    re.compile(r"\s*,?\s*\d{1,3}\s*(?:dk|dakika)\b.*$", re.I),
)
DIRTY_PERSON_RE = re.compile(
    r"(?:,\s*\d{1,3}(?:\+\d*)?|\s\d{1,3}\+\d*|\d{1,3}\s*\.\s*(?:dk|dakika))\s*$",
    re.I,
)
WEEK_RE = re.compile(r"\b(\d{1,3})\s*\.?\s*Hafta\b", re.I)
LEADING_WEEK_RE = re.compile(r"^\s*(\d{1,2})(?=\s+\S)")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def clean_person_name(value: Any) -> str:
    """TFF kişi alanının sonuna yapışan dakika parçalarını güvenle kaldırır."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    previous = None
    while previous != text:
        previous = text
        for pattern in PERSON_SUFFIX_PATTERNS:
            text = pattern.sub("", text).strip(" ,;-–—")
    return text


def _clean_mapping_field(mapping: Any, key: str) -> int:
    if not isinstance(mapping, dict) or key not in mapping:
        return 0
    old = str(mapping.get(key) or "")
    new = clean_person_name(old)
    if old == new:
        return 0
    mapping[key] = new
    return 1


def repair_detail_people(detail: dict[str, Any]) -> int:
    """Maç içindeki kişi alanlarını temizler ve maç oyuncu indeksini yeniden kurar."""
    changed = 0
    lineups = detail.get("lineups") if isinstance(detail.get("lineups"), dict) else {}
    for side in ("home", "away"):
        block = lineups.get(side) if isinstance(lineups.get(side), dict) else {}
        for collection in ("starting11", "substitutes", "technicalStaff"):
            for person in as_list(block.get(collection)):
                changed += _clean_mapping_field(person, "name")
        if block.get("coach"):
            changed += _clean_mapping_field(block, "coach")

    for collection, fields in (
        ("events", ("player", "scorer", "playerIn", "playerOut", "player_in", "player_out")),
        ("goals", ("player", "scorer")),
        ("goalScorers", ("player", "scorer")),
        ("cards", ("player",)),
        ("substitutions", ("playerIn", "playerOut", "player_in", "player_out")),
    ):
        for item in as_list(detail.get(collection)):
            for field in fields:
                changed += _clean_mapping_field(item, field)

    events = as_list(detail.get("events"))
    detail["players"] = build_players_index_for_match(lineups, events)
    completeness = detail.setdefault("detailCompleteness", {})
    if isinstance(completeness, dict):
        completeness["players"] = len(detail["players"])
    return changed


def fixture_week(fixture: dict[str, Any], detail: dict[str, Any]) -> tuple[int, str]:
    week = as_int(fixture.get("week"))
    if week > 0:
        return week, "tff_club_fixture"
    row_text = str(fixture.get("rowText") or "")
    match = WEEK_RE.search(row_text)
    if match:
        return int(match.group(1)), "tff_club_fixture_row"
    # TFF kulüp fikstürü tablosunda hafta ayrı sütundadır. ``tr`` metni
    # düzleştirildiğinde "17 BALIKESİRSPOR ..." biçiminde satırın başına gelir;
    # yanında "Hafta" kelimesi bulunmaz.
    match = LEADING_WEEK_RE.match(row_text)
    if match and 0 < int(match.group(1)) <= 60:
        return int(match.group(1)), "tff_club_fixture_row_leading_column"
    club_fixture = detail.get("clubFixture") if isinstance(detail.get("clubFixture"), dict) else {}
    week = as_int(club_fixture.get("week"))
    if week > 0:
        return week, "tff_club_fixture_embedded"
    match = WEEK_RE.search(str(club_fixture.get("rowText") or ""))
    if match:
        return int(match.group(1)), "tff_club_fixture_embedded_row"
    match = LEADING_WEEK_RE.match(str(club_fixture.get("rowText") or ""))
    if match and 0 < int(match.group(1)) <= 60:
        return int(match.group(1)), "tff_club_fixture_embedded_leading_column"
    for key in ("stageWeek", "standingsWeek", "week"):
        week = as_int(detail.get(key))
        if week > 0:
            return week, "existing_verified_round"
    return 0, "missing"


def configured_stages(registry_item: dict[str, Any], snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    configured = [item for item in as_list(registry_item.get("standingsStages")) if isinstance(item, dict)]
    for number, stage in enumerate(configured, 1):
        max_week = as_int(stage.get("maxWeek"))
        expected = as_int(stage.get("expectedMatches")) or max_week
        stages.append({
            "id": str(stage.get("id") or f"stage-{number}"),
            "label": str(stage.get("label") or stage.get("id") or f"Aşama {number}"),
            "number": number,
            "maxWeek": max_week or expected,
            "expectedMatches": expected or max_week,
        })
    if stages:
        return stages

    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        stage_id = str(snapshot.get("stageId") or "")
        if not stage_id:
            continue
        if stage_id not in seen:
            order.append(stage_id)
            seen[stage_id] = {
                "id": stage_id,
                "label": str(snapshot.get("stageLabel") or stage_id),
                "number": as_int(snapshot.get("stageNumber")) or len(order),
                "maxWeek": 0,
                "expectedMatches": as_int(snapshot.get("stageExpectedMatches")),
            }
        seen[stage_id]["maxWeek"] = max(
            as_int(seen[stage_id].get("maxWeek")),
            as_int(snapshot.get("stageWeek")),
        )
    stages = [seen[key] for key in order]
    for stage in stages:
        if not stage["expectedMatches"]:
            stage["expectedMatches"] = stage["maxWeek"]
    return stages


def fixture_map(registry_item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in as_list(registry_item.get("knownFixtures"))
        if isinstance(item, dict) and item.get("id")
    }


def _stage_for_position(stages: list[dict[str, Any]], position: int) -> tuple[dict[str, Any] | None, int, int]:
    if not stages:
        return None, position + 1, 0
    offset = 0
    remaining = position
    for index, stage in enumerate(stages):
        capacity = as_int(stage.get("expectedMatches")) or as_int(stage.get("maxWeek"))
        if index == len(stages) - 1 or remaining < capacity:
            return stage, remaining + 1, offset
        remaining -= capacity
        offset += as_int(stage.get("maxWeek")) or capacity
    return stages[-1], remaining + 1, offset


def assign_league_rounds(
    details: list[dict[str, Any]],
    registry_item: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Lig maçlarına TFF fikstür haftası ve çok aşamalı sezon alanlarını yazar."""
    fixtures = fixture_map(registry_item)
    stages = configured_stages(registry_item, snapshots)
    league = sorted(
        (item for item in details if str(item.get("matchType") or "league") == "league"),
        key=lambda item: (str(item.get("date") or ""), as_int(item.get("id"))),
    )
    assigned = exact = fallback = 0
    missing_ids: list[str] = []
    multi_stage = len(stages) > 1

    for position, detail in enumerate(league):
        stage, sequence_week, offset = _stage_for_position(stages, position)
        raw_week, source = fixture_week(fixtures.get(str(detail.get("id"))) or {}, detail)
        stage_max = as_int(stage.get("maxWeek")) if stage else 0
        if raw_week > 0 and (not stage_max or raw_week <= stage_max):
            stage_week = raw_week
            exact += 1
        else:
            stage_week = sequence_week
            source = "stage_sequence_fallback"
            fallback += 1
            missing_ids.append(str(detail.get("id") or ""))
        global_week = offset + stage_week if stage else stage_week
        detail["week"] = global_week
        detail["standingsWeek"] = global_week
        detail["stageWeek"] = stage_week
        detail["roundType"] = "league"
        detail["roundLabel"] = f"{stage_week}. Hafta"
        detail["roundSource"] = source
        if stage:
            detail["leagueStageId"] = stage["id"]
            detail["leagueStageLabel"] = stage["label"]
            detail["leagueStageNumber"] = stage["number"]
            if multi_stage:
                detail["stageId"] = stage["id"]
                detail["stageLabel"] = stage["label"]
                detail["stageNumber"] = stage["number"]
        assigned += 1

    non_league_cleaned = 0
    for detail in details:
        if str(detail.get("matchType") or "league") == "league":
            continue
        for key in (
            "standingsWeek", "stageWeek", "stageId", "stageNumber",
            "leagueStageId", "leagueStageLabel", "leagueStageNumber",
            "roundSource", "roundLabel",
        ):
            if key in detail:
                detail.pop(key, None)
                non_league_cleaned += 1
        if as_int(detail.get("week")) <= 0:
            detail.pop("week", None)
        detail["roundType"] = str(detail.get("matchType") or "other")

    return {
        "leagueMatches": len(league),
        "assigned": assigned,
        "exactFixtureWeeks": exact,
        "fallbackWeeks": fallback,
        "fallbackMatchIds": missing_ids[:50],
        "stages": stages,
        "nonLeagueFieldsCleaned": non_league_cleaned,
    }


def detail_index(detail: dict[str, Any]) -> dict[str, Any]:
    index = index_from_detail(detail)
    for key in (
        "stageWeek", "stageId", "stageNumber", "roundType", "roundLabel",
        "roundSource", "leagueStageId", "leagueStageLabel", "leagueStageNumber",
    ):
        value = detail.get(key)
        if value not in (None, "", {}, []):
            index[key] = value
    return index


def _player_identity(name: Any, person_id: Any) -> str:
    pid = str(person_id or "").strip()
    return f"id:{pid}" if pid else f"name:{norm(name)}"


def _event_kind(item: dict[str, Any]) -> str:
    return norm(item.get("type") or item.get("card") or item.get("goalType") or "")


def _is_penalty(item: dict[str, Any]) -> bool:
    return "penalt" in norm(" ".join(str(item.get(k) or "") for k in ("type", "goalType", "raw")))


def _is_own_goal(item: dict[str, Any]) -> bool:
    text = norm(" ".join(str(item.get(k) or "") for k in ("type", "goalType", "raw")))
    return "kendi kale" in text or "own goal" in text


def _ensure_player(store: dict[str, dict[str, Any]], name: Any, person_id: Any = "", team: Any = "") -> dict[str, Any] | None:
    clean_name = clean_person_name(name)
    if not clean_name:
        return None
    key = _player_identity(clean_name, person_id)
    item = store.setdefault(key, {
        "id": str(person_id or key),
        "name": clean_name,
        "tffPersonId": str(person_id or ""),
        "teams": set(),
        "roles": set(),
        "seasons": set(),
        "match_ids": set(),
        "appearance_ids": set(),
        "start_ids": set(),
        "bench_ids": set(),
        "sub_in_ids": set(),
        "sub_out_ids": set(),
        "goals": 0,
        "penalty_goals": 0,
        "own_goals": 0,
        "yellow_cards": 0,
        "red_cards": 0,
        "second_yellows": 0,
        "recent": [],
    })
    if team:
        item["teams"].add(str(team))
    return item


def rebuild_players_index(data_root: Path) -> list[dict[str, Any]]:
    players: dict[str, dict[str, Any]] = {}
    for index_path in sorted((data_root / "seasons").glob("*/matches_index.json")):
        season = index_path.parent.name
        for match in as_list(read_json(index_path, [])):
            if not isinstance(match, dict):
                continue
            match_id = str(match.get("id") or "")
            detail = read_json(index_path.parent / "matches" / f"{match_id}.json", {}) or {}
            if not isinstance(detail, dict):
                continue
            match_date = str(detail.get("date") or "")
            in_match: set[str] = set()
            lineups = detail.get("lineups") if isinstance(detail.get("lineups"), dict) else {}
            for side in ("home", "away"):
                block = lineups.get(side) if isinstance(lineups.get(side), dict) else {}
                team = str(block.get("team") or "")
                for collection, role in (("starting11", "starting11"), ("substitutes", "substitute")):
                    for person in as_list(block.get(collection)):
                        if not isinstance(person, dict):
                            continue
                        player = _ensure_player(players, person.get("name"), person.get("tffPersonId"), team)
                        if not player:
                            continue
                        key = _player_identity(player["name"], player["tffPersonId"])
                        in_match.add(key)
                        player["roles"].add(role)
                        player["match_ids"].add(match_id)
                        player["seasons"].add(season)
                        if role == "starting11":
                            player["start_ids"].add(match_id)
                            player["appearance_ids"].add(match_id)
                        else:
                            player["bench_ids"].add(match_id)
                        player["recent"].append((match_date, match_id))

            for substitution in as_list(detail.get("substitutions")):
                if not isinstance(substitution, dict):
                    continue
                team = substitution.get("team") or ""
                for fields, bucket, role in (
                    (("playerIn", "player_in"), "sub_in_ids", "substitution_in"),
                    (("playerOut", "player_out"), "sub_out_ids", "substitution_out"),
                ):
                    name = next((substitution.get(field) for field in fields if substitution.get(field)), "")
                    pid_field = "playerInTffPersonId" if bucket == "sub_in_ids" else "playerOutTffPersonId"
                    player = _ensure_player(players, name, substitution.get(pid_field), team)
                    if not player:
                        continue
                    key = _player_identity(player["name"], player["tffPersonId"])
                    in_match.add(key)
                    player["roles"].add(role)
                    player[bucket].add(match_id)
                    player["match_ids"].add(match_id)
                    player["seasons"].add(season)
                    if bucket == "sub_in_ids":
                        player["appearance_ids"].add(match_id)
                    player["recent"].append((match_date, match_id))

            event_collections = (
                ("goals", "goal"),
                ("cards", "card"),
            )
            for collection, default_kind in event_collections:
                for event in as_list(detail.get(collection)):
                    if not isinstance(event, dict):
                        continue
                    name = event.get("player") or event.get("scorer")
                    player = _ensure_player(players, name, event.get("tffPersonId"), event.get("team"))
                    if not player:
                        continue
                    key = _player_identity(player["name"], player["tffPersonId"])
                    in_match.add(key)
                    player["match_ids"].add(match_id)
                    player["seasons"].add(season)
                    player["appearance_ids"].add(match_id)
                    player["recent"].append((match_date, match_id))
                    kind = _event_kind(event) or default_kind
                    if collection == "goals":
                        player["goals"] += 1
                        player["penalty_goals"] += int(_is_penalty(event))
                        player["own_goals"] += int(_is_own_goal(event))
                    elif "second yellow" in kind or "ikinci sari" in kind:
                        player["second_yellows"] += 1
                        player["red_cards"] += 1
                    elif "red" in kind or "kirmizi" in kind:
                        player["red_cards"] += 1
                    else:
                        player["yellow_cards"] += 1

            # Olaylarda olup kadro/özel listelerde görünmeyen kişileri de koru.
            for event in as_list(detail.get("events")):
                if not isinstance(event, dict):
                    continue
                name = event.get("player") or event.get("scorer")
                player = _ensure_player(players, name, event.get("tffPersonId"), event.get("team"))
                if not player:
                    continue
                key = _player_identity(player["name"], player["tffPersonId"])
                if key not in in_match:
                    player["match_ids"].add(match_id)
                    player["seasons"].add(season)
                    player["appearance_ids"].add(match_id)
                    player["recent"].append((match_date, match_id))

    output: list[dict[str, Any]] = []
    for value in players.values():
        match_ids = sorted(value["match_ids"], key=lambda item: as_int(item))
        recent = [mid for _date, mid in sorted(set(value["recent"]), reverse=True)[:20]]
        appearances = len(value["appearance_ids"])
        starts = len(value["start_ids"])
        bench = len(value["bench_ids"])
        sub_in = len(value["sub_in_ids"])
        sub_out = len(value["sub_out_ids"])
        yellow = int(value["yellow_cards"])
        red = int(value["red_cards"])
        own = int(value["own_goals"])
        row = {
            "id": value["id"],
            "name": value["name"],
            "player_name": value["name"],
            "normalized_name": norm(value["name"]),
            "tffPersonId": value["tffPersonId"],
            "tffPlayerId": value["tffPersonId"],
            "teams": sorted(value["teams"], key=norm),
            "roles": sorted(value["roles"]),
            "seasons": sorted(value["seasons"], reverse=True),
            "matchCount": len(match_ids),
            "appearances": appearances,
            "starts": starts,
            "bench": bench,
            "subs": bench,
            "substituted_in": sub_in,
            "substituted_out": sub_out,
            "subbedIn": sub_in,
            "subbedOut": sub_out,
            "goals": int(value["goals"]),
            "penalty_goals": int(value["penalty_goals"]),
            "own_goals": own,
            "ownGoals": own,
            "yellow_cards": yellow,
            "red_cards": red,
            "second_yellows": int(value["second_yellows"]),
            "yellowCards": yellow,
            "redCards": red,
            "cards": yellow + red,
            "match_ids": match_ids,
            "matchIds": match_ids,
            "recentMatches": recent,
            "dataQuality": {
                "level": "derived_from_verified_tff_matches",
                "notes": [],
            },
        }
        output.append(row)
    output.sort(key=lambda item: norm(item.get("name")))
    write_json(data_root / "players_index.json", output)
    return output


def rebuild_opponents_index(data_root: Path) -> list[dict[str, Any]]:
    opponents: dict[str, dict[str, Any]] = {}
    for index_path in sorted((data_root / "seasons").glob("*/matches_index.json")):
        season = index_path.parent.name
        for match in as_list(read_json(index_path, [])):
            if not isinstance(match, dict):
                continue
            balkes = match.get("balkes") if isinstance(match.get("balkes"), dict) else {}
            name = str(balkes.get("opponent") or "").strip()
            if not name:
                continue
            key = norm(name)
            item = opponents.setdefault(key, {
                "name": name,
                "opponent": name,
                "normalized_opponent": key,
                "matches": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "goalsFor": 0,
                "goalsAgainst": 0,
                "homeMatches": 0,
                "awayMatches": 0,
                "leagueMatches": 0,
                "cupMatches": 0,
                "playoffMatches": 0,
                "seasons": set(),
                "matchIds": [],
                "lastMatchDate": "",
            })
            item["matches"] += 1
            result = str(balkes.get("result") or "")
            item["wins"] += int(result == "W")
            item["draws"] += int(result == "D")
            item["losses"] += int(result == "L")
            item["goalsFor"] += as_int(balkes.get("goalsFor"))
            item["goalsAgainst"] += as_int(balkes.get("goalsAgainst"))
            item["homeMatches"] += int(bool(balkes.get("isHome")))
            item["awayMatches"] += int(bool(balkes.get("isAway")) or not bool(balkes.get("isHome")))
            match_type = str(match.get("matchType") or "league")
            item["leagueMatches"] += int(match_type == "league")
            item["cupMatches"] += int(match_type == "cup")
            item["playoffMatches"] += int(match_type == "playoff")
            item["seasons"].add(season)
            item["matchIds"].append(str(match.get("id") or ""))
            item["lastMatchDate"] = max(item["lastMatchDate"], str(match.get("date") or ""))

    output: list[dict[str, Any]] = []
    for item in opponents.values():
        item["seasons"] = sorted(item["seasons"], reverse=True)
        item["matchIds"] = sorted(set(item["matchIds"]), key=as_int)
        item["match_ids"] = item["matchIds"]
        item["goals_for"] = item["goalsFor"]
        item["goals_against"] = item["goalsAgainst"]
        item["home_matches"] = item["homeMatches"]
        item["away_matches"] = item["awayMatches"]
        item["league_matches"] = item["leagueMatches"]
        item["cup_matches"] = item["cupMatches"]
        item["playoff_matches"] = item["playoffMatches"]
        output.append(item)
    output.sort(key=lambda item: norm(item["name"]))
    write_json(data_root / "opponents_index.json", output)
    return output


def iter_person_names(detail: dict[str, Any]) -> Iterable[str]:
    lineups = detail.get("lineups") if isinstance(detail.get("lineups"), dict) else {}
    for side in ("home", "away"):
        block = lineups.get(side) if isinstance(lineups.get(side), dict) else {}
        for collection in ("starting11", "substitutes", "technicalStaff"):
            for person in as_list(block.get(collection)):
                if isinstance(person, dict) and person.get("name"):
                    yield str(person["name"])
    for collection in ("players", "events", "goals", "goalScorers", "cards", "substitutions"):
        for item in as_list(detail.get(collection)):
            if not isinstance(item, dict):
                continue
            for key in ("name", "player", "scorer", "playerIn", "playerOut", "player_in", "player_out"):
                if item.get(key):
                    yield str(item[key])


def validate_repair(data_root: Path, players: list[dict[str, Any]], season_reports: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    league_matches = non_league_matches = dirty_names = 0
    for report in season_reports:
        if report.get("fallbackWeeks"):
            errors.append(
                f"{report.get('season')}: {report.get('fallbackWeeks')} lig maçında doğrulanmış fikstür haftası yok."
            )
    for detail_path in sorted((data_root / "seasons").glob("*/matches/*.json")):
        detail = read_json(detail_path, {}) or {}
        if not isinstance(detail, dict):
            errors.append(f"JSON okunamadı: {detail_path}")
            continue
        match_type = str(detail.get("matchType") or "league")
        if match_type == "league":
            league_matches += 1
            for key in ("week", "standingsWeek", "stageWeek"):
                if as_int(detail.get(key)) <= 0:
                    errors.append(f"{detail.get('season')}/{detail.get('id')}: {key} eksik.")
        else:
            non_league_matches += 1
            if as_int(detail.get("standingsWeek")) > 0:
                errors.append(f"{detail.get('season')}/{detail.get('id')}: lig dışı maça standingsWeek yazılmış.")
        for name in iter_person_names(detail):
            if DIRTY_PERSON_RE.search(name):
                dirty_names += 1
                if dirty_names <= 20:
                    errors.append(f"Kirli kişi adı: {detail.get('season')}/{detail.get('id')} -> {name}")

    required = {
        "player_name", "normalized_name", "tffPlayerId", "appearances", "starts",
        "bench", "substituted_in", "substituted_out", "goals", "penalty_goals",
        "own_goals", "yellow_cards", "red_cards", "second_yellows", "match_ids",
        "subbedIn", "subbedOut", "yellowCards", "redCards", "recentMatches",
    }
    incompatible = 0
    for player in players:
        missing = sorted(required - set(player))
        if missing:
            incompatible += 1
            if incompatible <= 20:
                errors.append(f"Oyuncu uyumluluk alanı eksik: {player.get('name')} -> {', '.join(missing)}")
        if DIRTY_PERSON_RE.search(str(player.get("name") or "")):
            dirty_names += 1
            errors.append(f"Oyuncu indeksinde kirli ad: {player.get('name')}")

    return {
        "generatedAt": now(),
        "status": "ok" if not errors else "error",
        "leagueMatches": league_matches,
        "nonLeagueMatches": non_league_matches,
        "players": len(players),
        "dirtyPersonNames": dirty_names,
        "incompatiblePlayers": incompatible,
        "errors": errors,
        "warnings": warnings,
    }


def registry_by_season(path: Path) -> dict[str, dict[str, Any]]:
    registry = read_json(path, {}) or {}
    return {
        str(item.get("season")): item
        for item in as_list(registry.get("seasons"))
        if isinstance(item, dict) and item.get("season")
    }


def repair_export(data_root: Path, registry_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = registry_by_season(registry_path)
    season_reports: list[dict[str, Any]] = []
    total_people = total_details = 0

    for season_dir in sorted((data_root / "seasons").glob("*")):
        if not season_dir.is_dir():
            continue
        details: list[dict[str, Any]] = []
        detail_paths: dict[str, Path] = {}
        for path in sorted((season_dir / "matches").glob("*.json"), key=lambda p: as_int(p.stem)):
            detail = read_json(path, {}) or {}
            if not isinstance(detail, dict):
                continue
            total_people += repair_detail_people(detail)
            details.append(detail)
            detail_paths[str(detail.get("id") or path.stem)] = path
        if not details:
            continue
        snapshots = as_list(read_json(season_dir / "standings_by_week.json", []))
        round_report = assign_league_rounds(details, registry.get(season_dir.name, {}), snapshots)
        round_report["season"] = season_dir.name
        round_report["details"] = len(details)
        season_reports.append(round_report)
        total_details += len(details)
        for detail in details:
            path = detail_paths.get(str(detail.get("id") or ""))
            if path:
                write_json(path, detail)
        write_json(season_dir / "matches_index.json", [
            detail_index(detail)
            for detail in sorted(details, key=lambda item: (str(item.get("date") or ""), as_int(item.get("id"))))
        ])

    players = rebuild_players_index(data_root)
    opponents = rebuild_opponents_index(data_root)
    report = {
        "generatedAt": now(),
        "status": "ok",
        "dataRoot": str(data_root),
        "registry": str(registry_path),
        "detailsProcessed": total_details,
        "personFieldsCleaned": total_people,
        "playersIndexed": len(players),
        "opponentsIndexed": len(opponents),
        "leagueMatches": sum(as_int(item.get("leagueMatches")) for item in season_reports),
        "exactFixtureWeeks": sum(as_int(item.get("exactFixtureWeeks")) for item in season_reports),
        "fallbackWeeks": sum(as_int(item.get("fallbackWeeks")) for item in season_reports),
        "seasons": season_reports,
    }
    validation = validate_repair(data_root, players, season_reports)
    if validation["status"] != "ok":
        report["status"] = "error"
    return report, validation


def main() -> int:
    parser = argparse.ArgumentParser(description="TFF JSON çıktısını onarır ve Android uyumluluğunu doğrular")
    parser.add_argument("--data-root", default="generated/tff-data")
    parser.add_argument("--registry", default="tools/tff/balkes_tff_seed_registry.json")
    parser.add_argument("--report", default="generated/tff-data/reports/repair_export.json")
    parser.add_argument("--validation-report", default="generated/tff-data/reports/repair_validation.json")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    report, validation = repair_export(data_root, Path(args.registry))
    write_json(Path(args.report), report)
    write_json(Path(args.validation_report), validation)
    print(
        "TFF çıktı onarımı: "
        f"detay={report['detailsProcessed']} "
        f"lig={report['leagueMatches']} "
        f"gerçekHafta={report['exactFixtureWeeks']} "
        f"temizAlan={report['personFieldsCleaned']} "
        f"oyuncu={report['playersIndexed']} "
        f"durum={validation['status']}",
        flush=True,
    )
    return 0 if validation["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
