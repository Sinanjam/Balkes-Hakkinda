#!/usr/bin/env python3
"""TFF Balıkesirspor kulüp sayfasından sezon ve maç kimliği keşfi.

TFF'nin eski ASP.NET/RadComboBox formunu gerçek bir tarayıcı gibi gönderir.
Sonuç, ayrıntı ve puan tablosu üreticilerinin kullandığı geçici registry'dir.
"""
from __future__ import annotations

import argparse
import copy
import html as html_lib
import itertools
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from archive_rules import reconciled_stage_max_week, select_reconciled_stage_set
from tff_factory import (
    clean_text,
    decode_bytes,
    is_balkes,
    norm,
    now,
    parse_detail,
    read_json,
    write_json,
)
from tff_standings_builder import (
    clean_standings_rows,
    parse_official_standings,
    standings_signature,
    standings_rows_are_usable,
)


DEFAULT_CLUB_URL = os.environ.get(
    "TFF_CLUB_URL",
    "http://www.tff.org/Default.aspx?pageId=28&kulupId=135",
)
SEASON_CONTROL = "ctl00$MPane$m_28_398_ctnr$m_28_398$SezonSelector1$combo"
TEAM_CONTROL = "ctl00$MPane$m_28_398_ctnr$m_28_398$cmbTakimlar"
SEARCH_BUTTON = "ctl00$MPane$m_28_398_ctnr$m_28_398$bntAra"
FIXTURE_GRID = "ctl00$MPane$m_28_398_ctnr$m_28_398$grdFikstur"
TEAM_TEXT = "BALIKESİRSPOR(Profesyonel Takım)"
TEAM_ID = "136"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Balkes-TFF-Sync/1.0"
PRINT_LOCK = threading.Lock()
ARCHIVE_ROOT_PAGE_IDS = {
    "first": 563,
    "second": 371,
    "third": 376,
}
STANDINGS_TARGET_CACHE_VERSION = 2


def seed_item(seed: dict[str, Any], season: str) -> dict[str, Any] | None:
    return next(
        (item for item in seed.get("seasons", []) if item.get("season") == season),
        None,
    )


def has_standings_target(item: dict[str, Any]) -> bool:
    plan = item.get("tffPlan") or {}
    return bool(
        item.get("standingsStages")
        or item.get("targetUrls")
        or item.get("targetPageID")
        or plan.get("pageID")
    )


def log(message: str) -> None:
    with PRINT_LOCK:
        print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def decode_response(response: requests.Response) -> str:
    return decode_bytes(response.content, response.headers.get("Content-Type", ""))


def tff_http(url: str) -> str:
    value = html_lib.unescape(str(url or "").strip())
    value = value.replace("https://www.tff.org", "http://www.tff.org")
    value = value.replace("https://tff.org", "http://www.tff.org")
    return value


def make_session(cookies: dict[str, str] | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.5",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
    })
    if cookies:
        session.cookies.update(cookies)
    return session


def request(session: requests.Session, method: str, url: str, *, data: dict[str, str] | None,
            timeout: float, attempts: int, delay: float) -> requests.Response:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.request(
                method,
                url,
                data=data,
                timeout=(min(8.0, timeout), timeout),
                allow_redirects=True,
                headers={"Referer": url} if method.upper() == "POST" else None,
            )
            if response.status_code in {429, 500, 502, 503, 504}:
                raise RuntimeError(f"HTTP {response.status_code}")
            response.raise_for_status()
            if delay:
                time.sleep(delay)
            return response
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(min(2.0, 0.25 * attempt))
    raise RuntimeError(f"{method} {url}: {last}")


def form_fields(raw: str) -> dict[str, str]:
    soup = BeautifulSoup(raw, "lxml")
    fields: dict[str, str] = {}
    for node in soup.select("input[name]"):
        kind = str(node.get("type") or "text").lower()
        if kind in {"hidden", "text"}:
            fields[str(node.get("name"))] = str(node.get("value") or "")
    return fields


def season_choices(raw: str) -> list[dict[str, str | int]]:
    found: dict[str, dict[str, str | int]] = {}
    pattern = re.compile(r'\{"Text":"(\d{4}-\d{4})","Value":"(\d{1,3})"')
    for match in pattern.finditer(raw):
        season, value = match.group(1), match.group(2)
        if season not in found:
            found[season] = {"season": season, "value": value, "index": len(found)}
    if found:
        return list(found.values())

    years = sorted(set(re.findall(r"\b(19\d{2}|20\d{2})-(19\d{2}|20\d{2})\b", raw)), reverse=True)
    return [
        {"season": f"{start}-{end}", "value": str(int(start) % 100), "index": index}
        for index, (start, end) in enumerate(years)
    ]


def selected_season(raw: str) -> str:
    soup = BeautifulSoup(raw, "lxml")
    node = soup.find(id=re.compile(r"m_28_398.*SezonSelector1_combo_Input$", re.I))
    return clean_text(node.get("value")) if node else ""


def apply_selection(fields: dict[str, str], choice: dict[str, str | int], *, button: bool) -> dict[str, str]:
    data = dict(fields)
    season = str(choice["season"])
    data[SEASON_CONTROL + "_Input"] = season
    data[SEASON_CONTROL + "_text"] = season
    data[SEASON_CONTROL + "_value"] = str(choice["value"])
    data[SEASON_CONTROL + "_index"] = str(choice["index"])
    data[TEAM_CONTROL + "_Input"] = TEAM_TEXT
    data[TEAM_CONTROL + "_text"] = TEAM_TEXT
    data[TEAM_CONTROL + "_value"] = TEAM_ID
    data[TEAM_CONTROL + "_index"] = "0"
    data["__EVENTTARGET"] = "" if button else SEASON_CONTROL
    data["__EVENTARGUMENT"] = "" if button else "TextChange"
    if button:
        data[SEARCH_BUTTON] = "Ara"
    else:
        data.pop(SEARCH_BUTTON, None)
    return data


def normalize_page_url(base_url: str, href: str) -> str:
    absolute = tff_http(urljoin(base_url, html_lib.unescape(href)))
    parsed = urlparse(absolute)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    ordered = sorted(params.items(), key=lambda item: item[0].lower())
    return urlunparse(parsed._replace(query=urlencode(ordered)))


