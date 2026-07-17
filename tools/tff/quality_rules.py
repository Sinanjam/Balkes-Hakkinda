#!/usr/bin/env python3
"""TFF doğrulama ve tamamlanma kapılarının ortak kalite kuralları."""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable


def as_match_date(value: Any) -> date | None:
    """TFF tarih alanını güvenli biçimde ISO güne çevirir."""
    raw = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def standings_not_yet_expected(
    details: Iterable[dict[str, Any]],
    *,
    today: date | None = None,
) -> bool:
    """Lig başlamadıysa boş puan tablosunun gerçek bir eksik olmadığını bildirir.

    Kural yalnızca en az bir lig fikstürü varsa, hiçbir lig maçı oynanmadıysa ve
    bütün lig maçları bugün ya da gelecekteyse geçerlidir. Böylece geçmiş sezon
    verisindeki bozuk/oynanmamış kayıtlar yanlışlıkla kabul edilmez.
    """
    league = [
        detail for detail in details
        if str(detail.get("matchType") or "league") == "league"
    ]
    if not league:
        return False
    if any(
        isinstance(detail.get("score"), dict) and detail["score"].get("played")
        for detail in league
    ):
        return False

    current_day = today or date.today()
    dates = [as_match_date(detail.get("date")) for detail in league]
    return all(match_day is not None and match_day >= current_day for match_day in dates)


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def played_balkes_totals(
    details: Iterable[dict[str, Any]],
    match_types: set[str],
) -> dict[str, int]:
    """Seçilen müsabaka türlerindeki oynanmış Balıkesirspor toplamlarını verir."""
    totals = {
        "played": 0,
        "won": 0,
        "drawn": 0,
        "lost": 0,
        "goalsFor": 0,
        "goalsAgainst": 0,
    }
    for detail in details:
        match_type = str(detail.get("matchType") or "league")
        score = detail.get("score") if isinstance(detail.get("score"), dict) else {}
        if match_type not in match_types or not score.get("played"):
            continue
        balkes = detail.get("balkes") if isinstance(detail.get("balkes"), dict) else {}
        totals["played"] += 1
        result = str(balkes.get("result") or "")
        totals["won"] += int(result == "W")
        totals["drawn"] += int(result == "D")
        totals["lost"] += int(result == "L")
        totals["goalsFor"] += as_int(balkes.get("goalsFor"))
        totals["goalsAgainst"] += as_int(balkes.get("goalsAgainst"))
    totals["goalDifference"] = totals["goalsFor"] - totals["goalsAgainst"]
    totals["rawPoints"] = totals["won"] * 3 + totals["drawn"]
    return totals


def official_standings_scope(
    details: Iterable[dict[str, Any]],
    standings_row: dict[str, Any],
) -> dict[str, Any]:
    """Resmi tablonun yalnız ligi mi, lig+play-off'u mu kapsadığını saptar.

    Bazı TFF sezonlarında grup tablosu play-off haftalarıyla devam eder. Tür
    ayrımını yalnız maç sayısı ve iki gol toplamı birlikte birebir uyuşursa
    kabul ederiz; böylece gerçek veri farkları yanlışlıkla örtülmez.
    """
    detail_list = list(details)
    league = played_balkes_totals(detail_list, {"league"})
    candidates = [(["league"], league)]
    league_and_playoff = played_balkes_totals(detail_list, {"league", "playoff"})
    if league_and_playoff["played"] > league["played"]:
        candidates.append((["league", "playoff"], league_and_playoff))

    expected = {
        "played": as_int(standings_row.get("played")),
        "goalsFor": as_int(standings_row.get("goalsFor")),
        "goalsAgainst": as_int(standings_row.get("goalsAgainst")),
    }
    for match_types, totals in candidates:
        if all(totals[key] == expected[key] for key in expected):
            return {
                "exact": True,
                "matchTypes": match_types,
                "totals": totals,
            }
    return {
        "exact": False,
        "matchTypes": ["league"],
        "totals": league,
    }
