#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Balkes Skor TFF Standings Builder

PC/local tool for weekly standings:
- tries official TFF weekly tables first;
- if weekly official table is unavailable, fetches all league match details and computes week-by-week tables;
- applies manual point penalties for computed tables;
- writes data/seasons/<season>/standings_by_week.json for the Android app;
- can commit and push generated files after a successful run.

Designed for NixOS + Fish, but only needs Python + bs4/lxml.
"""
from __future__ import annotations

import argparse
import html
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

try:
    from tff_factory import (
        clean_team,
        clean_text,
        date_in_season,
        decode_bytes,
        is_balkes,
        norm,
        parse_detail,
        parse_date_any,
        read_json,
        season_bounds,
        tff_url,
        write_json,
    )
except Exception as exc:  # pragma: no cover
    print(f"tff_factory import edilemedi: {exc}", file=sys.stderr)
    raise

from quality_rules import official_standings_scope, played_balkes_totals

TFF = os.environ.get("TFF_BASE_URL", "http://www.tff.org/Default.aspx")
DEFAULT_PENALTIES = "data/standings_penalties.json"
BUILDER_VERSION = "standings-builder-v7-archive-gap-recovery"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_int(value: Any) -> int | None:
    text = clean_text(value)
    text = text.replace("−", "-").replace("+", "")
    m = re.search(r"-?\d+", text)
    return int(m.group(0)) if m else None


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)[:160]


def fetch_url(url: str, path: Path, sleep_s: float = 0.8, force: bool = False) -> tuple[bool, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 200 and not force:
        return True, path.read_text(encoding="utf-8", errors="replace")
    last = ""
    for attempt in range(1, 3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 BalkesSkorStandingsBuilder/1.0",
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
            })
            with urllib.request.urlopen(req, timeout=18) as res:
                raw = res.read()
                content_type = res.headers.get("Content-Type", "")
            text = decode_bytes(raw, content_type)
            path.write_text(text, encoding="utf-8")
            if sleep_s:
                time.sleep(sleep_s)
            return True, text
        except Exception as exc:
            last = str(exc)
            time.sleep(min(1.0, max(0.2, sleep_s * attempt)))
    path.with_suffix(path.suffix + ".error.txt").write_text(last, encoding="utf-8")
    return False, ""


def soup(raw: str):
    if BeautifulSoup is None:
        return None
    return BeautifulSoup(raw, "lxml" if "lxml" in sys.modules else "html.parser")


def extract_match_ids(raw: str) -> list[str]:
    ids = set(re.findall(r"[?&]macId=(\d+)", raw, flags=re.I))
    return sorted(ids, key=lambda x: int(x))


def build_item_urls(item: dict[str, Any], week: int | None = None) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    plan = item.get("tffPlan") or {}
    page_id = str(item.get("targetPageID") or plan.get("pageID") or "").strip()
    group_id = str(item.get("targetGrupID") or plan.get("grupID") or "").strip()
    raw_targets = [u for u in item.get("targetUrls", []) or [] if isinstance(u, str) and u.strip()]

    bases: list[tuple[str, str]] = []
    if page_id:
        params: dict[str, Any] = {"pageID": page_id}
        if group_id:
            params["grupID"] = group_id
        bases.append((f"pageID_{page_id}_group_{group_id or 'none'}", TFF + "?" + urllib.parse.urlencode(params)))
    for u in raw_targets:
        u = u.replace("https://www.tff.org", "http://www.tff.org")
        label = "extra_" + hashlib.sha1(u.encode("utf-8")).hexdigest()[:10]
        bases.append((label, u.strip()))

    # Registry çoğu zaman aynı exact hedefi hem alanlarda hem targetUrls içinde
    # taşır. Aynı TFF sayfasını iki farklı cache adıyla indirmeyelim.
    unique_bases: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for label, url in bases:
        parsed = urllib.parse.urlparse(url)
        normalized = urllib.parse.urlunparse(
            parsed._replace(query=urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(parsed.query))))
        ).lower()
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        unique_bases.append((label, url))
    bases = unique_bases

    if week is None:
        return bases

    # Fast/default path: TFF league pages use `hafta` for weekly fixture/table views.
    # The v1 builder tried 5 different parameter names for every week, causing
    # 5x network requests. Fallback variants are handled by build_week_urls().
    return build_week_urls(bases, week, ["hafta"])


def build_week_urls(bases: list[tuple[str, str]], week: int, keys: list[str]) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for label, base in bases:
        parsed = urllib.parse.urlparse(base)
        qs = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        for key in keys:
            wqs = dict(qs)
            wqs[key] = str(week)
            url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(wqs)))
            urls.append((f"{label}_{key}_{week:02d}", url))
    return urls


def week_param_candidates(mode: str) -> list[str]:
    if mode == "fast":
        return ["hafta"]
    if mode == "wide":
        return ["hafta", "Hafta", "haftaNo", "haftaID", "week"]
    # smart: start narrow, expand only if the week produced no useful page.
    return ["hafta", "Hafta", "haftaNo", "haftaID", "week"]


def maybe_header_map(cells: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    aliases = {
        "rank": ["sira", "sıra", "#"],
        "team": ["takim", "takım", "kulup", "kulüp", "team"],
        "played": ["o", "om", "oyn", "oynanan", "mac", "maç"],
        "won": ["g", "galibiyet"],
        "drawn": ["b", "beraberlik"],
        "lost": ["m", "maglubiyet", "mağlubiyet"],
        "goalsFor": ["a", "atilan", "atılan", "attigi", "attığı", "gf"],
        "goalsAgainst": ["y", "yenilen", "yedigi", "yediği", "ga"],
        "goalDifference": ["av", "averaj", "+/-", "gd"],
        "points": ["p", "puan", "pts"],
    }
    for idx, cell in enumerate(cells):
        n = norm(cell)
        compact = re.sub(r"\s+", "", n)
        for key, names in aliases.items():
            if compact in [norm(x).replace(" ", "") for x in names] and key not in out:
                out[key] = idx
    return out


def parse_team_from_cells(cells: list[str], numeric_indexes: set[int]) -> tuple[int | None, str]:
    for i, c in enumerate(cells):
        if i in numeric_indexes:
            continue
        text = clean_text(c)
        if not text:
            continue
        n = norm(text)
        if n in {"takim", "takım", "kulup", "kulüp", "team"}:
            continue
        if re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", text):
            # Strip leading rank noise but keep team suffixes.
            text = re.sub(r"^\s*\d+\s*[.)-]?\s*", "", text).strip()
            if len(norm(text)) >= 3:
                return i, clean_team(text)
    return None, ""


def row_from_cells(cells: list[str], header: dict[str, int] | None = None) -> dict[str, Any] | None:
    cells = [clean_text(c) for c in cells if clean_text(c)]
    if len(cells) < 4:
        return None
    numeric: list[tuple[int, int]] = []
    for i, c in enumerate(cells):
        v = parse_int(c)
        if v is not None and re.fullmatch(r"[+−\-]?\d+", c.replace(" ", "")):
            numeric.append((i, v))
    numeric_indexes = {i for i, _ in numeric}

    if header and "team" in header and header["team"] < len(cells):
        team = clean_team(cells[header["team"]])
        if not team or not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", team):
            _, team = parse_team_from_cells(cells, numeric_indexes)
        row: dict[str, Any] = {"team": team}
        for key in ["rank", "played", "won", "drawn", "lost", "goalsFor", "goalsAgainst", "goalDifference", "points"]:
            idx = header.get(key)
            if idx is not None and idx < len(cells):
                row[key] = parse_int(cells[idx])
        if team and row.get("played") is not None and row.get("points") is not None:
            return normalize_standing_row(row)

    team_idx, team = parse_team_from_cells(cells, numeric_indexes)
    if not team or team_idx is None:
        return None
    nums_after = [v for i, v in numeric if i > team_idx]
    rank = None
    if numeric and numeric[0][0] < team_idx:
        rank = numeric[0][1]
    if len(nums_after) < 5:
        return None
    # Common table: O G B M A Y AV P. If AV omitted: O G B M A Y P.
    row = {"team": team, "rank": rank}
    row["played"] = nums_after[0]
    row["won"] = nums_after[1] if len(nums_after) > 1 else 0
    row["drawn"] = nums_after[2] if len(nums_after) > 2 else 0
    row["lost"] = nums_after[3] if len(nums_after) > 3 else 0
    row["goalsFor"] = nums_after[4] if len(nums_after) > 4 else 0
    row["goalsAgainst"] = nums_after[5] if len(nums_after) > 5 else 0
    if len(nums_after) >= 8:
        row["goalDifference"] = nums_after[6]
        row["points"] = nums_after[7]
    elif len(nums_after) >= 7:
        row["goalDifference"] = row["goalsFor"] - row["goalsAgainst"]
        row["points"] = nums_after[6]
    else:
        return None
    return normalize_standing_row(row)


def normalize_standing_row(row: dict[str, Any]) -> dict[str, Any] | None:
    team = clean_team(row.get("team", ""))
    if not team:
        return None
    played = int(row.get("played") or 0)
    won = int(row.get("won") or 0)
    drawn = int(row.get("drawn") or 0)
    lost = int(row.get("lost") or 0)
    gf = int(row.get("goalsFor") or 0)
    ga = int(row.get("goalsAgainst") or 0)
    gd = int(row.get("goalDifference") if row.get("goalDifference") is not None else gf - ga)
    points = int(row.get("points") or 0)
    if played == 0 and points == 0 and won == 0 and drawn == 0 and lost == 0:
        return None
    return {
        "rank": int(row.get("rank") or 0),
        "team": team,
        "played": played,
        "won": won,
        "drawn": drawn,
        "lost": lost,
        "goalsFor": gf,
        "goalsAgainst": ga,
        "goalDifference": gd,
        "points": points,
        "rawPoints": int(row.get("rawPoints") if row.get("rawPoints") is not None else points),
        "pointsDeducted": int(row.get("pointsDeducted") or 0),
        "penaltyNote": str(row.get("penaltyNote") or ""),
        "isBalkes": bool(is_balkes(team)),
    }



def valid_standing_row(row: dict[str, Any]) -> bool:
    """Reject bogus table fragments such as '1. Devre / 2. Devre'."""
    if not row:
        return False
    team = clean_team(row.get("team", ""))
    n = norm(team)
    bad_exact = {"devre", "1 devre", "2 devre", "ilk yari", "ikinci yari", "ic saha", "dis saha", "genel", "takim"}
    if not team or n in bad_exact or n.endswith(" devre"):
        return False
    if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", team):
        return False
    try:
        played = int(row.get("played") or 0)
        won = int(row.get("won") or 0)
        drawn = int(row.get("drawn") or 0)
        lost = int(row.get("lost") or 0)
        gf = int(row.get("goalsFor") or 0)
        ga = int(row.get("goalsAgainst") or 0)
        gd = int(row.get("goalDifference") if row.get("goalDifference") is not None else gf - ga)
        pts = int(row.get("points") or 0)
    except Exception:
        return False
    if played < 0 or played > 50 or won < 0 or drawn < 0 or lost < 0:
        return False
    if won + drawn + lost != played:
        return False
    if gf < 0 or ga < 0 or abs(gd - (gf - ga)) > 1:
        return False
    # A few sanctions/restorations are possible, but absurd values indicate a parsed header/fragment.
    if pts < -20 or pts > won * 3 + drawn + 15:
        return False
    return True


def clean_standings_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = [r for r in rows if valid_standing_row(r)]
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in cleaned:
        team_id = str(r.get("teamId") or "").strip()
        key = f"id:{team_id}" if team_id else f"name:{norm(r.get('team', ''))}"
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(r)
    for i, r in enumerate(out, 1):
        if not r.get("rank") or int(r.get("rank") or 0) <= 0:
            r["rank"] = i
        r["isBalkes"] = bool(is_balkes(r.get("team", "")))
    return out


def standings_rows_are_usable(rows: list[dict[str, Any]], require_balkes: bool = True) -> bool:
    rows = clean_standings_rows(rows)
    if len(rows) < 8:
        return False
    if require_balkes and not any(r.get("isBalkes") or is_balkes(r.get("team", "")) for r in rows):
        return False
    return True

def _standings_scopes_for_group(sp: Any, group_id: str) -> list[Any]:
    """Return only the archive module that owns ``group_id``.

    Historical TFF pages can render two independent standings modules in the
    same HTML document (for example Kademe and Klasman/Yukselme groups).  A
    page-wide table scan can therefore return Balikesirspor from the other
    module even when the requested group does not contain the club.
    """
    wanted = str(group_id or "").strip()
    if not wanted:
        return []
    scopes: list[Any] = []
    seen: set[int] = set()
    for anchor in sp.find_all("a", href=True):
        query = urllib.parse.parse_qs(
            urllib.parse.urlparse(html.unescape(str(anchor.get("href") or ""))).query
        )
        candidate = (query.get("grupID") or query.get("grupId") or [""])[0]
        if str(candidate) != wanted:
            continue
        container = anchor.find_parent(
            "div", id=re.compile(r"_ctnr_div$", re.I)
        )
        if container is None:
            continue
        marker = id(container)
        if marker not in seen:
            seen.add(marker)
            scopes.append(container)
    return scopes


def standing_team_id(tr: Any) -> str:
    """Puan tablosu satırındaki kalıcı TFF takım/kulüp kimliğini okur."""
    for anchor in tr.find_all("a", href=True):
        query = urllib.parse.parse_qs(
            urllib.parse.urlparse(html.unescape(str(anchor.get("href") or ""))).query
        )
        lowered = {str(key).casefold(): value for key, value in query.items()}
        for key in ("takimid", "kulupid", "teamid", "clubid"):
            value = (lowered.get(key) or [""])[0]
            if str(value).strip():
                return str(value).strip()
    return ""


def parse_official_standings(
    raw: str,
    group_id: str = "",
    module_id: str = "",
) -> list[dict[str, Any]]:
    sp = soup(raw)
    if not sp:
        return []
    scopes: list[Any] = []
    if module_id:
        module = sp.find(id=str(module_id))
        if module is None:
            return []
        scopes = [module]
    elif group_id:
        scopes = _standings_scopes_for_group(sp, group_id)
        # Modern league pages can expose one standings module without group
        # links. Their caller also verifies season and Balikesirspor rows. Old
        # multi-module archive pages are guarded by archive_group_is_selected.
    table_roots = scopes or [sp]
    candidates: list[list[dict[str, Any]]] = []
    tables: list[Any] = []
    seen_tables: set[int] = set()
    for root in table_roots:
        for table in root.find_all("table"):
            marker = id(table)
            if marker not in seen_tables:
                seen_tables.add(marker)
                tables.append(table)
    for table in tables:
        header: dict[str, int] | None = None
        rows: list[dict[str, Any]] = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if not cells:
                continue
            hm = maybe_header_map(cells)
            if len(hm) >= 3:
                header = hm
                continue
            row = row_from_cells(cells, header)
            if row:
                team_id = standing_team_id(tr)
                if team_id:
                    row["teamId"] = team_id
                rows.append(row)
        rows = clean_standings_rows(rows)
        if len(rows) >= 8:
            candidates.append(rows)
    if not candidates:
        return []
    # Prefer tables with Balkes and many rows.
    candidates.sort(key=lambda rows: (any(r.get("isBalkes") for r in rows), len(rows)), reverse=True)
    rows = clean_standings_rows(candidates[0])
    # Ensure rank order when missing.
    for i, r in enumerate(rows, 1):
        if not r.get("rank"):
            r["rank"] = i
    return rows


def standings_signature(rows: list[dict[str, Any]]) -> str:
    compact = [(
        str(r.get("teamId") or norm(r.get("team", ""))),
        r.get("played"),
        r.get("points"),
        r.get("goalDifference"),
    ) for r in rows]
    return hashlib.sha1(json.dumps(compact, sort_keys=True).encode("utf-8")).hexdigest()


def load_penalties(path: Path) -> dict[str, Any]:
    if path.exists():
        return read_json(path, {}) or {}
    obj = {
        "schemaVersion": 1,
        "updatedAt": now(),
        "notes": [
            "Computed standings apply these manual point corrections. Official TFF standings are assumed to already include official corrections.",
            "Use negative points for deductions, positive points for restorations/awards.",
            "Set effectiveWeek to the first week where the correction must appear. Omit or set 1 to apply from the start.",
        ],
        "seasons": {},
        "reviewedSeasons": {},
    }
    write_json(path, obj)
    return obj


def penalties_for_week(penalties: dict[str, Any], season: str, week: int) -> list[dict[str, Any]]:
    out = []
    for p in ((penalties.get("seasons") or {}).get(season) or []):
        try:
            eff = int(p.get("effectiveWeek") or 1)
        except Exception:
            eff = 1
        if week >= eff:
            out.append(p)
    return out


def apply_penalties(rows: list[dict[str, Any]], penalties: dict[str, Any], season: str, week: int) -> None:
    active = penalties_for_week(penalties, season, week)
    if not active:
        return
    for row in rows:
        row["rawPoints"] = int(row.get("points") or 0)
        row["pointsDeducted"] = 0
        row["penaltyNote"] = ""
        for p in active:
            if norm(p.get("team", "")) == norm(row.get("team", "")):
                delta = int(p.get("points") or 0)
                row["points"] = int(row.get("points") or 0) + delta
                row["pointsDeducted"] += delta
                note = clean_text(p.get("note", ""))
                if note:
                    row["penaltyNote"] = (row["penaltyNote"] + "; " + note).strip("; ")


def sort_standings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows.sort(key=lambda r: (
        -int(r.get("points") or 0),
        -int(r.get("goalDifference") or 0),
        -int(r.get("goalsFor") or 0),
        norm(r.get("team", "")),
    ))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["isBalkes"] = bool(is_balkes(r.get("team", "")))
    return rows


@dataclass
class TeamStats:
    team: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goalsFor: int = 0
    goalsAgainst: int = 0

    @property
    def points(self) -> int:
        return self.won * 3 + self.drawn

    @property
    def goalDifference(self) -> int:
        return self.goalsFor - self.goalsAgainst

    def row(self) -> dict[str, Any]:
        return {
            "team": self.team,
            "played": self.played,
            "won": self.won,
            "drawn": self.drawn,
            "lost": self.lost,
            "goalsFor": self.goalsFor,
            "goalsAgainst": self.goalsAgainst,
            "goalDifference": self.goalDifference,
            "points": self.points,
            "rawPoints": self.points,
            "pointsDeducted": 0,
            "penaltyNote": "",
            "isBalkes": bool(is_balkes(self.team)),
        }


def update_stats(stats: dict[str, TeamStats], match: dict[str, Any]) -> None:
    home = clean_team(match.get("homeTeam", ""))
    away = clean_team(match.get("awayTeam", ""))
    score = match.get("score") or {}
    if not home or not away or not score.get("played"):
        return
    h = score.get("home")
    a = score.get("away")
    if h is None or a is None:
        return
    h, a = int(h), int(a)
    sh = stats.setdefault(norm(home), TeamStats(home))
    sa = stats.setdefault(norm(away), TeamStats(away))
    sh.played += 1; sa.played += 1
    sh.goalsFor += h; sh.goalsAgainst += a
    sa.goalsFor += a; sa.goalsAgainst += h
    if h > a:
        sh.won += 1; sa.lost += 1
    elif h < a:
        sa.won += 1; sh.lost += 1
    else:
        sh.drawn += 1; sa.drawn += 1


def detail_is_league_match(detail: dict[str, Any], season: str, seed: dict[str, Any]) -> bool:
    if not detail.get("homeTeam") or not detail.get("awayTeam"):
        return False
    if not detail.get("date") or not date_in_season(detail.get("date"), season, seed):
        return False
    score = detail.get("score") or {}
    if not score.get("played"):
        return False
    match_type = detail.get("matchType") or detail.get("type") or ""
    if match_type and match_type != "league":
        return False
    comp = norm(detail.get("competition", ""))
    if "kupa" in comp or "ziraat" in comp or "play" in comp:
        return False
    return True



def parse_score_text(value: str) -> tuple[int | None, int | None, str, bool]:
    text = clean_text(value)
    # Avoid dates such as 07.09.2025; prefer explicit score separators.
    m = re.search(r"(?<!\d)(\d{1,2})\s*[-–]\s*(\d{1,2})(?!\d)", text)
    if not m:
        return None, None, "", False
    h, a = int(m.group(1)), int(m.group(2))
    return h, a, f"{h}-{a}", True


def cell_looks_like_team(value: str) -> bool:
    text = clean_text(value)
    if not text or len(norm(text)) < 3:
        return False
    n = norm(text)
    bad = {
        "detay", "mac detay", "maç detay", "hafta", "tarih", "saat", "skor", "sonuc", "sonuç",
        "stadyum", "stad", "hakem", "rapor", "puan durumu", "fikstur", "fikstür",
    }
    if n in bad or any(n.startswith(x + " ") for x in bad):
        return False
    if parse_date_any(text):
        return False
    if re.fullmatch(r"[+−\-]?\d+", text.replace(" ", "")):
        return False
    if re.fullmatch(r"\d{1,2}[:.]\d{2}", text):
        return False
    if re.search(r"\b\d{1,2}\s*[-–]\s*\d{1,2}\b", text):
        return False
    return bool(re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", text))


def html_unescape(value: Any) -> str:
    import html as _html
    return _html.unescape(str(value or ""))


def parse_listing_matches(raw: str, season: str, week: int, source_url: str, seed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Best-effort fixture parser for TFF weekly pages.

    It returns only conservative rows where macId + date in season + two team
    names + played score are visible in the listing. Those rows are enough to
    compute the table without opening each match detail page.
    """
    sp = soup(raw)
    if not sp:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for tr in sp.find_all("tr"):
        hrefs = [a.get("href") or "" for a in tr.find_all("a", href=True)]
        mids: list[str] = []
        for h in hrefs:
            mids.extend(re.findall(r"[?&]macId=(\d+)", html_unescape(h), flags=re.I))
        if not mids:
            continue
        mid = sorted(set(mids), key=lambda x: int(x))[0]
        cells = [clean_text(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        row_text = clean_text(tr.get_text(" ", strip=True))
        hscore, ascore, score_display, played = parse_score_text(row_text)
        if not played:
            continue
        match_date = parse_date_any(row_text)
        if not match_date or not date_in_season(match_date, season, seed):
            continue
        score_idx = None
        for i, c in enumerate(cells):
            if parse_score_text(c)[3]:
                score_idx = i
                break
        team_cells = [(i, clean_team(c)) for i, c in enumerate(cells) if cell_looks_like_team(c)]
        cleaned: list[tuple[int, str]] = []
        for i, t in team_cells:
            if len(t) > 80:
                continue
            if not cleaned or norm(cleaned[-1][1]) != norm(t):
                cleaned.append((i, t))
        home = away = ""
        if score_idx is not None:
            before = [(i, t) for i, t in cleaned if i < score_idx]
            after = [(i, t) for i, t in cleaned if i > score_idx]
            if before and after:
                home, away = before[-1][1], after[0][1]
        if not home or not away:
            sane = [t for _, t in cleaned if not norm(t).startswith("mac detay")]
            if len(sane) >= 2:
                home, away = sane[0], sane[1]
        if not home or not away or norm(home) == norm(away):
            continue
        detail = {
            "id": str(mid),
            "season": season,
            "competition": "Lig",
            "competitionType": "league",
            "competitionLabel": "Lig",
            "date": match_date,
            "time": "",
            "dateDisplay": match_date,
            "homeTeam": home,
            "awayTeam": away,
            "matchType": "league",
            "matchTypeLabel": "Lig",
            "type": "league",
            "typeLabel": "Lig",
            "score": {"home": hscore, "away": ascore, "display": score_display, "played": True},
            "source": {"name": "TFF", "url": source_url, "retrievedAt": now(), "sourceType": "official_tff_weekly_fixture_row"},
            "standingsWeek": week,
        }
        out[str(mid)] = finalize_listing_detail(detail)
    return out


def finalize_listing_detail(detail: dict[str, Any]) -> dict[str, Any]:
    home = clean_team(detail.get("homeTeam", ""))
    away = clean_team(detail.get("awayTeam", ""))
    score = detail.get("score") or {}
    h, a = score.get("home"), score.get("away")
    is_home = is_balkes(home)
    is_away = is_balkes(away)
    gf = h if is_home else a if is_away else None
    ga = a if is_home else h if is_away else None
    result = ""
    if gf is not None and ga is not None:
        result = "W" if int(gf) > int(ga) else "D" if int(gf) == int(ga) else "L"
    detail["homeTeam"] = home
    detail["awayTeam"] = away
    detail["balkes"] = {
        "isHome": bool(is_home),
        "isAway": bool(is_away),
        "opponent": away if is_home else home if is_away else "",
        "goalsFor": gf,
        "goalsAgainst": ga,
        "result": result,
    }
    return detail

def collect_week_fixtures(item: dict[str, Any], season: str, seed: dict[str, Any], raw_root: Path, sleep_s: float, force: bool, max_week: int, week_param_mode: str = "smart") -> tuple[dict[str, int], dict[str, dict[str, Any]], dict[str, Any]]:
    """Collect match IDs and conservative listing-level match rows.

    v1 tried 5 param names for every week. v2 learns the working param per base
    URL: `hafta` first, fallback variants only when a week returns no IDs/matches.
    """
    by_id: dict[str, int] = {}
    listing_details: dict[str, dict[str, Any]] = {}
    bases = build_item_urls(item, None)
    preferred_key: dict[str, str] = {}
    stats: dict[str, Any] = {"weeklyPagesFetched": 0, "fallbackParamAttempts": 0, "listingRowsParsed": 0, "workingWeekParams": {}}
    all_keys = week_param_candidates(week_param_mode)
    for week in range(1, max_week + 1):
        found_this_week: set[str] = set()
        parsed_this_week = 0
        for base_label, base_url in bases:
            keys = [preferred_key[base_label]] if base_label in preferred_key else ["hafta"]
            for pass_no in [1, 2]:
                useful = False
                for key in keys:
                    for label, url in build_week_urls([(base_label, base_url)], week, [key]):
                        ok, raw = fetch_url(url, raw_root / season / "weekly_pages" / f"{safe_name(label)}.html", sleep_s, force)
                        stats["weeklyPagesFetched"] += 1
                        if not ok:
                            continue
                        ids = set(extract_match_ids(raw))
                        parsed = parse_listing_matches(raw, season, week, url, seed)
                        if ids or parsed:
                            found_this_week.update(ids)
                            for mid, detail in parsed.items():
                                listing_details[mid] = detail
                                found_this_week.add(mid)
                            parsed_this_week += len(parsed)
                            preferred_key[base_label] = key
                            stats["workingWeekParams"][base_label] = key
                            useful = True
                            break
                    if useful:
                        break
                if useful or week_param_mode == "fast" or pass_no == 2:
                    break
                # Fallback only for empty/unrecognized week pages.
                keys = [k for k in all_keys if k != "hafta"]
                stats["fallbackParamAttempts"] += len(keys)
        for mid in found_this_week:
            by_id.setdefault(mid, week)
        stats["listingRowsParsed"] += parsed_this_week
        log(f"{season}: hafta {week}/{max_week} fikstürID={len(found_this_week)} listingRows={parsed_this_week} toplamID={len(by_id)}")
    if not by_id:
        for label, url in bases:
            ok, raw = fetch_url(url, raw_root / season / "weekly_pages" / f"{safe_name(label)}_base.html", sleep_s, force)
            stats["weeklyPagesFetched"] += 1
            if not ok:
                continue
            for mid in extract_match_ids(raw):
                by_id.setdefault(mid, 0)
    return by_id, listing_details, stats


def collect_week_match_ids(item: dict[str, Any], season: str, raw_root: Path, sleep_s: float, force: bool, max_week: int) -> dict[str, int]:
    by_id, _details, _stats = collect_week_fixtures(item, season, {}, raw_root, sleep_s, force, max_week, "smart")
    return by_id


def fetch_detail_worker(mid: str, season: str, raw_root: Path, sleep_s: float, force: bool, seed: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str]:
    url = tff_url(pageID=29, macId=mid)
    ok, raw = fetch_url(url, raw_root / season / "match_details" / f"{mid}.html", sleep_s, force)
    if not ok:
        return mid, None, "fetch_failed"
    try:
        detail = parse_detail(mid, raw, season, url, seed)
    except Exception as exc:
        return mid, None, f"parse_error:{exc}"
    if not detail_is_league_match(detail, season, seed):
        return mid, None, "not_league_or_invalid"
    return mid, detail, "ok"


def fetch_full_league_matches(item: dict[str, Any], season: str, seed: dict[str, Any], raw_root: Path, sleep_s: float, force: bool, max_week: int, probe_limit: int, workers: int = 4, detail_fetch_mode: str = "missing", week_param_mode: str = "smart") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    week_by_id, listing_details, stats = collect_week_fixtures(item, season, seed, raw_root, sleep_s, force, max_week, week_param_mode)
    mids = sorted(week_by_id.keys(), key=lambda x: int(x))
    if probe_limit > 0:
        mids = mids[:probe_limit]
    details_by_id: dict[str, dict[str, Any]] = {}
    if detail_fetch_mode != "all":
        for mid in mids:
            d = listing_details.get(mid)
            if d and detail_is_league_match(d, season, seed):
                details_by_id[mid] = d
    if detail_fetch_mode == "none":
        to_fetch: list[str] = []
    elif detail_fetch_mode == "all":
        to_fetch = mids
    else:
        to_fetch = [mid for mid in mids if mid not in details_by_id]
    stats["detailCandidates"] = len(mids)
    stats["detailFetchNeeded"] = len(to_fetch)
    stats["listingDetailsUsed"] = len(details_by_id)
    rejected: dict[str, int] = {}
    if to_fetch:
        log(f"{season}: detay fetch gerekli={len(to_fetch)} workers={workers} mode={detail_fetch_mode}")
    if workers <= 1:
        iterator = (fetch_detail_worker(mid, season, raw_root, sleep_s, force, seed) for mid in to_fetch)
        for idx, (mid, detail, reason) in enumerate(iterator, 1):
            if detail:
                detail["standingsWeek"] = int(week_by_id.get(mid) or 0)
                details_by_id[mid] = detail
            else:
                rejected[reason] = rejected.get(reason, 0) + 1
            if idx % 50 == 0 or idx == len(to_fetch):
                log(f"{season}: detay {idx}/{len(to_fetch)} ligMaçı={len(details_by_id)}")
    else:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = {ex.submit(fetch_detail_worker, mid, season, raw_root, sleep_s, force, seed): mid for mid in to_fetch}
            for idx, fut in enumerate(as_completed(futs), 1):
                mid, detail, reason = fut.result()
                if detail:
                    detail["standingsWeek"] = int(week_by_id.get(mid) or 0)
                    details_by_id[mid] = detail
                else:
                    rejected[reason] = rejected.get(reason, 0) + 1
                if idx % 50 == 0 or idx == len(to_fetch):
                    log(f"{season}: detay {idx}/{len(to_fetch)} ligMaçı={len(details_by_id)}")
    details = list(details_by_id.values())
    # If week is unknown, assign by date order roughly using match batches per round.
    if details and all(int(d.get("standingsWeek") or 0) == 0 for d in details):
        teams = sorted({norm(d["homeTeam"]) for d in details} | {norm(d["awayTeam"]) for d in details})
        per_round = max(1, len(teams) // 2)
        details.sort(key=lambda d: (d.get("date") or "", int(d.get("id") or 0)))
        for i, d in enumerate(details):
            d["standingsWeek"] = min(max_week, i // per_round + 1)
    stats["detailsRejected"] = rejected
    return details, stats


def compute_weekly_standings(matches: list[dict[str, Any]], season: str, max_week: int, penalties: dict[str, Any]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    stats: dict[str, TeamStats] = {}
    by_week: dict[int, list[dict[str, Any]]] = defaultdict(list)
    # Initialize every team before week 1 so bye weeks / not-yet-played teams
    # still appear with 0 matches instead of popping into the table later.
    for m in matches:
        for side in ["homeTeam", "awayTeam"]:
            team = clean_team(m.get(side, ""))
            if team:
                stats.setdefault(norm(team), TeamStats(team))
    for m in matches:
        week = int(m.get("standingsWeek") or 0)
        if week <= 0:
            continue
        by_week[min(week, max_week)].append(m)
    for week in range(1, max_week + 1):
        for m in sorted(by_week.get(week, []), key=lambda d: (d.get("date") or "", int(d.get("id") or 0))):
            update_stats(stats, m)
        rows = [s.row() for s in stats.values()]
        apply_penalties(rows, penalties, season, week)
        rows = sort_standings(rows)
        snapshots.append({
            "week": week,
            "source": "computed_from_tff_results",
            "generatedAt": now(),
            "builderVersion": BUILDER_VERSION,
            "standings": rows,
            "warnings": ["Sıralama puan, averaj, atılan gol ve takım adına göre hesaplandı; TFF özel ikili averaj kuralları ayrıca doğrulanmalıdır."],
        })
    return snapshots


def fetch_official_week(item: dict[str, Any], season: str, raw_root: Path,
                        sleep_s: float, force: bool, week: int) -> tuple[int, dict[str, Any] | None]:
    best: list[dict[str, Any]] = []
    best_url = ""
    for label, url in build_item_urls(item, week):
        ok, raw = fetch_url(
            url,
            raw_root / season / "official_tables" / f"{safe_name(label)}.html",
            sleep_s,
            force,
        )
        if not ok:
            continue
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        group_id = str(
            (query.get("grupID") or query.get("grupId") or [
                item.get("targetGrupID") or ""
            ])[0]
        )
        rows = clean_standings_rows(parse_official_standings(
            raw,
            group_id,
            str(item.get("targetModuleID") or ""),
        ))
        if standings_rows_are_usable(rows, require_balkes=True) and (
            not best or len(rows) > len(best) or any(r.get("isBalkes") for r in rows)
        ):
            best = rows
            best_url = url
    if best:
        best = clean_standings_rows(best)
        for i, row in enumerate(best, 1):
            if not row.get("rank"):
                row["rank"] = i
            row["isBalkes"] = bool(is_balkes(row.get("team", "")))
        return week, {
            "week": week,
            "source": "official_tff_weekly_table",
            "generatedAt": now(),
            "builderVersion": BUILDER_VERSION,
            "sourceUrl": best_url,
            "standings": best,
            "warnings": [],
        }
    return week, None


def try_official_weekly(item: dict[str, Any], season: str, raw_root: Path,
                        sleep_s: float, force: bool, max_week: int,
                        workers: int = 4) -> list[dict[str, Any]]:
    snapshots_by_week: dict[int, dict[str, Any]] = {}
    worker_count = max(1, min(int(workers), max_week))
    if worker_count == 1:
        iterator = (
            fetch_official_week(item, season, raw_root, sleep_s, force, week)
            for week in range(1, max_week + 1)
        )
        for completed, (week, snapshot) in enumerate(iterator, 1):
            if snapshot:
                snapshots_by_week[week] = snapshot
            log(f"{season}: resmi hafta {completed}/{max_week} tamamlandı")
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    fetch_official_week, item, season, raw_root,
                    sleep_s, force, week,
                ): week
                for week in range(1, max_week + 1)
            }
            for completed, future in enumerate(as_completed(futures), 1):
                week, snapshot = future.result()
                if snapshot:
                    snapshots_by_week[week] = snapshot
                if completed % 5 == 0 or completed == max_week:
                    log(
                        f"{season}: resmi haftalar {completed}/{max_week}, "
                        f"tablo={len(snapshots_by_week)}, workers={worker_count}"
                    )

    # Eski TFF arşivi eşzamanlı isteklerin bir bölümünde geçerli HTTP cevabı
    # içinde boş/varsayılan modül döndürebiliyor. Kısmen başarılı bir sezonun
    # eksik haftalarını bir kez seri ve zorunlu taze istekle toparla. Bu geçiş
    # yalnız resmi tabloyu yeniden okur; sentetik veri veya ileri taşıma yapmaz.
    missing = [week for week in range(1, max_week + 1) if week not in snapshots_by_week]
    if missing and len(snapshots_by_week) >= max(2, max_week // 3):
        log(
            f"{season}: eksik resmi haftalar seri kurtarılıyor: "
            + ",".join(map(str, missing))
        )
        recovered = 0
        for week in missing:
            _week, snapshot = fetch_official_week(
                item,
                season,
                raw_root,
                max(sleep_s, 0.35),
                True,
                week,
            )
            if not snapshot:
                continue
            snapshot.setdefault("warnings", []).append(
                "Paralel TFF isteğinde eksik kalan hafta seri resmi istekle yeniden alındı."
            )
            snapshots_by_week[week] = snapshot
            recovered += 1
        log(
            f"{season}: seri resmi hafta kurtarma={recovered}/{len(missing)}, "
            f"toplamTablo={len(snapshots_by_week)}"
        )
    snapshots = [snapshots_by_week[week] for week in sorted(snapshots_by_week)]
    if len(snapshots) < max(2, max_week // 3):
        return []
    unique = {standings_signature(s.get("standings") or []) for s in snapshots}
    if max_week > 3 and len(unique) <= 1:
        log(f"{season}: resmi tablo haftalık değişmiyor; computed fallback kullanılacak")
        return []
    return snapshots


def try_official_stages(item: dict[str, Any], season: str, raw_root: Path,
                        sleep_s: float, force: bool, workers: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    combined: list[dict[str, Any]] = []
    stage_reports: list[dict[str, Any]] = []
    offset = 0
    for stage_number, stage in enumerate(item.get("standingsStages") or [], 1):
        stage_id = str(stage.get("id") or f"stage-{stage_number}")
        stage_label = str(stage.get("label") or stage_id)
        max_week = int(stage.get("maxWeek") or 0)
        stage_item = {
            "targetPageID": str(stage.get("targetPageID") or ""),
            "targetGrupID": str(stage.get("targetGrupID") or ""),
            "targetModuleID": str(stage.get("targetModuleID") or ""),
            "targetUrls": [] if stage.get("targetPageID") else [stage.get("targetUrl")],
        }
        snapshots = try_official_weekly(
            stage_item, season, raw_root / "stages" / stage_id,
            sleep_s, force, max_week, workers,
        ) if max_week > 0 else []
        stage_reports.append({
            "id": stage_id,
            "label": stage_label,
            "maxWeek": max_week,
            "expectedMatches": int(stage.get("expectedMatches") or 0),
            "carriedMatches": int(stage.get("carriedMatches") or 0),
            "rawFinalPlayed": int(stage.get("rawFinalPlayed") or 0),
            "weeksGenerated": len(snapshots),
            "targetPageID": stage.get("targetPageID"),
            "targetGrupID": stage.get("targetGrupID"),
            "targetModuleID": stage.get("targetModuleID"),
        })
        if not snapshots:
            return [], stage_reports
        for snapshot in snapshots:
            stage_week = int(snapshot.get("week") or 0)
            snapshot["week"] = offset + stage_week
            snapshot["stageWeek"] = stage_week
            snapshot["stageId"] = stage_id
            snapshot["stageLabel"] = stage_label
            snapshot["stageNumber"] = stage_number
            snapshot["stageExpectedMatches"] = int(stage.get("expectedMatches") or 0)
            snapshot["stageCarriedMatches"] = int(stage.get("carriedMatches") or 0)
            snapshot["stageRawFinalPlayed"] = int(stage.get("rawFinalPlayed") or 0)
            combined.append(snapshot)
        offset += max_week
    return combined, stage_reports


def season_item(seed: dict[str, Any], season: str) -> dict[str, Any] | None:
    for item in seed.get("seasons", []) or []:
        if item.get("season") == season:
            return item
    return None


def selected_seasons(seed: dict[str, Any], start: str, max_seasons: int, explicit: list[str] | None = None) -> list[str]:
    if explicit:
        return explicit
    order = seed.get("runOrder") or [x.get("season") for x in seed.get("seasons", []) if x.get("season")]
    if start not in order:
        return [start]
    idx = order.index(start)
    return order[idx: idx + max_seasons]


def standings_row_summary(row: dict[str, Any]) -> dict[str, int]:
    goals_for = int(row.get("goalsFor") or 0)
    goals_against = int(row.get("goalsAgainst") or 0)
    return {
        "played": int(row.get("played") or 0),
        "won": int(row.get("won") or 0),
        "drawn": int(row.get("drawn") or 0),
        "lost": int(row.get("lost") or 0),
        "goalsFor": goals_for,
        "goalsAgainst": goals_against,
        "goalDifference": int(
            row.get("goalDifference")
            if row.get("goalDifference") is not None
            else goals_for - goals_against
        ),
        "points": int(row.get("points") or 0),
        "rawPoints": int(row.get("rawPoints") or row.get("points") or 0),
        "pointsDeducted": int(row.get("pointsDeducted") or 0),
        "finalRank": int(row.get("rank") or 0),
    }


def matching_balkes_snapshot_summary(
    snapshots: list[dict[str, Any]],
    totals: dict[str, int],
) -> dict[str, int] | None:
    for snapshot in reversed(snapshots):
        rows = snapshot.get("standings") or []
        row = next(
            (value for value in rows if value.get("isBalkes") or is_balkes(value.get("team"))),
            None,
        )
        if not row:
            continue
        if all(int(row.get(key) or 0) == totals[key] for key in (
            "played", "goalsFor", "goalsAgainst"
        )):
            return standings_row_summary(row)
    return None


def update_season_files(data_root: Path, season: str, snapshots: list[dict[str, Any]]) -> None:
    season_dir = data_root / "seasons" / season
    season_dir.mkdir(parents=True, exist_ok=True)
    write_json(season_dir / "standings_by_week.json", snapshots)
    season_json = read_json(season_dir / "season.json", {}) or {"id": season, "name": season}
    season_json.pop("officialStandingsMatchTypes", None)
    season_json.pop("officialStandingsSummary", None)
    files = season_json.setdefault("files", {})
    files["standingsByWeek"] = f"seasons/{season}/standings_by_week.json"
    if snapshots:
        league_summary_from_stages: dict[str, Any] | None = None
        stage_finals: dict[str, dict[str, Any]] = {}
        stage_ranges: dict[str, list[int]] = {}
        for snapshot in snapshots:
            stage_id = str(snapshot.get("stageId") or "")
            if not stage_id:
                continue
            stage_finals[stage_id] = snapshot
            stage_ranges.setdefault(stage_id, []).append(int(snapshot.get("week") or 0))
        if stage_finals:
            league_stages: list[dict[str, Any]] = []
            aggregate = {
                "played": 0, "won": 0, "drawn": 0, "lost": 0,
                "goalsFor": 0, "goalsAgainst": 0,
                "points": 0, "rawPoints": 0, "pointsDeducted": 0,
            }
            ordered_finals = sorted(
                stage_finals.items(),
                key=lambda value: int(value[1].get("stageNumber") or 0),
            )
            final_rank = 0
            for stage_id, snapshot in ordered_finals:
                rows = snapshot.get("standings") or []
                row = next((value for value in rows if value.get("isBalkes")), None)
                if not row:
                    continue
                weeks = stage_ranges.get(stage_id) or []
                carried = int(snapshot.get("stageCarriedMatches") or 0)
                raw_values = {
                    "played": int(row.get("played") or 0),
                    "won": int(row.get("won") or 0),
                    "drawn": int(row.get("drawn") or 0),
                    "lost": int(row.get("lost") or 0),
                    "goalsFor": int(row.get("goalsFor") or 0),
                    "goalsAgainst": int(row.get("goalsAgainst") or 0),
                    "points": int(row.get("points") or 0),
                    "rawPoints": int(row.get("rawPoints") or row.get("points") or 0),
                    "pointsDeducted": int(row.get("pointsDeducted") or 0),
                }
                effective = {
                    key: raw_values[key] - aggregate[key] if carried else raw_values[key]
                    for key in aggregate
                }
                if carried:
                    aggregate.update(raw_values)
                else:
                    for key, value in effective.items():
                        aggregate[key] += value
                final_rank = int(row.get("rank") or 0)
                league_stages.append({
                    "id": stage_id,
                    "label": snapshot.get("stageLabel") or stage_id,
                    "stageNumber": int(snapshot.get("stageNumber") or 0),
                    "startWeek": min(weeks, default=0),
                    "endWeek": max(weeks, default=0),
                    "played": effective["played"],
                    "won": effective["won"],
                    "drawn": effective["drawn"],
                    "lost": effective["lost"],
                    "goalsFor": effective["goalsFor"],
                    "goalsAgainst": effective["goalsAgainst"],
                    "goalDifference": effective["goalsFor"] - effective["goalsAgainst"],
                    "points": effective["points"],
                    "finalRank": final_rank,
                    "carriedMatches": carried,
                    "officialTableIsCumulative": bool(carried),
                })
            league_stages.sort(key=lambda value: (value.get("stageNumber", 0), value.get("startWeek", 0)))
            season_json["leagueStages"] = league_stages
            league_summary_from_stages = {
                **aggregate,
                "goalDifference": aggregate["goalsFor"] - aggregate["goalsAgainst"],
                "finalRank": final_rank,
            }
        final = snapshots[-1].get("standings") or []
        balkes = next((r for r in final if r.get("isBalkes")), None)
        if balkes:
            league_summary = league_summary_from_stages or standings_row_summary(balkes)
            matches = read_json(season_dir / "matches_index.json", []) or []
            if isinstance(matches, list) and matches:
                scope = official_standings_scope(matches, league_summary)
                season_json["officialStandingsMatchTypes"] = scope["matchTypes"]
                season_json["officialStandingsSummary"] = dict(league_summary)
                if scope["exact"] and "playoff" in scope["matchTypes"]:
                    league_totals = played_balkes_totals(matches, {"league"})
                    league_only = matching_balkes_snapshot_summary(snapshots, league_totals)
                    if league_only:
                        league_summary = league_only
            season_json["leagueSummary"] = league_summary
            summary = season_json.setdefault("summary", {})
            # Genel özet kupa/play-off dahil bütün maçları kapsar. Puan tablosu
            # verisi bu gol toplamlarının üzerine yazılmaz; yalnız lig alanları
            # ayrıca tutulur ve eski istemci için birkaç alan aynalanır.
            for key in ("points", "rawPoints", "pointsDeducted", "finalRank"):
                summary[key] = league_summary[key]
    season_json["standingsUpdatedAt"] = now()
    season_json["standingsBuilderVersion"] = BUILDER_VERSION
    write_json(season_dir / "season.json", season_json)


def update_manifest(data_root: Path, seasons: list[str]) -> None:
    manifest_path = data_root / "manifest.json"
    manifest = read_json(manifest_path, {}) or {}
    available = manifest.get("availableSeasons") or []
    by_season = {s.get("id"): s for s in available if isinstance(s, dict)}
    for season in seasons:
        season_json = read_json(data_root / "seasons" / season / "season.json", {}) or {}
        if season in by_season and season_json.get("summary"):
            by_season[season].pop("officialStandingsMatchTypes", None)
            by_season[season].pop("officialStandingsSummary", None)
            by_season[season]["summary"] = season_json.get("summary")
            if season_json.get("leagueSummary"):
                by_season[season]["leagueSummary"] = season_json.get("leagueSummary")
            if season_json.get("leagueStages"):
                by_season[season]["leagueStages"] = season_json.get("leagueStages")
            if season_json.get("officialStandingsMatchTypes"):
                by_season[season]["officialStandingsMatchTypes"] = season_json.get(
                    "officialStandingsMatchTypes"
                )
            if season_json.get("officialStandingsSummary"):
                by_season[season]["officialStandingsSummary"] = season_json.get(
                    "officialStandingsSummary"
                )
            by_season[season]["standingsByWeekUrl"] = f"seasons/{season}/standings_by_week.json"
    manifest["standingsUpdatedAt"] = now()
    manifest["standingsBuilderVersion"] = BUILDER_VERSION
    write_json(manifest_path, manifest)


def commit_and_push(paths: list[str], message: str, push: bool, branch: str) -> None:
    subprocess.run(["git", "add", *paths], check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        log("Commit edilecek değişiklik yok.")
        return
    subprocess.run(["git", "commit", "-m", message], check=True)
    if push:
        subprocess.run(["git", "pull", "--rebase", "origin", branch], check=True)
        subprocess.run(["git", "push", "origin", f"HEAD:{branch}"], check=True)



def snapshots_look_clean(snapshots: list[dict[str, Any]]) -> bool:
    if not snapshots:
        return False
    good = 0
    for s in snapshots:
        rows = clean_standings_rows(s.get("standings") or [])
        if standings_rows_are_usable(rows, require_balkes=True):
            s["standings"] = rows
            good += 1
    return good >= max(1, len(snapshots) // 2)

def process_one(season: str, item: dict[str, Any], args: argparse.Namespace, seed: dict[str, Any], penalties: dict[str, Any]) -> dict[str, Any]:
    data_root = Path(args.data_root)
    raw_root = Path(args.raw_root)
    reports_root = Path(args.reports_root)
    configured_stages = item.get("standingsStages") or []
    max_week = (
        sum(int(stage.get("maxWeek") or 0) for stage in configured_stages)
        if configured_stages
        else int(item.get("maxWeek") or (item.get("tffPlan") or {}).get("maxWeek") or args.default_max_week)
    )
    report: dict[str, Any] = {
        "season": season,
        "generatedAt": now(),
        "builderVersion": BUILDER_VERSION,
        "mode": args.mode,
        "maxWeek": max_week,
        "source": "none",
        "weeksGenerated": 0,
        "teams": 0,
        "matchesUsed": 0,
        "penaltiesApplied": len((penalties.get("seasons") or {}).get(season) or []),
        "warnings": [],
    }

    if item.get("skipTff") or item.get("professionalStatus") == "amateur":
        report["source"] = "skipped_amateur_or_no_tff"
        report["warnings"].append(item.get("skipReason") or "Bu sezon TFF profesyonel kayıt taraması için atlandı.")
        write_json(reports_root / f"{season}.json", report)
        log(f"{season}: atlandı ({report['warnings'][-1]})")
        return report

    if not configured_stages and not build_item_urls(item, None):
        # Yalnızca Balıkesirspor'un maçlarından bütün ligin tablosu hesaplanamaz.
        # Böyle bir çıktı sayısal olarak düzgün görünse bile rakiplerin birbirleriyle
        # oynadığı maçları içermediği için yanlıştır. Eksik hedefi açıkça raporla.
        report["source"] = "missing_exact_tff_league_target"
        report["warnings"].append(
            "TFF lig/grup hedefi bulunamadı; eksik lig maçlarından sahte puan tablosu üretilmedi."
        )
        write_json(reports_root / f"{season}.json", report)
        log(f"{season}: hedef TFF URL yok; yanlış/eksik tablo üretilmedi")
        return report

    snapshots: list[dict[str, Any]] = []
    if args.mode in {"auto", "official-only"}:
        log(f"{season}: resmi haftalık tablo deneniyor")
        if configured_stages:
            snapshots, stage_reports = try_official_stages(
                item, season, raw_root, args.sleep, args.force, args.week_workers
            )
            report["stages"] = stage_reports
        else:
            snapshots = try_official_weekly(
                item, season, raw_root, args.sleep, args.force, max_week, args.week_workers
            )
        if snapshots and snapshots_look_clean(snapshots):
            report["source"] = (
                "official_tff_multi_stage_weekly_table"
                if configured_stages else "official_tff_weekly_table"
            )
        elif snapshots:
            report["warnings"].append("Resmi tablo parse edildi ama satır tutarlılığı zayıf; hesaplama fallback kullanılacak.")
            snapshots = []
    if not snapshots and args.mode == "official-only":
        report["warnings"].append("Resmi haftalık tablo bulunamadı.")
    if not snapshots and args.mode in {"auto", "computed-only"}:
        log(f"{season}: maç detaylarından hesaplama deneniyor")
        matches, fetch_stats = fetch_full_league_matches(
            item, season, seed, raw_root, args.sleep, args.force, max_week,
            args.probe_limit, args.workers, args.detail_fetch_mode, args.week_param_mode
        )
        report["matchesUsed"] = len(matches)
        report["fetchStats"] = fetch_stats
        teams = sorted({clean_team(m.get("homeTeam", "")) for m in matches} | {clean_team(m.get("awayTeam", "")) for m in matches})
        teams = [t for t in teams if t]
        report["teams"] = len(teams)
        min_matches = max(1, int((len(teams) * max_week / 2) * args.min_match_coverage)) if teams else 1
        if len(matches) >= min_matches or args.allow_partial:
            snapshots = compute_weekly_standings(matches, season, max_week, penalties)
            report["source"] = "computed_from_tff_results"
            if args.allow_partial and len(matches) < min_matches:
                report["warnings"].append(f"Partial tablo yazıldı: {len(matches)} maç, beklenen minimum {min_matches}.")
        else:
            report["warnings"].append(f"Yeterli lig maçı bulunamadı: {len(matches)} maç, minimum eşik {min_matches}. Partial tablo yazılmadı.")
    if snapshots:
        for _snap in snapshots:
            _snap["standings"] = clean_standings_rows(_snap.get("standings") or [])
        update_season_files(data_root, season, snapshots)
        report["weeksGenerated"] = len(snapshots)
        final = snapshots[-1].get("standings") or []
        report["teams"] = report.get("teams") or len(final)
        report["balkesFinal"] = next((r for r in final if r.get("isBalkes")), None)
    write_json(reports_root / f"{season}.json", report)
    log(f"{season}: tamam source={report['source']} weeks={report['weeksGenerated']} warnings={len(report['warnings'])}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="sources/tff/registry/balkes_tff_seed_registry.json")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--raw-root", default="sources/tff/standings_raw")
    ap.add_argument("--reports-root", default="reports/standings")
    ap.add_argument("--penalties", default=DEFAULT_PENALTIES)
    ap.add_argument("--start-season", default="2025-2026")
    ap.add_argument("--max-seasons", type=int, default=1)
    ap.add_argument("--season", action="append", help="Specific season. Can be repeated.")
    ap.add_argument("--mode", choices=["auto", "official-only", "computed-only"], default="auto")
    ap.add_argument("--default-max-week", type=int, default=34)
    ap.add_argument("--probe-limit", type=int, default=2500)
    ap.add_argument("--workers", type=int, default=4, help="Parallel detail fetch workers. Use 1 for fully serial/polite mode.")
    ap.add_argument("--week-workers", type=int, default=4, help="Bir sezonun resmi hafta sayfaları için paralel istek sayısı.")
    ap.add_argument("--season-workers", type=int, default=2, help="Aynı anda işlenecek sezon sayısı.")
    ap.add_argument("--detail-fetch-mode", choices=["missing", "all", "none"], default="missing", help="missing=listing rows first, details only for missing rows; all=verify every ID; none=listing-only fast mode.")
    ap.add_argument("--week-param-mode", choices=["smart", "fast", "wide"], default="smart", help="smart tries hafta first then fallbacks only when needed; fast uses only hafta; wide tries all params.")
    ap.add_argument("--min-match-coverage", type=float, default=0.55)
    ap.add_argument("--allow-partial", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    seed = read_json(args.seed, {}) or {}
    data_root = Path(args.data_root)
    reports_root = Path(args.reports_root)
    reports_root.mkdir(parents=True, exist_ok=True)
    penalties = load_penalties(Path(args.penalties))
    seasons = selected_seasons(seed, args.start_season, args.max_seasons, args.season)
    log("standings queue=" + ", ".join(seasons))
    reports_by_season: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, int(args.season_workers))) as executor:
        futures = {
            executor.submit(
                process_one, season, season_item(seed, season) or {"season": season},
                args, seed, penalties,
            ): season
            for season in seasons
        }
        for future in as_completed(futures):
            season = futures[future]
            reports_by_season[season] = future.result()
    reports = [reports_by_season[season] for season in seasons]
    changed = [report["season"] for report in reports if report.get("weeksGenerated")]
    if changed:
        update_manifest(data_root, changed)
    summary = {
        "generatedAt": now(),
        "builderVersion": BUILDER_VERSION,
        "seasons": reports,
    }
    write_json(reports_root / "last_run_summary.json", summary)
    if args.commit or args.push:
        # Do not add raw HTML or tee logs. Keep committed reports to compact JSON only.
        report_jsons = [str(p) for p in sorted(reports_root.glob("*.json"))]
        paths = [
            str(data_root / "manifest.json"),
            str(data_root / "standings_penalties.json"),
            str(data_root / "seasons"),
            *report_jsons,
        ]
        message = f"Build weekly standings from {seasons[0]} ({len(seasons)} seasons)"
        commit_and_push(paths, message, args.push, args.branch)
    failures = [r for r in reports if not r.get("weeksGenerated") and r.get("source") != "skipped_amateur_or_no_tff"]
    if failures and not args.allow_partial:
        log(f"Uyarı: {len(failures)} sezon için puan tablosu üretilmedi. Raporlara bakın: {args.reports_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