def extract_fixture_result(raw: str, season: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(raw, "lxml")
    grid = soup.find(id=re.compile(r"m_28_398.*grdFikstur$", re.I)) or soup
    fixtures: dict[str, dict[str, Any]] = {}
    competition_urls: set[str] = set()
    weeks: list[int] = []

    for row in grid.find_all("tr"):
        row_links = [str(a.get("href") or "") for a in row.find_all("a", href=True)]
        match_ids: set[str] = set()
        for href in row_links:
            match_ids.update(re.findall(r"[?&](?:amp;)?macId=(\d+)", html_lib.unescape(href), re.I))
        if not match_ids:
            continue

        row_text = clean_text(row.get_text(" ", strip=True))
        week_match = re.search(r"\b(\d{1,2})\s*\.?\s*Hafta\b", row_text, re.I)
        # Güncel/eski TFF kulüp fikstürü görünümlerinde hafta çoğunlukla ayrı
        # ilk sütundur. Satır metni "17 BALIKESİRSPOR ..." olur ve "Hafta"
        # sözcüğü bulunmaz. 60 üst sınırı yanlışlıkla maç kodu/tarih almamızı
        # engeller.
        leading_week = re.match(r"^\s*(\d{1,2})(?=\s+\S)", row_text)
        week = int(week_match.group(1)) if week_match else (
            int(leading_week.group(1)) if leading_week and 0 < int(leading_week.group(1)) <= 60 else 0
        )
        if week:
            weeks.append(week)

        detail_href = next((href for href in row_links if re.search(r"[?&](?:amp;)?macId=", html_lib.unescape(href), re.I)), "")
        for match_id in match_ids:
            fixtures[match_id] = {
                "id": match_id,
                "season": season,
                "week": week,
                "rowText": row_text,
                "sourceUrl": normalize_page_url(source_url, detail_href) if detail_href else "",
            }

        for anchor in row.find_all("a", href=True):
            decoded = html_lib.unescape(str(anchor.get("href") or ""))
            query = dict(parse_qsl(urlparse(urljoin(source_url, decoded)).query))
            page_id = str(query.get("pageID") or query.get("pageId") or "")
            group_id = str(query.get("grupID") or query.get("grupId") or "")
            label = norm(anchor.get_text(" ", strip=True))
            looks_like_competition = any(
                part in label for part in ("lig", "sezon", "grup", "fikstur", "puan")
            )
            if (page_id and page_id not in {"28", "29", "30", "72", "219", "394", "528"}
                    and "macId" not in query and (group_id or looks_like_competition)):
                competition_urls.add(normalize_page_url(source_url, decoded))

    # Bazı TFF sürümlerinde grup bağlantısı fikstür satırının dışında kalıyor.
    for anchor in grid.find_all("a", href=True):
        href = html_lib.unescape(str(anchor.get("href") or ""))
        query = dict(parse_qsl(urlparse(urljoin(source_url, href)).query))
        page_id = str(query.get("pageID") or query.get("pageId") or "")
        group_id = str(query.get("grupID") or query.get("grupId") or "")
        if page_id and group_id and page_id not in {"28", "29", "528"}:
            competition_urls.add(normalize_page_url(source_url, href))

    return {
        "season": season,
        "selectedSeason": selected_season(raw),
        "matchIds": sorted(fixtures, key=int),
        "fixtures": [fixtures[key] for key in sorted(fixtures, key=int)],
        "targetUrls": sorted(competition_urls),
        "maxWeek": max(weeks, default=0),
    }


def fixture_page_count(raw: str) -> int:
    marker = 'window["ctl00_MPane_m_28_398_ctnr_m_28_398_grdFikstur"]'
    start = raw.find(marker)
    segment = raw[start:start + 16000] if start >= 0 else raw
    match = re.search(r"PageCount\s*:\s*(\d+)", segment, re.I)
    count = int(match.group(1)) if match else 1
    for page in re.findall(r"Page\$(\d+)", html_lib.unescape(segment), re.I):
        count = max(count, int(page))
    return max(1, count)


def _postback_from_script(script: str) -> tuple[str, str] | None:
    """ASP.NET LinkButton ve WebForm postback komutunu JavaScript'ten çıkarır."""
    decoded = html_lib.unescape(str(script or ""))
    patterns = (
        r"__doPostBack\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)",
        r"WebForm_PostBackOptions\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]",
    )
    for pattern in patterns:
        match = re.search(pattern, decoded, re.I)
        if match:
            return match.group(1), match.group(2)
    return None


def fixture_page_actions(raw: str, page: int) -> list[dict[str, str]]:
    """Telerik RadGrid için güvenli sayfalama eylemlerini öncelik sırasıyla bulur.

    Eski TFF sayfası her dönemde aynı pager HTML'ini üretmiyor. Bazı sürümler
    ``Page$2`` argümanı, bazıları ise numaralı LinkButton'ın tam kontrol adını
    ve boş argümanı kullanıyor. HTML'deki gerçek düğme daima ilk tercihtir.
    """
    decoded = html_lib.unescape(raw)
    actions: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add(*, target: str = "", argument: str = "", submit_name: str = "",
            submit_value: str = "", source: str) -> None:
        key = (target, argument, submit_name, submit_value)
        if key in seen or not (target or submit_name):
            return
        seen.add(key)
        actions.append({
            "target": target,
            "argument": argument,
            "submitName": submit_name,
            "submitValue": submit_value,
            "source": source,
        })

    soup = BeautifulSoup(raw, "lxml")
    grid = soup.find(id=re.compile(r"m_28_398.*grdFikstur$", re.I)) or soup
    for node in grid.find_all(["a", "button", "input"]):
        label = clean_text(node.get("value") or node.get_text(" ", strip=True))
        script = " ".join(str(node.get(name) or "") for name in ("href", "onclick"))
        normalized_script = html_lib.unescape(script)
        is_requested = bool(
            re.search(rf"Page\${page}(?:\D|$)", normalized_script, re.I)
            or label == str(page)
            or re.search(rf"(?:sayfa|page)\s*{page}\b", norm(label + " " + str(node.get("title") or "")), re.I)
        )
        if not is_requested:
            continue
        postback = _postback_from_script(normalized_script)
        if postback:
            add(target=postback[0], argument=postback[1], source="html_postback")
        name = str(node.get("name") or "")
        if name and "grdfikstur" in name.lower():
            add(submit_name=name, submit_value=str(node.get("value") or label), source="html_submit")

    # HTML parserın dışında kalan script bloklarındaki açık Page$N komutları.
    for match in re.finditer(
        r"__doPostBack\(\s*['\"]([^'\"]*grdFikstur[^'\"]*)['\"]\s*,"
        rf"\s*['\"]Page\${page}['\"]\s*\)",
        decoded,
        re.I,
    ):
        add(target=match.group(1), argument=f"Page${page}", source="script_page_command")

    # Son çareler: farklı Telerik sürümlerinde grid veya master table hedef olur.
    add(target=FIXTURE_GRID, argument=f"Page${page}", source="radgrid_fallback")
    add(target=FIXTURE_GRID + "$ctl00", argument=f"Page${page}", source="master_table_fallback")
    return actions


def merge_fixture_pages(pages: list[str], season: str, source_url: str, *,
                        expected_pages: int | None = None,
                        pagination_complete: bool = True,
                        pagination_error: str = "",
                        pagination_strategies: list[str] | None = None) -> dict[str, Any]:
    merged_fixtures: dict[str, dict[str, Any]] = {}
    targets: set[str] = set()
    max_week = 0
    for raw in pages:
        current = extract_fixture_result(raw, season, source_url)
        for fixture in current.get("fixtures", []):
            merged_fixtures[str(fixture["id"])] = fixture
        targets.update(current.get("targetUrls", []))
        max_week = max(max_week, int(current.get("maxWeek") or 0))
    ids = sorted(merged_fixtures, key=int)
    return {
        "season": season,
        "selectedSeason": season,
        "matchIds": ids,
        "fixtures": [merged_fixtures[mid] for mid in ids],
        "targetUrls": sorted(targets),
        "maxWeek": max_week,
        "fixturePages": len(pages),
        "fixturePagesExpected": int(expected_pages or len(pages)),
        "paginationComplete": bool(pagination_complete),
        "paginationError": pagination_error,
        "paginationStrategies": pagination_strategies or [],
    }


def cached_fixture_pages(cache_dir: Path, season: str) -> list[str] | None:
    first_path = cache_dir / f"{season}.html"
    if not first_path.exists() or first_path.stat().st_size <= 500:
        return None
    first = first_path.read_text(encoding="utf-8", errors="replace")
    expected = fixture_page_count(first)
    pages = [first]
    for page in range(2, expected + 1):
        path = cache_dir / f"{season}_page_{page:02d}.html"
        if not path.exists() or path.stat().st_size <= 500:
            return None
        pages.append(path.read_text(encoding="utf-8", errors="replace"))
    return pages


def adult_league_tier(value: str) -> str:
    """TFF metnini yetişkin erkek lig seviyesine indirger."""
    text = norm(value)
    excluded = (
        "kadin", "u14", "u15", "u16", "u17", "u18", "u19",
        "gelisim", "altyapi", "futsal", "plaj", "engelli", "kupa",
        "play off", "baraj", "sampiyona",
    )
    if any(part in text for part in excluded):
        return ""
    if "super lig" in text or "1 lig" in text and "turkiye 1 ligi" in text:
        return "super"
    if re.search(r"(?:^| )1 (?:lig|ligi)(?: |$)", text):
        return "first"
    if re.search(r"(?:^| )2 (?:lig|ligi)(?: |$)", text):
        return "second"
    if re.search(r"(?:^| )3 (?:lig|ligi)(?: |$)", text):
        return "third"
    if "bolgesel amator" in text or text == "bal":
        return "regional"
    return ""


def archive_root_for_item(item: dict[str, Any]) -> int:
    text = norm(" ".join(str(item.get(key) or "") for key in (
        "competition", "leagueEra", "professionalStatus"
    )))
    if re.search(r"(?:^| )(?:tff |turkiye )?3 (?:lig|ligi)(?: |$)", text):
        return ARCHIVE_ROOT_PAGE_IDS["third"]
    if re.search(r"(?:^| )(?:tff |turkiye )?2 (?:lig|ligi)(?: |$)", text):
        return ARCHIVE_ROOT_PAGE_IDS["second"]
    if re.search(r"(?:^| )(?:tff |turkiye )?1 (?:lig|ligi)(?: |$)", text):
        return ARCHIVE_ROOT_PAGE_IDS["first"]
    return 0


def archive_stage_sort_key(stage: dict[str, Any]) -> tuple[int, str]:
    label = norm(stage.get("label") or "")
    # Kademe/numaralı gruplar ilk devre, Klasman/Final grupları ikinci devredir.
    if re.fullmatch(r"\d+", label) or "kademe" in label:
        return 0, label
    if label.startswith("k") or "klasman" in label or label == "f":
        return 1, label
    return 2, label


def expected_league_matches_from_item(item: dict[str, Any]) -> int:
    return expected_standings_matches_from_item(item)["league"]


def fixture_match_type(item: dict[str, Any], fixture: dict[str, Any]) -> str:
    """Kulüp fikstürü satırını ayrıntı indirilmeden dar biçimde sınıflandırır."""
    overrides = item.get("matchOverrides") or {}
    override = overrides.get(str(fixture.get("id") or "")) if isinstance(overrides, dict) else None
    if isinstance(override, dict) and override.get("matchType"):
        return str(override["matchType"])
    text = norm(fixture.get("rowText") or "")
    if any(value in text for value in ("play off", "playoff", "final musabakalari")):
        return "playoff"
    if any(value in text for value in ("turkiye kupasi", "ziraat", " kupa ")):
        return "cup"
    return "league" if adult_league_tier(text) else ""


def expected_standings_matches_from_item(item: dict[str, Any]) -> dict[str, int]:
    """Resmi tablonun kabul edilebilecek maç kapsamlarını sayar.

    Lig sayısı ana hedeftir. TFF grup tablosu play-off maçlarını aynı puan
    cetveline eklediyse lig+play-off toplamı yalnız ikinci hedef olarak kabul
    edilir; kupa ve diğer maçlar hiçbir zaman bu toplama girmez.
    """
    totals = {"league": 0, "playoff": 0, "standings": 0}
    fixtures = [value for value in item.get("knownFixtures", []) if isinstance(value, dict)]
    for fixture in fixtures:
        match_type = fixture_match_type(item, fixture)
        if match_type in {"league", "playoff"}:
            totals[match_type] += 1
    totals["standings"] = totals["league"] + totals["playoff"]
    return totals


def max_numbered_league_fixture_week(item: dict[str, Any]) -> int:
    """Yalnız gerçek lig satırlarındaki açık hafta numarasını döndürür."""
    return max((
        int(fixture.get("week") or 0)
        for fixture in item.get("knownFixtures", [])
        if isinstance(fixture, dict) and fixture_match_type(item, fixture) == "league"
    ), default=0)


def reconcile_archive_stages(
    stages: list[dict[str, Any]],
    expected_league_matches: int,
    expected_standings_matches: int = 0,
    direct_fixture_max_week: int = 0,
) -> list[dict[str, Any]]:
    """Choose the chronological stages matching the discovered league fixture count.

    Some TFF Klasman tables carry Kademe totals forward.  In that case a row
    can say 32 played although the second stage added only 14 matches.
    """
    ordered = sorted((copy.deepcopy(stage) for stage in stages), key=archive_stage_sort_key)

    def annotate(
        values: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        out: list[dict[str, Any]] = []
        running = 0
        for original in values:
            stage = copy.deepcopy(original)
            raw_played = int(stage.get("expectedMatches") or 0)
            carried = running if running > 0 and raw_played > running else 0
            incremental = raw_played - carried if carried else raw_played
            if incremental <= 0:
                return [], -1
            stage["rawFinalPlayed"] = raw_played
            stage["carriedMatches"] = carried
            stage["expectedMatches"] = incremental
            stage["maxWeek"] = reconciled_stage_max_week(
                stage,
                incremental,
                direct_fixture_max_week if len(values) == 1 else 0,
            )
            running += incremental
            out.append(stage)
        return out, running

    if expected_league_matches <= 0:
        return annotate(ordered)[0]

    exact_by_total: dict[int, list[list[dict[str, Any]]]] = {}
    for length in range(1, len(ordered) + 1):
        for subset in itertools.combinations(ordered, length):
            annotated, total = annotate(subset)
            if total > 0:
                exact_by_total.setdefault(total, []).append(annotated)

    targets = [expected_league_matches]
    if expected_standings_matches > expected_league_matches:
        targets.append(expected_standings_matches)
    for target in targets:
        exact = exact_by_total.get(target) or []
        if not exact:
            continue
        selected = select_reconciled_stage_set(exact)
        if selected:
            selected[-1]["officialMatchTypes"] = (
                ["league", "playoff"]
                if target > expected_league_matches
                else ["league"]
            )
        return selected
    return []


def page_mentions_season(raw: str, season: str) -> bool:
    """Require the exact requested season on a candidate standings page."""
    match = re.fullmatch(r"(\d{4})-(\d{4})", str(season or "").strip())
    if not match:
        return False
    start, end = match.groups()
    visible = clean_text(BeautifulSoup(raw, "lxml").get_text(" ", strip=True))
    patterns = (
        rf"\b{start}\s*[-/]\s*{end}\b",
        rf"\b{start}\s*[-/]\s*{end[-2:]}\b",
    )
    return any(re.search(pattern, visible) for pattern in patterns)


def archive_group_is_selected(raw: str, group_id: str) -> bool:
    """Verify that TFF actually activated the requested archive group."""
    wanted = str(group_id or "").strip()
    if not wanted:
        return True
    soup = BeautifulSoup(raw, "lxml")
    for anchor in soup.find_all("a", href=True):
        query = dict(parse_qsl(
            urlparse(html_lib.unescape(str(anchor.get("href") or ""))).query
        ))
        candidate = str(query.get("grupID") or query.get("grupId") or "")
        if candidate != wanted:
            continue
        marker = " ".join([
            str(anchor.get("style") or ""),
            " ".join(anchor.get("class") or []),
            " ".join((anchor.parent or {}).get("class") or []) if anchor.parent else "",
        ]).lower()
        if "a10102" in marker or re.search(r"\b(active|selected|current|on)\b", marker):
            return True
    return False


def standalone_archive_stages(
    raw: str,
    season_page_id: str,
    season_url: str,
) -> list[dict[str, Any]]:
    """Find group-less promotion/final tables rendered beside archive groups."""
    soup = BeautifulSoup(raw, "lxml")
    stages: list[dict[str, Any]] = []
    for module in soup.find_all(
        "div",
        id=lambda value: bool(
            value and "_MPane_" in str(value) and str(value).endswith("_ctnr_div")
        ),
    ):
        module_id = str(module.get("id") or "")
        group_links = []
        week_numbers: list[int] = []
        for anchor in module.find_all("a", href=True):
            query = dict(parse_qsl(
                urlparse(html_lib.unescape(str(anchor.get("href") or ""))).query
            ))
            group_id = str(query.get("grupID") or query.get("grupId") or "")
            if group_id:
                group_links.append(group_id)
            week = str(query.get("hafta") or "")
            if not group_id and week.isdigit():
                week_numbers.append(int(week))
        if group_links:
            continue
        rows = clean_standings_rows(parse_official_standings(str(module)))
        if not standings_rows_are_usable(rows, require_balkes=True):
            continue
        balkes = next((row for row in rows if is_balkes(row.get("team", ""))), None)
        if not balkes:
            continue
        title = module.find(class_=re.compile(r"moduleTitle", re.I))
        label = clean_text(title.get_text(" ", strip=True)) if title else ""
        if not label:
            continue
        played = int(balkes.get("played") or 0)
        team_count = len(rows)
        inferred_max = played + 2 if team_count % 2 == 1 and played > 0 else played
        max_week = max(week_numbers, default=inferred_max)
        stage_id = "standalone-" + (norm(label).replace(" ", "-") or module_id.lower())
        stages.append({
            "id": stage_id,
            "label": label,
            "targetPageID": season_page_id,
            "targetGrupID": "",
            "targetModuleID": module_id,
            "targetUrl": season_url,
            "maxWeek": max_week,
            "expectedMatches": played,
            "teamCount": team_count,
            "finalRank": int(balkes.get("rank") or 0),
            "finalPoints": int(balkes.get("points") or 0),
            "standingsSignature": standings_signature(rows),
        })
    return stages


def discover_archive_standings_stages(
    item: dict[str, Any],
    cache_dir: Path,
    timeout: float,
    attempts: int,
    delay: float,
    force: bool,
) -> dict[str, Any]:
    """TFF lig arşivinden sezon sayfası ve Balıkesirspor grup(lar)ını bulur."""
    season = str(item.get("season") or "")
    root_page_id = archive_root_for_item(item)
    if not root_page_id:
        return {"season": season, "error": "lig arşiv kökü belirlenemedi"}

    def get_cached(session: requests.Session, url: str, path: Path) -> str:
        if path.exists() and path.stat().st_size > 500 and not force:
            return path.read_text(encoding="utf-8", errors="replace")
        response = request(
            session, "GET", url, data=None,
            timeout=timeout, attempts=attempts, delay=delay,
        )
        raw = decode_response(response)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8")
        return raw

    session = make_session()
    try:
        root_url = f"http://www.tff.org/Default.aspx?pageID={root_page_id}"
        root_raw = get_cached(
            session,
            root_url,
            cache_dir / "archive" / f"root_{root_page_id}.html",
        )
        root_soup = BeautifulSoup(root_raw, "lxml")
        season_page_id = ""
        for anchor in root_soup.find_all("a", href=True):
            if clean_text(anchor.get_text(" ", strip=True)) != season:
                continue
            query = dict(parse_qsl(urlparse(urljoin(root_url, str(anchor.get("href")))).query))
            season_page_id = str(query.get("pageID") or query.get("pageId") or "")
            if season_page_id:
                break
        if not season_page_id:
            return {
                "season": season,
                "archiveRootPageID": str(root_page_id),
                "error": "lig arşivinde sezon bağlantısı bulunamadı",
            }

        season_url = f"http://www.tff.org/Default.aspx?pageID={season_page_id}"
        season_raw = get_cached(
            session,
            season_url,
            cache_dir / "archive" / season / f"page_{season_page_id}.html",
        )
        season_soup = BeautifulSoup(season_raw, "lxml")
        groups: dict[str, dict[str, str]] = {}
        for anchor in season_soup.find_all("a", href=True):
            href = html_lib.unescape(str(anchor.get("href") or ""))
            query = dict(parse_qsl(urlparse(urljoin(season_url, href)).query))
            page_id = str(query.get("pageID") or query.get("pageId") or "")
            group_id = str(query.get("grupID") or query.get("grupId") or "")
            if page_id != season_page_id or not group_id:
                continue
            label = clean_text(anchor.get_text(" ", strip=True)) or f"Grup {group_id}"
            groups.setdefault(group_id, {"id": group_id, "label": label})

        candidates = list(groups.values()) or [{"id": "", "label": "Lig"}]

        def inspect_group(candidate: dict[str, str]) -> dict[str, Any] | None:
            group_id = candidate["id"]
            url = season_url + (f"&grupID={group_id}" if group_id else "")
            worker_session = make_session()
            try:
                raw = get_cached(
                    worker_session,
                    url,
                    cache_dir / "archive" / season / f"page_{season_page_id}_group_{group_id or 'none'}.html",
                )
            finally:
                worker_session.close()
            if group_id and not archive_group_is_selected(raw, group_id):
                return None
            rows = clean_standings_rows(parse_official_standings(raw, group_id))
            if not standings_rows_are_usable(rows, require_balkes=True):
                return None
            balkes = next((row for row in rows if is_balkes(row.get("team", ""))), None)
            if not balkes:
                return None
            played = int(balkes.get("played") or 0)
            team_count = len(rows)
            max_week = played + 2 if team_count % 2 == 1 and played > 0 else played
            label = candidate["label"]
            return {
                "id": f"group-{norm(label).replace(' ', '-') or group_id or 'league'}",
                "label": label,
                "targetPageID": season_page_id,
                "targetGrupID": group_id,
                "targetUrl": url,
                "maxWeek": max_week,
                "expectedMatches": played,
                "teamCount": team_count,
                "finalRank": int(balkes.get("rank") or 0),
                "finalPoints": int(balkes.get("points") or 0),
                "standingsSignature": standings_signature(rows),
            }

        stages: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, min(8, len(candidates)))) as executor:
            for stage in executor.map(inspect_group, candidates):
                if stage:
                    stages.append(stage)
        stages.extend(standalone_archive_stages(season_raw, season_page_id, season_url))
        stages.sort(key=archive_stage_sort_key)
        unique_stages: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        for stage in stages:
            signature = str(stage.get("standingsSignature") or "")
            if signature and signature in seen_signatures:
                continue
            if signature:
                seen_signatures.add(signature)
            unique_stages.append(stage)
        stages = unique_stages
        expected_counts = expected_standings_matches_from_item(item)
        expected_league_matches = expected_counts["league"]
        expected_standings_matches = expected_counts["standings"]
        fixture_max_week = max_numbered_league_fixture_week(item)
        reconciled = reconcile_archive_stages(
            stages,
            expected_league_matches,
            expected_standings_matches,
            fixture_max_week,
        )
        if expected_league_matches and not reconciled:
            return {
                "season": season,
                "archiveRootPageID": str(root_page_id),
                "seasonPageID": season_page_id,
                "expectedLeagueMatches": expected_league_matches,
                "expectedStandingsMatches": expected_standings_matches,
                "fixtureMaxWeek": fixture_max_week,
                "error": "arşiv aşamaları kulüp fikstüründeki lig maçı sayısıyla uzlaştırılamadı",
            }
        stages = reconciled
        if not stages:
            return {
                "season": season,
                "archiveRootPageID": str(root_page_id),
                "seasonPageID": season_page_id,
                "error": "arşiv gruplarında Balıkesirspor puan tablosu bulunamadı",
            }
        return {
            "season": season,
            "archiveRootPageID": str(root_page_id),
            "seasonPageID": season_page_id,
            "strategy": "official_tff_archive_groups",
            "expectedLeagueMatches": expected_league_matches,
            "expectedStandingsMatches": expected_standings_matches,
            "fixtureMaxWeek": fixture_max_week,
            "officialStandingsMatchTypes": list(
                (stages[-1] if stages else {}).get("officialMatchTypes") or ["league"]
            ),
            "stages": stages,
        }
    finally:
        session.close()


