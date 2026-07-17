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
    league = [detail for detail in details if detail.get("matchType") == "league"]
    if not league:
        return False
    if any((detail.get("score") or {}).get("played") for detail in league):
        return False

    current_day = today or date.today()
    dates = [as_match_date(detail.get("date")) for detail in league]
    return all(match_day is not None and match_day >= current_day for match_day in dates)
