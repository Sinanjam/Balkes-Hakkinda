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