def points_options(raw: str) -> list[dict[str, Any]]:
    """Maç sayfasındaki Puan Cetvelleri RadComboBox seçeneklerini okur."""
    pattern = re.compile(
        r'\{"Text":"((?:\\.|[^"])*)","Value":"(\d+)_(-?\d+)",'
        r'"ClientID":"([^"]*m_29_2084[^"]*_c(\d+))"\}'
    )
    options: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for match in pattern.finditer(raw):
        text = clean_text(html_lib.unescape(match.group(1).replace(r'\"', '"')))
        tournament_id, group_id = match.group(2), match.group(3)
        if int(group_id) <= 0 or (tournament_id, group_id) in seen:
            continue
        seen.add((tournament_id, group_id))
        options.append({
            "text": text,
            "value": f"{tournament_id}_{group_id}",
            "tournamentId": tournament_id,
            "groupId": group_id,
            "index": int(match.group(5)),
            "tier": adult_league_tier(text),
        })
    return options


def points_control(raw: str) -> str:
    soup = BeautifulSoup(raw, "lxml")
    node = soup.find(
        "input",
        attrs={"name": re.compile(r"\$mo_text$"), "id": re.compile(r"m_29_2084.*_mo_text$", re.I)},
    )
    name = str(node.get("name") or "") if node else ""
    return name[:-5] if name.endswith("_text") else ""


