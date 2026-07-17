#!/usr/bin/env python3
"""Eski TFF arşivindeki aşama adaylarını güvenle seçen saf kurallar."""
from __future__ import annotations

import re
from typing import Any


def is_direct_numbered_group(stage: dict[str, Any]) -> bool:
    """``03`` / ``3. Grup`` gibi tam sezon grup etiketlerini tanır."""
    label = str(stage.get("label") or "").casefold().strip()
    label = re.sub(r"[._-]+", " ", label)
    label = re.sub(r"\s+", " ", label)
    return bool(re.fullmatch(r"(?:grup )?\d+(?: grup)?", label))


def reconciled_stage_max_week(
    stage: dict[str, Any],
    incremental_matches: int,
    direct_fixture_max_week: int = 0,
) -> int:
    """Bir arşiv aşamasının gerçek hafta tavanını güvenli biçimde seçer.

    Eski TFF sayfalarında aynı kulüp adı iki farklı takım kimliği için
    görünebildiğinden yalnız satır sayısına bakmak tek sayılı takım sonucu
    üretebilir. Doğrudan numaralı tam sezon grubunda kulüp fikstürünün açık
    hafta numarası varsa bu, takım sayısı tahmininden daha güçlü kanıttır.
    """
    incremental = max(0, int(incremental_matches or 0))
    fixture_week = max(0, int(direct_fixture_max_week or 0))
    if (
        incremental
        and fixture_week >= incremental
        and is_direct_numbered_group(stage)
    ):
        return fixture_week
    team_count = max(0, int(stage.get("teamCount") or 0))
    return incremental + 2 if team_count % 2 == 1 and incremental else incremental


def select_reconciled_stage_set(
    exact: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Fikstür toplamına uyan adaylar içinden gerçek kronolojiyi seçer.

    Aynı sayfada doğrudan numaralı grup bütün sezonu karşılıyorsa onu tercih
    ederiz. Aksi hâlde Kademe/Klasman gibi gerçek çok aşamalı yapıda daha fazla
    aşamayı koruyan eski davranış sürer.
    """
    if not exact:
        return []
    direct = [
        values for values in exact
        if len(values) == 1 and is_direct_numbered_group(values[0])
    ]
    candidates = direct or exact
    return max(
        candidates,
        key=lambda values: (
            len(values),
            sum(int(value.get("maxWeek") or 0) for value in values),
        ),
    )