def apply_points_selection(fields: dict[str, str], control: str,
                           option: dict[str, Any]) -> dict[str, str]:
    data = dict(fields)
    data[control + "_Input"] = str(option["text"])
    data[control + "_text"] = str(option["text"])
    data[control + "_value"] = str(option["value"])
    data[control + "_index"] = str(option["index"])
    data["__EVENTTARGET"] = control
    data["__EVENTARGUMENT"] = "TextChange"
    return data


def points_panel_has_balkes(raw: str) -> bool:
    soup = BeautifulSoup(raw, "lxml")
    panel = soup.find(id=re.compile(r"m_29_2084.*Panel1$", re.I))
    return bool(panel and is_balkes(panel.get_text(" ", strip=True)))


def generic_fixture_page(tier: str) -> str:
    return {
        "super": "198",
        "first": "142",
        "second": "976",
        "third": "971",
        "regional": "1289",
    }.get(tier, "")


def target_from_response(response: requests.Response, raw: str, option: dict[str, Any],
                         competition: str) -> dict[str, Any] | None:
    query = dict(parse_qsl(urlparse(tff_http(response.url)).query))
    response_page = str(query.get("pageID") or query.get("pageId") or "")
    response_group = str(query.get("grupID") or query.get("grupId") or "")
    group_id = str(option["groupId"])
    # Bazı arşiv sayfaları redirect yerine doğru sezon URL'sini form/link içinde
    # döndürür. Önce onu kullan; bulunmazsa lig seviyesinin kalıcı sayfasına düş.
    if response_page in {"", "29", "528"}:
        soup = BeautifulSoup(raw, "lxml")
        for node in soup.find_all(lambda tag: tag.has_attr("href") or tag.has_attr("action")):
            candidate = str(node.get("href") or node.get("action") or "")
            candidate_url = tff_http(urljoin(response.url, html_lib.unescape(candidate)))
            candidate_query = dict(parse_qsl(urlparse(candidate_url).query))
            candidate_group = str(
                candidate_query.get("grupID") or candidate_query.get("grupId") or ""
            )
            candidate_page = str(
                candidate_query.get("pageID") or candidate_query.get("pageId") or ""
            )
            if candidate_group == group_id and candidate_page not in {"", "28", "29", "528"}:
                response_page = candidate_page
                response_group = candidate_group
                break
    page_id = response_page if response_page not in {"", "29", "528"} else generic_fixture_page(
        str(option.get("tier") or adult_league_tier(competition))
    )
    if response_group and response_group != group_id:
        return None
    if not page_id:
        return None
    target_url = tff_http(
        "http://www.tff.org/Default.aspx?" + urlencode({"pageID": page_id, "grupID": group_id})
    )
    return {
        "pageId": page_id,
        "groupId": group_id,
        "targetUrl": target_url,
        "competition": competition,
        "optionText": option["text"],
        "optionValue": option["value"],
        "responseUrl": tff_http(response.url),
    }


def discover_standings_target(item: dict[str, Any], result: dict[str, Any], seed: dict[str, Any],
                              raw_dir: Path, cache_dir: Path, timeout: float,
                              attempts: int, delay: float, force: bool) -> dict[str, Any]:
    """Bir lig maçından doğru TFF grup/hedef URL'sini birkaç postback ile bulur."""
    season = str(item["season"])
    cached = cache_dir / season / "target.json"
    if cached.exists() and not force:
        value = read_json(cached, {}) or {}
        if (
            value.get("targetUrl")
            and value.get("season") == season
            and int(value.get("discoveryVersion") or 0) == STANDINGS_TARGET_CACHE_VERSION
        ):
            value["cache"] = True
            return value

    match_ids = [str(value) for value in result.get("matchIds", [])]
    last_error = "uygun lig maçı veya puan cetveli grubu bulunamadı"
    for match_id in match_ids[:8]:
        wrong_season_target_seen = False
        detail_url = tff_http(f"http://www.tff.org/Default.aspx?pageID=29&macId={match_id}")
        session = make_session()
        try:
            detail_response = request(
                session, "GET", detail_url, data=None,
                timeout=timeout, attempts=attempts, delay=delay,
            )
            raw = decode_response(detail_response)
            detail_path = raw_dir / season / "matches" / f"{match_id}.html"
            detail_path.parent.mkdir(parents=True, exist_ok=True)
            detail_path.write_text(raw, encoding="utf-8")
            detail = parse_detail(match_id, raw, season, detail_url, seed)
            if not (is_balkes(detail.get("homeTeam")) or is_balkes(detail.get("awayTeam"))):
                continue
            competition = str(detail.get("competition") or "")
            tier = adult_league_tier(competition)
            if not tier:
                continue
            options = [option for option in points_options(raw) if option.get("tier") == tier]
            control = points_control(raw)
            if not options or not control:
                last_error = f"{match_id}: lig grubu seçenekleri veya postback kontrolü bulunamadı"
                continue

            for option_no, option in enumerate(options):
                # Her aday için taze ViewState kullan; eski ASP.NET aynı state'in
                # ikinci kez gönderilmesini bazı sunucularda reddediyor.
                if option_no:
                    session.close()
                    session = make_session()
                    detail_response = request(
                        session, "GET", detail_url, data=None,
                        timeout=timeout, attempts=attempts, delay=delay,
                    )
                    raw = decode_response(detail_response)
                    control = points_control(raw)
                    if not control:
                        break
                selected = request(
                    session,
                    "POST",
                    detail_url,
                    data=apply_points_selection(form_fields(raw), control, option),
                    timeout=timeout,
                    attempts=attempts,
                    delay=delay,
                )
                selected_raw = decode_response(selected)
                selected_query = dict(parse_qsl(urlparse(tff_http(selected.url)).query))
                redirected_group = str(
                    selected_query.get("grupID") or selected_query.get("grupId") or ""
                )
                if not points_panel_has_balkes(selected_raw) and redirected_group != str(option["groupId"]):
                    continue
                target = target_from_response(selected, selected_raw, option, competition)
                if not target:
                    continue
                verify_response = request(
                    session,
                    "GET",
                    str(target["targetUrl"]),
                    data=None,
                    timeout=timeout,
                    attempts=attempts,
                    delay=delay,
                )
                verify_raw = decode_response(verify_response)
                target_group = str(target.get("groupId") or "")
                verify_rows = clean_standings_rows(
                    parse_official_standings(verify_raw, target_group)
                )
                if not page_mentions_season(verify_raw, season):
                    wrong_season_target_seen = True
                    last_error = (
                        f"{match_id}: grup {option['groupId']} bulundu fakat lig URL'si "
                        f"{season} sezonuna ait değil"
                    )
                    continue
                if not standings_rows_are_usable(verify_rows, require_balkes=True):
                    last_error = (
                        f"{match_id}: grup {option['groupId']} bulundu fakat lig URL'si "
                        "Balıkesirspor puan tablosuyla doğrulanamadı"
                    )
                    continue
                target.update({
                    "season": season,
                    "matchId": match_id,
                    "verified": True,
                    "verifiedUrl": tff_http(verify_response.url),
                    "discoveredAt": now(),
                    "discoveryVersion": STANDINGS_TARGET_CACHE_VERSION,
                    "cache": False,
                })
                write_json(cached, target)
                response_path = cache_dir / season / f"group_{option['groupId']}.html"
                response_path.parent.mkdir(parents=True, exist_ok=True)
                response_path.write_text(selected_raw, encoding="utf-8")
                (cache_dir / season / f"target_{option['groupId']}.html").write_text(
                    verify_raw, encoding="utf-8"
                )
                return target
            if wrong_season_target_seen:
                # Maç detayındaki açılır kutu tarihsel grup yerine güncel ligi
                # gösteriyorsa sonraki yedi maçı aynı postback zinciriyle tekrar
                # denemek yalnızca süre kaybettirir. Arşiv fallback'ine geç.
                return {
                    "season": season,
                    "error": last_error,
                    "strategy": "archive_fallback_after_wrong_season_target",
                }
        except Exception as exc:
            last_error = f"{match_id}: {exc}"
        finally:
            session.close()
    return {"season": season, "error": last_error}


def enrich_standings_targets(runtime: dict[str, Any], results: list[dict[str, Any]],
                             raw_dir: Path, cache_dir: Path, workers: int,
                             timeout: float, attempts: int, delay: float,
                             force: bool) -> list[dict[str, Any]]:
    by_result = {str(value.get("season")): value for value in results if value.get("matchIds")}
    jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for season, result in by_result.items():
        item = seed_item(runtime, season)
        if item and not has_standings_target(item) and not item.get("skipTff"):
            jobs.append((item, result))
    if not jobs:
        return []

    log(f"Eksik puan tablosu hedefleri keşfediliyor: sezon={len(jobs)}")
    by_discovered: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(4, workers))) as executor:
        futures = {
            executor.submit(
                discover_standings_target, item, result, runtime,
                raw_dir, cache_dir, timeout, attempts, delay, force,
            ): str(item["season"])
            for item, result in jobs
        }
        for future in as_completed(futures):
            season = futures[future]
            try:
                target = future.result()
            except Exception as exc:
                target = {"season": season, "error": str(exc)}
            by_discovered[season] = target
            item = seed_item(runtime, season)
            if target.get("targetUrl") and item:
                item["targetUrls"] = sorted(set(item.get("targetUrls", [])) | {target["targetUrl"]})
                item["targetPageID"] = str(target["pageId"])
                item["targetGrupID"] = str(target["groupId"])
                item["standingsTargetDiscovery"] = target
                log(f"{season}: puan hedefi bulundu pageID={target['pageId']} grupID={target['groupId']}")
            else:
                log(
                    f"{season}: maç detayından puan hedefi bulunamadı; "
                    "lig arşivi deneniyor"
                )

    archive_jobs = [
        item for item, _ in jobs
        if not by_discovered.get(str(item["season"]), {}).get("targetUrl")
        and archive_root_for_item(item)
    ]
    if archive_jobs:
        with ThreadPoolExecutor(max_workers=max(1, min(4, workers))) as executor:
            futures = {
                executor.submit(
                    discover_archive_standings_stages,
                    item, cache_dir, timeout, attempts, delay, force,
                ): str(item["season"])
                for item in archive_jobs
            }
            for future in as_completed(futures):
                season = futures[future]
                previous = by_discovered.get(season, {})
                try:
                    target = future.result()
                except Exception as exc:
                    target = {"season": season, "error": str(exc)}
                if previous.get("error"):
                    target["matchDetailDiscoveryError"] = previous["error"]
                by_discovered[season] = target
                item = seed_item(runtime, season)
                stages = target.get("stages") or []
                if stages and item:
                    item["standingsStages"] = stages
                    item["officialStandingsMatchTypes"] = list(
                        target.get("officialStandingsMatchTypes") or ["league"]
                    )
                    item["targetUrls"] = sorted(
                        set(item.get("targetUrls", []))
                        | {str(stage["targetUrl"]) for stage in stages if stage.get("targetUrl")}
                    )
                    if len(stages) == 1:
                        stage = stages[0]
                        item["targetPageID"] = str(stage.get("targetPageID") or "")
                        item["targetGrupID"] = str(stage.get("targetGrupID") or "")
                        item["maxWeek"] = int(stage.get("maxWeek") or 0)
                    item["standingsTargetDiscovery"] = target
                    log(
                        f"{season}: lig arşivinden puan aşaması bulundu: "
                        + ", ".join(
                            f"{stage.get('label')}({stage.get('expectedMatches')} maç)"
                            for stage in stages
                        )
                    )
                else:
                    log(
                        f"{season}: puan hedefi bulunamadı "
                        f"({target.get('error', 'bilinmeyen hata')})"
                    )
    return sorted(by_discovered.values(), key=lambda value: str(value.get("season")), reverse=True)


def fetch_season(choice: dict[str, str | int], club_url: str, cache_dir: Path,
                 shared_fields: dict[str, str], shared_cookies: dict[str, str],
                 timeout: float, attempts: int, delay: float, force: bool) -> dict[str, Any]:
    season = str(choice["season"])
    cache_file = cache_dir / f"{season}.html"
    cached_pages = cached_fixture_pages(cache_dir, season) if not force else None
    if cached_pages:
        result = merge_fixture_pages(
            cached_pages,
            season,
            club_url,
            expected_pages=len(cached_pages),
        )
        result["cache"] = True
        return result

    session = make_session(shared_cookies)
    try:
        # En hızlı yol: ilk GET'in ViewState'i ile doğrudan Ara düğmesini gönder.
        response = request(
            session,
            "POST",
            club_url,
            data=apply_selection(shared_fields, choice, button=True),
            timeout=timeout,
            attempts=attempts,
            delay=delay,
        )
        raw = decode_response(response)
        if selected_season(raw) != season:
            # OEM/eski ASP.NET kurulumlarında önce RadComboBox TextChange gerekebilir.
            fresh = request(session, "GET", club_url, data=None, timeout=timeout, attempts=attempts, delay=delay)
            first_raw = decode_response(fresh)
            changed = request(
                session,
                "POST",
                club_url,
                data=apply_selection(form_fields(first_raw), choice, button=False),
                timeout=timeout,
                attempts=attempts,
                delay=delay,
            )
            changed_raw = decode_response(changed)
            response = request(
                session,
                "POST",
                club_url,
                data=apply_selection(form_fields(changed_raw), choice, button=True),
                timeout=timeout,
                attempts=attempts,
                delay=delay,
            )
            raw = decode_response(response)

        if selected_season(raw) != season:
            raise RuntimeError(f"sezon seçimi doğrulanamadı: beklenen={season}, gelen={selected_season(raw)}")
        pages = [raw]
        expected_pages = fixture_page_count(raw)
        current_raw = raw
        previous_ids = set(extract_fixture_result(raw, season, club_url).get("matchIds", []))
        pagination_complete = True
        pagination_error = ""
        pagination_strategies: list[str] = []
        for page in range(2, expected_pages + 1):
            advanced = False
            attempted: list[str] = []
            for action in fixture_page_actions(current_raw, page):
                attempted.append(action["source"])
                page_data = form_fields(current_raw)
                page_data.pop(SEARCH_BUTTON, None)
                if action.get("submitName"):
                    page_data["__EVENTTARGET"] = ""
                    page_data["__EVENTARGUMENT"] = ""
                    page_data[action["submitName"]] = action.get("submitValue", "")
                else:
                    page_data["__EVENTTARGET"] = action["target"]
                    page_data["__EVENTARGUMENT"] = action.get("argument", "")
                try:
                    page_response = request(
                        session,
                        "POST",
                        club_url,
                        data=page_data,
                        timeout=timeout,
                        attempts=attempts,
                        delay=delay,
                    )
                except Exception:
                    continue
                candidate_raw = decode_response(page_response)
                if selected_season(candidate_raw) != season:
                    continue
                page_ids = set(
                    extract_fixture_result(candidate_raw, season, club_url).get("matchIds", [])
                )
                if page_ids and page_ids != previous_ids:
                    current_raw = candidate_raw
                    previous_ids = page_ids
                    pages.append(current_raw)
                    pagination_strategies.append(action["source"])
                    advanced = True
                    break
            if not advanced:
                pagination_complete = False
                pagination_error = (
                    f"fikstür sayfalaması ilerlemedi: sezon={season}, "
                    f"sayfa={page}/{expected_pages}, denenen={','.join(dict.fromkeys(attempted))}"
                )
                # İlk sayfadaki doğrulanmış maçları kaybetmek, kısmi ama dürüst
                # bir sonuçtan daha kötüdür. Eksik durum rapora yazılır.
                break

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        for page, page_raw in enumerate(pages, start=1):
            page_path = cache_file if page == 1 else cache_dir / f"{season}_page_{page:02d}.html"
            page_path.write_text(page_raw, encoding="utf-8")
        result = merge_fixture_pages(
            pages,
            season,
            club_url,
            expected_pages=expected_pages,
            pagination_complete=pagination_complete,
            pagination_error=pagination_error,
            pagination_strategies=pagination_strategies,
        )
        result["cache"] = False
        return result
    finally:
        session.close()


def ensure_seed_item(seed: dict[str, Any], season: str) -> dict[str, Any]:
    for item in seed.setdefault("seasons", []):
        if item.get("season") == season:
            return item
    item = {
        "season": season,
        "pageIds": [29, 528],
        "knownMatchIds": [],
        "targetUrls": [],
        "tryWeeklyStandings": True,
        "professionalStatus": "professional",
    }
    seed["seasons"].append(item)
    return item


def merge_results(seed: dict[str, Any], choices: list[dict[str, str | int]],
                  results: list[dict[str, Any]]) -> dict[str, Any]:
    runtime = copy.deepcopy(seed)
    by_result = {str(item["season"]): item for item in results if not item.get("error")}

    # Registry'deki TFF URL'lerini HTTP'ye indir; TFF'nin HTTPS zinciri bazı Nix
    # kurulumlarında eksik sertifika yüzünden başarısız olabiliyor.
    for item in runtime.get("seasons", []):
        item["targetUrls"] = [tff_http(url) for url in item.get("targetUrls", []) if str(url).strip()]

    for choice in choices:
        season = str(choice["season"])
        item = ensure_seed_item(runtime, season)
        result = by_result.get(season)
        if not result:
            plan = item.get("tffPlan") or {}
            has_exact_target = bool(
                item.get("knownMatchIds") or item.get("targetUrls")
                or item.get("targetPageID") or plan.get("pageID")
            )
            if not has_exact_target:
                item["skipTff"] = True
                item["skipReason"] = "club_fixture_discovery_failed_no_exact_fast_target"
                probe = item.get("legacyPageIdProbe") or item.get("legacyPageIDProbe")
                if isinstance(probe, dict):
                    probe["enabled"] = False
            continue
        ids = sorted(set(str(x) for x in item.get("knownMatchIds", [])) | set(result.get("matchIds", [])), key=int)
        targets = sorted(set(tff_http(url) for url in item.get("targetUrls", []))
                         | set(tff_http(url) for url in result.get("targetUrls", [])))
        item["knownMatchIds"] = ids
        fixture_by_id = {
            str(fixture.get("id")): fixture
            for fixture in item.get("knownFixtures", [])
            if isinstance(fixture, dict) and fixture.get("id")
        }
        for fixture in result.get("fixtures", []):
            if isinstance(fixture, dict) and fixture.get("id"):
                fixture_by_id[str(fixture["id"])] = fixture
        item["knownFixtures"] = [fixture_by_id[mid] for mid in sorted(fixture_by_id, key=int)]
        item["targetUrls"] = targets
        if ids:
            # Tam kulüp fikstürü bütün lig/kupa maçlarını kapsar ve en hızlı
            # yoldur. Kısmi sayfalama ise exact sezon sayfasıyla tamamlanmalıdır.
            item["knownOnly"] = bool(result.get("paginationComplete", True))
            item["skipTff"] = False
            item["skipReason"] = ""
            item["noTffRecord"] = False
            item["amateurSeason"] = False
            item["professionalStatus"] = "professional"
        elif not targets and not item.get("targetPageID") and not (item.get("tffPlan") or {}).get("pageID"):
            # Hızlı senkron kör pageID araması yapmaz. Gelecek sezon veya TFF'de
            # kaydı olmayan dönem raporda görünür ve sonraki çalışmada yeniden denenir.
            item["skipTff"] = True
            item["skipReason"] = "club_fixture_discovery_returned_no_matches_or_target"
            probe = item.get("legacyPageIdProbe") or item.get("legacyPageIDProbe")
            if isinstance(probe, dict):
                probe["enabled"] = False
        if int(result.get("maxWeek") or 0) > 0:
            item["maxWeek"] = max(int(item.get("maxWeek") or 0), int(result["maxWeek"]))
        item["clubFixtureDiscovery"] = {
            "source": DEFAULT_CLUB_URL,
            "matchCount": len(ids),
            "targetUrlCount": len(targets),
            "fixturePages": int(result.get("fixturePages") or 1),
            "fixturePagesExpected": int(result.get("fixturePagesExpected") or 1),
            "paginationComplete": bool(result.get("paginationComplete", True)),
            "paginationError": str(result.get("paginationError") or ""),
            "discoveredAt": now(),
        }

    choice_order = [str(choice["season"]) for choice in choices]
    remaining = [str(x) for x in runtime.get("runOrder", []) if str(x) not in choice_order]
    runtime["runOrder"] = choice_order + remaining
    runtime["policy"] = "TFF-only; club fixture postback discovery; concurrent detail fetch; cached/resumable"
    runtime["generatedAt"] = now()
    return runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="TFF kulüp sayfasından Balıkesirspor sezon/maç kimliklerini keşfet")
    parser.add_argument("--registry", default="tools/tff/balkes_tff_seed_registry.json")
    parser.add_argument("--output", default=".cache/tff/runtime_registry.json")
    parser.add_argument("--report", default="generated/tff-data/reports/club_fixture_discovery.json")
    parser.add_argument("--cache-dir", default=".cache/tff/club_fixtures")
    parser.add_argument("--raw-dir", default=".cache/tff/raw")
    parser.add_argument("--target-cache-dir", default=".cache/tff/standings_targets")
    parser.add_argument("--club-url", default=DEFAULT_CLUB_URL)
    parser.add_argument("--season", action="append", help="Yalnızca bu sezon; birden çok kez verilebilir")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--delay", type=float, default=0.08)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()

    seed = read_json(args.registry, {})
    if not isinstance(seed, dict):
        raise SystemExit(f"Registry okunamadı: {args.registry}")

    club_url = tff_http(args.club_url)
    base_session = make_session()
    base_response = request(
        base_session, "GET", club_url, data=None,
        timeout=args.timeout, attempts=args.attempts, delay=args.delay,
    )
    base_raw = decode_response(base_response)
    choices = season_choices(base_raw)
    if args.season:
        wanted = set(args.season)
        choices = [choice for choice in choices if choice["season"] in wanted]
    if not choices:
        raise SystemExit("TFF kulüp sayfasında sezon seçeneği bulunamadı.")

    shared_fields = form_fields(base_raw)
    shared_cookies = requests.utils.dict_from_cookiejar(base_session.cookies)
    base_session.close()
    cache_dir = Path(args.cache_dir)
    results: list[dict[str, Any]] = []
    log(f"TFF sezon keşfi başladı: sezon={len(choices)}, workers={max(1, args.workers)}")

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                fetch_season, choice, club_url, cache_dir, shared_fields, shared_cookies,
                args.timeout, args.attempts, args.delay, args.force,
            ): str(choice["season"])
            for choice in choices
        }
        completed = 0
        for future in as_completed(futures):
            season = futures[future]
            completed += 1
            try:
                result = future.result()
                results.append(result)
                log(
                    f"{completed}/{len(choices)} {season}: maç={len(result['matchIds'])}, "
                    f"fikstürSayfası={result.get('fixturePages', 1)}, "
                    f"tam={result.get('paginationComplete', True)}, "
                    f"hedef={len(result['targetUrls'])}, cache={result['cache']}"
                )
            except Exception as exc:
                results.append({"season": season, "error": str(exc), "matchIds": [], "targetUrls": []})
                log(f"{completed}/{len(choices)} {season}: HATA {exc}")

    results.sort(key=lambda item: str(item["season"]), reverse=True)
    runtime = merge_results(seed, choices, results)
    standings_targets = enrich_standings_targets(
        runtime,
        results,
        Path(args.raw_dir),
        Path(args.target_cache_dir),
        args.workers,
        args.timeout,
        args.attempts,
        args.delay,
        args.force,
    )
    write_json(args.output, runtime)
    report = {
        "discoveryVersion": STANDINGS_TARGET_CACHE_VERSION,
        "generatedAt": now(),
        "clubUrl": club_url,
        "seasonsRequested": len(choices),
        "seasonsSucceeded": sum(1 for item in results if not item.get("error")),
        "seasonsWithMatches": sum(1 for item in results if item.get("matchIds")),
        "uniqueMatchIds": len({mid for item in results for mid in item.get("matchIds", [])}),
        "errors": [{"season": item["season"], "error": item["error"]} for item in results if item.get("error")],
        "paginationFailures": [
            {
                "season": item["season"],
                "pagesFetched": item.get("fixturePages", 0),
                "pagesExpected": item.get("fixturePagesExpected", 0),
                "error": item.get("paginationError", ""),
            }
            for item in results
            if not item.get("error") and not item.get("paginationComplete", True)
        ],
        "results": results,
        "standingsTargets": standings_targets,
        "runtimeRegistry": str(args.output),
    }
    write_json(args.report, report)
    log(f"Keşif bitti: sezon={report['seasonsSucceeded']}/{report['seasonsRequested']}, benzersizMaç={report['uniqueMatchIds']}")
    if report["uniqueMatchIds"] == 0 and not args.allow_empty:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
