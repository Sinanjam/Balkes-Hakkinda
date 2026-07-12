#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Balkes TFF Factory v2.3 targeted perfect details no-standings

Bu sürümün hedefi:
- Puan tablosu/standings ÇEKMEZ.
- TFF maç detay sayfasından takım/skor/tarih alanlarını HTML id/class üzerinden parse eder.
- Önce selectedIds/knownIds adaylarını dener; selected yoksa allDiscovered fallback yapar.
- Non-Balkes adaylarını raporlayarak eler.
- Score span'leri ayrı ayrı geldiği için "2-1" regex'ine bağımlı kalmaz.
- Hiç maç üretmezse fail eder ve main'e boş data basmaz.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

TFF = os.environ.get("TFF_BASE_URL", "http://www.tff.org/Default.aspx")
FETCH_TIMEOUT = float(os.environ.get("TFF_FETCH_TIMEOUT", "24"))
FAST_SKIP_HTTP_CODES = {502, 503, 504}
FETCH_LAST_ERROR_BY_PATH: dict[str, str] = {}
FACTORY_VERSION = "v5-professional-only-resilient"
TEAM_CANONICAL = "Balıkesirspor"
DATA_BASE_URL = os.environ.get(
    "BALKES_DATA_BASE_URL",
    "https://raw.githubusercontent.com/Sinanjam/Balkes-Hakkinda/main/data/",
).rstrip("/") + "/"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def read_json(path: Path | str, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path | str, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def tff_url(**params: Any) -> str:
    return TFF + "?" + urllib.parse.urlencode(params)


def decode_bytes(raw: bytes, content_type: str = "") -> str:
    encs = []
    m = re.search(r"charset=([A-Za-z0-9_\-]+)", content_type or "", re.I)
    if m:
        encs.append(m.group(1))
    head = raw[:4096].decode("ascii", errors="ignore")
    m2 = re.search(r"charset=['\"]?([A-Za-z0-9_\-]+)", head, re.I)
    if m2:
        encs.append(m2.group(1))
    encs.extend(["windows-1254", "iso-8859-9", "utf-8", "latin-1"])
    best, score = "", 10**9
    for enc in dict.fromkeys(encs):
        try:
            s = raw.decode(enc, errors="replace")
            bad = s.count("\ufffd") + s.count("ï¿½") * 2
            if bad < score:
                best, score = s, bad
        except Exception:
            pass
    return best or raw.decode("utf-8", errors="replace")


def fetch(url: str, path: Path, sleep_s: float = 1.0, force: bool = False) -> tuple[bool, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    FETCH_LAST_ERROR_BY_PATH[str(path)] = ""
    if path.exists() and path.stat().st_size > 200 and not force:
        return True, path.read_text(encoding="utf-8", errors="replace")
    last = ""
    for attempt in range(1, 3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 BalkesTFFFactory-v26-gateway-guard/1.0",
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
            })
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as res:
                body = res.read()
                ctype = res.headers.get("Content-Type", "")
            text = decode_bytes(body, ctype)
            path.write_text(text, encoding="utf-8")
            if sleep_s:
                time.sleep(sleep_s)
            FETCH_LAST_ERROR_BY_PATH[str(path)] = ""
            return True, text
        except urllib.error.HTTPError as exc:
            last = f"HTTP Error {exc.code}: {exc.reason}"
            code_key = f"http_{exc.code}"
            FETCH_LAST_ERROR_BY_PATH[str(path)] = code_key
            if int(exc.code) in FAST_SKIP_HTTP_CODES:
                # TFF legacy archive often returns 502/503/504 on dead group branches.
                # Retrying the same toxic URL costs minutes and never increases accuracy.
                log(f"fetch hızlı atla: {url} -> {last}")
                path.with_suffix(path.suffix + ".error.txt").write_text(last, encoding="utf-8")
                return False, ""
            log(f"fetch hata {attempt}/2: {url} -> {last}")
            time.sleep(max(2.0, sleep_s * attempt))
        except Exception as exc:
            last = str(exc)
            err_norm = str(exc).lower()
            FETCH_LAST_ERROR_BY_PATH[str(path)] = "timeout" if "timed out" in err_norm or "timeout" in err_norm else "error"
            log(f"fetch hata {attempt}/2: {url} -> {last}")
            time.sleep(max(2.0, sleep_s * attempt))
    path.with_suffix(path.suffix + ".error.txt").write_text(last, encoding="utf-8")
    return False, ""


def fix_mojibake(s: Any) -> str:
    s = str(s or "")
    s = s.replace("ï¿½", "İ").replace("\ufffd", "İ").replace("�", "İ")
    repl = {
        "Ä°": "İ", "Ä±": "ı", "ÅŸ": "ş", "Åž": "Ş", "ÄŸ": "ğ", "Äž": "Ğ",
        "Ã¼": "ü", "Ãœ": "Ü", "Ã¶": "ö", "Ã–": "Ö", "Ã§": "ç", "Ã‡": "Ç",
        "&nbsp;": " ",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    return html.unescape(s)


def norm(s: Any) -> str:
    s = fix_mojibake(s).lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.translate(str.maketrans({
        "ı": "i", "İ": "i", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
        "ş": "s", "Ş": "s", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"
    }))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def is_balkes(s: Any) -> bool:
    n = norm(s)
    if "balkes" in n:
        return True
    if "balikesirspor" in n or "balikesir spor" in n:
        return True
    if "balikes" in n and "spor" in n:
        return True
    return False


NON_PROFESSIONAL_MARKERS = (
    "paf takimi", "rezerv takim", "akademi", "altyapi", "gelisim ligi",
    "genclik", "kadin", "futsal", "plaj", "engelli", "bal takimi",
    "bolgesel amator", "amator takim",
)


def professional_competition_status(value: Any) -> tuple[bool, str]:
    """Müsabakanın Balıkesirspor profesyonel A takımına ait olup olmadığını söyler.

    TFF'nin yeni sayfaları ``(Profesyonel Takım)`` etiketini taşır. Çok eski
    sayfalarda bu etiket bulunmayabildiği için, açık bir altyapı/amateur işareti
    yoksa kayıt ``inferred`` olarak kabul edilir; kirli U14-U21/PAF/BAL verisi
    hiçbir koşulda uygulama çıktısına alınmaz.
    """
    text = norm(value)
    if not text:
        return False, "competition_missing"
    if any(marker in text for marker in NON_PROFESSIONAL_MARKERS):
        return False, "non_professional_marker"
    if re.search(r"(?:^| )u ?(?:13|14|15|16|17|18|19|20|21|23)(?: |$)", text):
        return False, "youth_age_group"
    if "profesyonel takim" in text or re.search(r"(?:^| )a takim(?:i)?(?: |$)", text):
        return True, "explicit_professional"
    return True, "inferred_senior"


def is_professional_competition(value: Any) -> bool:
    return professional_competition_status(value)[0]


def clean_text(s: Any) -> str:
    return re.sub(r"\s+", " ", fix_mojibake(s)).strip()


def clean_team(s: Any) -> str:
    s = clean_text(s)
    if is_balkes(s):
        return TEAM_CANONICAL
    return s


def soup_from_html(raw: str):
    return BeautifulSoup(raw, "html.parser") if BeautifulSoup else None


def text_from_html(raw: str) -> str:
    soup = soup_from_html(raw)
    if soup:
        for t in soup(["script", "style", "noscript"]):
            t.decompose()
        return "\n".join(clean_text(x) for x in soup.get_text("\n").splitlines() if clean_text(x))
    raw = re.sub(r"<[^>]+>", "\n", raw)
    return "\n".join(clean_text(x) for x in raw.splitlines() if clean_text(x))


def extract_ids(raw: str, key: str = "macId") -> list[str]:
    return sorted(set(re.findall(rf"[?&]{re.escape(key)}=(\d+)", raw, re.I)), key=lambda x: int(x))


def extract_param(raw: str, key: str) -> list[str]:
    return sorted(set(re.findall(rf"[?&]{re.escape(key)}=(\d+)", raw, re.I)), key=lambda x: int(x))


def extract_balkes_ids(raw: str) -> list[str]:
    ids: set[str] = set()
    soup = soup_from_html(raw)
    if soup:
        for a in soup.find_all("a", href=True):
            href = html.unescape(a.get("href") or "")
            m = re.search(r"[?&]macId=(\d+)", href, re.I)
            if not m:
                continue
            parent = a.find_parent("tr") or a.find_parent(["div", "li", "p", "td"]) or a.parent
            ctx = clean_text(parent.get_text(" ", strip=True) if parent else a.get_text(" ", strip=True))
            # TFF bazı fikstür satırlarında link metni boş olabiliyor; küçük çevre fallback.
            if is_balkes(ctx):
                ids.add(m.group(1))
        # Parser çalıştığında ham HTML çevre penceresi kullanılmaz. Bu pencere
        # komşu satırdaki Balıkesirspor adını görüp yüzlerce ilgisiz macId'yi
        # seçebiliyordu.
        return sorted(ids, key=lambda x: int(x))
    # BeautifulSoup bulunmayan minimal ortamlarda satır bazlı güvenli fallback.
    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", raw, re.I | re.S):
        if not is_balkes(re.sub(r"<[^>]+>", " ", row)):
            continue
        ids.update(re.findall(r"[?&]macId=(\d+)", html.unescape(row), re.I))
    return sorted(ids, key=lambda x: int(x))


def parse_date_any(s: Any) -> str:
    s = fix_mojibake(s)
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d).isoformat()
        except Exception:
            return ""
    ay = {
        "ocak": 1, "subat": 2, "şubat": 2, "mart": 3, "nisan": 4, "mayis": 5, "mayıs": 5,
        "haziran": 6, "temmuz": 7, "agustos": 8, "ağustos": 8, "eylul": 9, "eylül": 9,
        "ekim": 10, "kasim": 11, "kasım": 11, "aralik": 12, "aralık": 12,
    }
    m = re.search(r"\b(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})\b", s)
    if m:
        d = int(m.group(1)); mon = norm(m.group(2)); y = int(m.group(3))
        if mon in ay:
            return date(y, ay[mon], d).isoformat()
    return ""


def parse_time_any(s: Any) -> str:
    s = fix_mojibake(s)
    # Tarih içindeki 07.09 gibi parçaları saat sanmamak için önce "tarih - saat" formunu yakala.
    m = re.search(r"\b\d{1,2}[./]\d{1,2}[./]\d{4}\s*[-–]\s*([01]?\d|2[0-3])[:.](\d{2})\b", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    # Genel saat formu: nokta yerine tercihen iki nokta üst üste.
    m = re.search(r"\b([01]?\d|2[0-3]):(\d{2})\b", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    # Noktalı saat için tarih biçimiyle çakışmayan durumları al.
    cleaned = re.sub(r"\b\d{1,2}[./]\d{1,2}[./]\d{4}\b", " ", s)
    m = re.search(r"\b([01]?\d|2[0-3])\.(\d{2})\b", cleaned)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else ""


def season_bounds(season: str, seed: dict[str, Any]) -> tuple[str, str]:
    guard = (seed.get("seasonDateGuard") or {}).get(season) or {}
    if guard.get("start") and guard.get("end"):
        return guard["start"], guard["end"]
    y = int(season[:4])
    return f"{y}-07-01", f"{y+1}-06-30"


def date_in_season(iso_date: str, season: str, seed: dict[str, Any]) -> bool:
    if not iso_date:
        return False
    a, b = season_bounds(season, seed)
    return a <= iso_date <= b


def classify_type(*parts: Any) -> tuple[str, str]:
    n = norm(" ".join(str(x or "") for x in parts))
    if any(k in n for k in ["play off", "playoff", "play offs", "playoffs", "final musabakalari"]):
        return "playoff", "Play-off"
    if any(k in n for k in ["ziraat", "turkiye kupasi", "turkiye kupas", "ztk", " kupa "]):
        return "cup", "Ziraat Türkiye Kupası"
    if "hazirlik" in n or "friendly" in n:
        return "friendly_or_unknown", "Hazırlık/Bilinmeyen"
    return "league", "Lig"


def first_by_id_contains(soup, token: str):
    if not soup:
        return None
    token = token.lower()
    for tag in soup.find_all(True):
        tid = " ".join([str(tag.get("id") or ""), " ".join(tag.get("class") or [])]).lower()
        if token in tid:
            return tag
    return None


def all_by_id_contains(soup, token: str):
    if not soup:
        return []
    token = token.lower()
    out = []
    for tag in soup.find_all(True):
        tid = " ".join([str(tag.get("id") or ""), " ".join(tag.get("class") or [])]).lower()
        if token in tid:
            out.append(tag)
    return out


def parse_int_text(s: Any):
    m = re.search(r"-?\d+", clean_text(s))
    return int(m.group(0)) if m else None


def teams_from_soup(soup, txt: str) -> tuple[str, str]:
    home = away = ""
    t1 = first_by_id_contains(soup, "lnkTakim1")
    t2 = first_by_id_contains(soup, "lnkTakim2")
    if t1:
        home = clean_team(t1.get_text(" ", strip=True))
    if t2:
        away = clean_team(t2.get_text(" ", strip=True))
    if home and away:
        return home, away

    # Legacy TFF pages sometimes do not expose lnkTakim1/lnkTakim2 ids.
    # In those pages the most reliable fallback is the page title / first lines:
    #   "EV SAHİBİ 2-1 DEPLASMAN - Maç Detayları ..."
    # or occasionally:
    #   "EV SAHİBİ - DEPLASMAN"
    candidates: list[str] = []
    if soup:
        if soup.title and soup.title.string:
            candidates.append(clean_text(soup.title.string))
        for meta_name in ["description", "og:title"]:
            tag = soup.find("meta", attrs={"name": meta_name}) or soup.find("meta", attrs={"property": meta_name})
            if tag and tag.get("content"):
                candidates.append(clean_text(tag.get("content")))
    candidates.extend([x for x in txt.splitlines()[:80] if is_balkes(x)])

    def strip_tail(line: str) -> str:
        line = clean_text(line)
        line = re.sub(r"\s+-\s+(Maç|Mac)\s+Detay.*$", "", line, flags=re.I)
        line = re.sub(r"\s+\|\s+.*$", "", line)
        return line.strip(" -–|")

    for raw_line in candidates:
        line = strip_tail(raw_line)
        if not is_balkes(line):
            continue
        # Score-title form: TEAM A 2-1 TEAM B
        m = re.match(r"^(.{2,80}?)\s+\d{1,2}\s*[-–]\s*\d{1,2}\s+(.{2,80}?)$", line)
        if m:
            h, a = clean_team(m.group(1)), clean_team(m.group(2))
            if h and a and (is_balkes(h) or is_balkes(a)):
                return h, a
        # Separator-title form: TEAM A - TEAM B (avoid splitting score hyphen)
        parts = re.split(r"\s+[-–]\s+", line)
        parts = [clean_team(x) for x in parts if clean_team(x)]
        if len(parts) >= 2:
            h, a = parts[0], parts[1]
            if h and a and (is_balkes(h) or is_balkes(a)):
                return h, a

    return home, away

def score_from_soup(soup, txt: str) -> tuple[Any, Any, str, bool]:
    h = a = None
    # Modern TFF detay sayfası:
    # lblTakim1Skor -> ev skoru, Label12/lblTakim2Skor -> deplasman skoru.
    t1 = first_by_id_contains(soup, "lblTakim1Skor")
    if t1:
        h = parse_int_text(t1.get_text(" ", strip=True))
    t2 = first_by_id_contains(soup, "lblTakim2Skor") or first_by_id_contains(soup, "Label12")
    if t2:
        a = parse_int_text(t2.get_text(" ", strip=True))

    if h is None or a is None:
        # MacDetaySayi sınıfındaki iki sayı.
        nums = []
        for tag in all_by_id_contains(soup, "MacDetaySayi"):
            v = parse_int_text(tag.get_text(" ", strip=True))
            if v is not None:
                nums.append(v)
        if len(nums) >= 2:
            h, a = nums[0], nums[1]

    if h is None or a is None:
        m = re.search(r"\b(\d{1,2})\s*[-–]\s*(\d{1,2})\b", txt)
        if m:
            h, a = int(m.group(1)), int(m.group(2))

    played = h is not None and a is not None
    return h, a, f"{h}-{a}" if played else "", played


def parse_match_code(soup, txt: str) -> str:
    tag = first_by_id_contains(soup, "lblKod")
    if tag:
        return clean_text(tag.get_text(" ", strip=True))
    m = re.search(r"(?:Müsabaka|Musabaka|Maç|Mac)\s*Kodu\s*:?\s*(\d+)", txt, re.I)
    return m.group(1) if m else ""


def parse_date_time(soup, txt: str) -> tuple[str, str]:
    tag = first_by_id_contains(soup, "lblTarih")
    raw = tag.get_text(" ", strip=True) if tag else txt
    return parse_date_any(raw), parse_time_any(raw)


def parse_competition(soup, txt: str) -> str:
    tag = first_by_id_contains(soup, "lblOrganizasyonAdi")
    return clean_text(tag.get_text(" ", strip=True)) if tag else ""


def parse_stadium(soup) -> str:
    tag = first_by_id_contains(soup, "lnkStad")
    return clean_text(tag.get_text(" ", strip=True)) if tag else ""


def parse_officials(soup, txt: str) -> list[dict[str, str]]:
    officials = []
    if soup:
        for a in soup.find_all("a", href=True):
            href = a.get("href") or ""
            raw = clean_text(a.get_text(" ", strip=True))
            if "hakemId=" not in href and "(Hakem)" not in raw and "Yardımcı Hakem" not in raw:
                continue
            m = re.match(r"(.+?)\((.+?)\)\s*$", raw)
            if m:
                name, role = clean_text(m.group(1)), clean_text(m.group(2))
            else:
                name, role = raw, "Hakem"
            officials.append({"role": role, "name": name})
    if officials:
        return officials

    patterns = [
        ("Hakem", r"\bHakem\s*:?\s*([A-ZÇĞİÖŞÜa-zçğıöşü .'-]{4,80})"),
        ("1. Yardımcı Hakem", r"(?:1\.?\s*Yardımcı Hakem|1\.?\s*Yardimci Hakem)\s*:?\s*([A-ZÇĞİÖŞÜa-zçğıöşü .'-]{4,80})"),
        ("2. Yardımcı Hakem", r"(?:2\.?\s*Yardımcı Hakem|2\.?\s*Yardimci Hakem)\s*:?\s*([A-ZÇĞİÖŞÜa-zçğıöşü .'-]{4,80})"),
        ("Gözlemci", r"\bGözlemci\s*:?\s*([A-ZÇĞİÖŞÜa-zçğıöşü .'-]{4,80})"),
    ]
    for role, pat in patterns:
        m = re.search(pat, txt, re.I)
        if m:
            officials.append({"role": role, "name": clean_text(m.group(1))})
    return officials



def parse_sections_raw(txt: str) -> dict[str, str]:
    lines = txt.splitlines()
    sections = {"full_text_excerpt": txt[:30000]}
    picks = {
        "officials_raw": ["hakem", "gozlemci", "gözlemci", "temsilci"],
        "lineups_raw": ["ilk 11", "yedek", "teknik sorumlu"],
        "events_raw": ["sari kart", "sarı kart", "kirmizi kart", "kırmızı kart", "oyuna giren", "oyundan cikan", "oyundan çıkan", "gol", " dk", "penalt"],
    }
    for key, needles in picks.items():
        hits = [x for x in lines if any(n in norm(x) for n in needles)]
        if hits:
            sections[key] = "\n".join(hits[:400])
    return sections


def parse_person_id(href: Any) -> str:
    m = re.search(r"(?:kisiId|hakemId|personId|oyuncuId)=(\d+)", str(href or ""), re.I)
    return m.group(1) if m else ""


def parse_minute_value(raw: Any) -> tuple[Any, str]:
    text = clean_text(raw)
    n = norm(text)
    m = re.search(r"\b(\d{1,3})\s*(?:\.\s*)?(?:dk|dakika|'|’)?\b", n)
    if m:
        return int(m.group(1)), text
    if n in {"ms", "mac sonu", "maç sonu"} or "ms" == n:
        return "MS", text
    if "devre" in n:
        return "HT", text
    return None, text


def repeat_groups(soup, team_no: int, rpt: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    if not soup:
        return groups
    pattern = re.compile(rf"grdTakim{team_no}_{rpt}_ctl(\d+)_([^\s]+)$", re.I)
    for tag in soup.find_all(True):
        tid = str(tag.get("id") or "")
        m = pattern.search(tid)
        if not m:
            continue
        idx, field = m.group(1), m.group(2)
        if idx == "00":
            continue
        g = groups.setdefault(idx, {})
        txt = clean_text(tag.get_text(" ", strip=True))
        if txt:
            g[field] = txt
        href = tag.get("href")
        if href:
            g[field + "Href"] = href
            pid = parse_person_id(href)
            if pid:
                g[field + "Id"] = pid
        if tag.name == "img":
            if tag.get("alt"):
                g[field + "Alt"] = clean_text(tag.get("alt"))
            if tag.get("src"):
                g[field + "Src"] = str(tag.get("src"))
    return groups


def player_obj(name: Any, number: Any = "", href: Any = "", role: str = "") -> dict[str, Any]:
    name = clean_text(name)
    if not name:
        return {}
    name = re.sub(r",?\s*\d{1,3}\s*\.\s*dk.*$", "", name, flags=re.I).strip()
    number_text = clean_text(number).replace(".", "")
    num = parse_int_text(number_text)
    obj: dict[str, Any] = {"name": name}
    if num is not None:
        obj["number"] = num
        obj["shirt_no"] = str(num)
    pid = parse_person_id(href)
    if pid:
        obj["tffPersonId"] = pid
    if role:
        obj["role"] = role
    return obj


def parse_roster_group(soup, team_no: int, rpt: str) -> list[dict[str, Any]]:
    out = []
    for idx, g in sorted(repeat_groups(soup, team_no, rpt).items(), key=lambda kv: int(kv[0])):
        name = g.get("lnkOyuncu") or g.get("lblOyuncu") or g.get("lnkTeknikSorumlu") or g.get("lblTeknikSorumlu")
        href = g.get("lnkOyuncuHref") or g.get("lblOyuncuHref") or g.get("lnkTeknikSorumluHref") or g.get("lblTeknikSorumluHref") or ""
        number = g.get("formaNo") or ""
        obj = player_obj(name, number, href)
        if obj:
            out.append(obj)
    return out


def lineup_side(team: str, starting: list[dict[str, Any]], subs: list[dict[str, Any]], staff: list[dict[str, Any]], sections: dict[str, str]) -> dict[str, Any]:
    coach = ""
    if staff:
        coach = clean_text(staff[0].get("name", ""))
    return {
        "team": team,
        "starting11": starting,
        "substitutes": subs,
        "technicalStaff": staff,
        "coach": coach,
        "raw": sections.get("lineups_raw", ""),
    }


def parse_lineups_structured(soup, home: str, away: str, sections: dict[str, str]) -> dict[str, Any]:
    home_start = parse_roster_group(soup, 1, "rptKadrolar")
    home_subs = parse_roster_group(soup, 1, "rptYedekler")
    home_staff = parse_roster_group(soup, 1, "rptTeknikKadro")
    away_start = parse_roster_group(soup, 2, "rptKadrolar")
    away_subs = parse_roster_group(soup, 2, "rptYedekler")
    away_staff = parse_roster_group(soup, 2, "rptTeknikKadro")
    return {
        "home": lineup_side(home, home_start, home_subs, home_staff, sections),
        "away": lineup_side(away, away_start, away_subs, away_staff, sections),
    }


def parse_goal_text(raw: Any) -> tuple[str, Any, str, str]:
    text = clean_text(raw)
    goal_type = ""
    mtype = re.search(r"\(([^)]+)\)", text)
    if mtype:
        goal_type = clean_text(mtype.group(1))
    no_type = re.sub(r"\([^)]*\)", "", text).strip()
    minute, minute_raw = parse_minute_value(no_type)
    name = re.sub(r",?\s*\d{1,3}\s*\.\s*dk.*$", "", no_type, flags=re.I).strip(" ,-")
    return clean_text(name), minute, minute_raw, goal_type


def parse_goals(soup, team_no: int, team: str) -> list[dict[str, Any]]:
    out = []
    for idx, g in sorted(repeat_groups(soup, team_no, "rptGoller").items(), key=lambda kv: int(kv[0])):
        raw = g.get("lblGol") or g.get("g") or ""
        name, minute, minute_raw, goal_type = parse_goal_text(raw)
        if not name:
            continue
        href = g.get("lblGolHref") or ""
        obj: dict[str, Any] = {"type": "goal", "team": team, "player": name, "scorer": name, "raw": raw}
        if minute is not None:
            obj["minute"] = minute
        if minute_raw:
            obj["minuteRaw"] = minute_raw
        if goal_type:
            obj["goalType"] = goal_type
        pid = parse_person_id(href)
        if pid:
            obj["tffPersonId"] = pid
        out.append(obj)
    return out


def parse_cards(soup, team_no: int, team: str) -> list[dict[str, Any]]:
    out = []
    for idx, g in sorted(repeat_groups(soup, team_no, "rptKartlar").items(), key=lambda kv: int(kv[0])):
        name = clean_text(g.get("lblKart") or "")
        if not name:
            continue
        minute, minute_raw = parse_minute_value(g.get("d") or g.get("k") or "")
        alt = g.get("kAlt") or ""
        src = g.get("kSrc") or ""
        card = "yellow"
        if "kirmizi" in norm(alt) or "kirmizi" in norm(src) or "red" in norm(src):
            card = "red"
        obj: dict[str, Any] = {"type": f"{card}_card", "card": card, "team": team, "player": name}
        if minute is not None:
            obj["minute"] = minute
        if minute_raw:
            obj["minuteRaw"] = minute_raw
        pid = parse_person_id(g.get("lblKartHref") or "")
        if pid:
            obj["tffPersonId"] = pid
        out.append(obj)
    return out


def parse_sub_rows(soup, team_no: int, rpt: str, field: str, minute_field: str) -> list[dict[str, Any]]:
    out = []
    for idx, g in sorted(repeat_groups(soup, team_no, rpt).items(), key=lambda kv: int(kv[0])):
        name = clean_text(g.get(field) or "")
        if not name:
            continue
        minute, minute_raw = parse_minute_value(g.get(minute_field) or "")
        obj: dict[str, Any] = {"player": name, "order": int(idx)}
        if minute is not None:
            obj["minute"] = minute
        if minute_raw:
            obj["minuteRaw"] = minute_raw
        pid = parse_person_id(g.get(field + "Href") or "")
        if pid:
            obj["tffPersonId"] = pid
        out.append(obj)
    return out


def parse_substitutions(soup, team_no: int, team: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    outs = parse_sub_rows(soup, team_no, "rptCikanlar", "lblCikan", "oc")
    ins = parse_sub_rows(soup, team_no, "rptGirenler", "lblGiren", "og")
    subs = []
    events = []
    max_len = max(len(outs), len(ins))
    for i in range(max_len):
        outp = outs[i] if i < len(outs) else {}
        inp = ins[i] if i < len(ins) else {}
        minute = inp.get("minute", outp.get("minute"))
        minute_raw = inp.get("minuteRaw", outp.get("minuteRaw", ""))
        sub: dict[str, Any] = {"team": team, "order": i + 1}
        if minute is not None:
            sub["minute"] = minute
        if minute_raw:
            sub["minuteRaw"] = minute_raw
        if outp:
            sub["playerOut"] = outp.get("player")
            sub["player_out"] = outp.get("player")
            if outp.get("tffPersonId"):
                sub["playerOutTffPersonId"] = outp.get("tffPersonId")
        if inp:
            sub["playerIn"] = inp.get("player")
            sub["player_in"] = inp.get("player")
            if inp.get("tffPersonId"):
                sub["playerInTffPersonId"] = inp.get("tffPersonId")
        if sub.get("playerIn") or sub.get("playerOut"):
            subs.append(sub)
            ev = {"type": "substitution", "team": team, "order": i + 1,
                  "player_in": sub.get("playerIn", ""), "player_out": sub.get("playerOut", ""),
                  "playerIn": sub.get("playerIn", ""), "playerOut": sub.get("playerOut", "")}
            if minute is not None:
                ev["minute"] = minute
            if minute_raw:
                ev["minuteRaw"] = minute_raw
                ev["minute_text"] = minute_raw
            events.append(ev)
            if outp:
                raw_ev = {"type": "substitution_out", "team": team, "player": outp.get("player"), "order": i + 1}
                if minute is not None: raw_ev["minute"] = minute
                if minute_raw: raw_ev["minuteRaw"] = minute_raw
                events.append(raw_ev)
            if inp:
                raw_ev = {"type": "substitution_in", "team": team, "player": inp.get("player"), "order": i + 1}
                if minute is not None: raw_ev["minute"] = minute
                if minute_raw: raw_ev["minuteRaw"] = minute_raw
                events.append(raw_ev)
    return subs, events


def build_players_index_for_match(lineups: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    players: dict[str, dict[str, Any]] = {}
    def add(name: Any, team: Any = "", role: str = "", number: Any = None, pid: str = ""):
        name = clean_text(name)
        if not name:
            return
        key = norm(team) + "|" + norm(name)
        p = players.setdefault(key, {"name": name, "team": team})
        if role:
            p.setdefault("roles", [])
            if role not in p["roles"]:
                p["roles"].append(role)
        if number is not None and "number" not in p:
            p["number"] = number
        if pid and "tffPersonId" not in p:
            p["tffPersonId"] = pid
    for side in ["home", "away"]:
        block = lineups.get(side, {}) or {}
        team = block.get("team", "")
        for role_name, key in [("starting11", "starting11"), ("substitute", "substitutes"), ("technical_staff", "technicalStaff")]:
            for pl in block.get(key, []) or []:
                add(pl.get("name"), team, role_name, pl.get("number"), pl.get("tffPersonId", ""))
    for ev in events:
        add(ev.get("player") or ev.get("scorer"), ev.get("team", ""), ev.get("type", "event"), pid=ev.get("tffPersonId", ""))
    return sorted(players.values(), key=lambda x: (norm(x.get("team", "")), norm(x.get("name", ""))))


def parse_structured_events(soup, home: str, away: str, txt: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    goals = parse_goals(soup, 1, home) + parse_goals(soup, 2, away)
    cards = parse_cards(soup, 1, home) + parse_cards(soup, 2, away)
    subs1, sub_events1 = parse_substitutions(soup, 1, home)
    subs2, sub_events2 = parse_substitutions(soup, 2, away)
    substitutions = subs1 + subs2
    events = goals + cards + sub_events1 + sub_events2
    if not events:
        events = parse_events_best_effort(txt, home, away)
    return events, goals, cards, substitutions


def parse_events_best_effort(txt: str, home: str, away: str) -> list[dict[str, Any]]:
    events = []
    current_team = ""
    for line in txt.splitlines():
        n = norm(line)
        if home and norm(home) in n:
            current_team = home
        elif away and norm(away) in n:
            current_team = away
        mm = re.search(r"\b(\d{1,3})\s*(?:\.?\s*dk|dakika|'|’)?\b", n)
        if not mm:
            continue
        typ = ""
        if "sari" in n and "kart" in n:
            typ = "yellow_card"
        elif "kirmizi" in n and "kart" in n:
            typ = "red_card"
        elif "oyundan cikan" in n or "cikti" in n:
            typ = "substitution_out"
        elif "oyuna giren" in n or "girdi" in n:
            typ = "substitution_in"
        elif "gol" in n:
            typ = "goal"
        if typ:
            events.append({"type": typ, "minute": int(mm.group(1)), "team": current_team, "raw": line})
    return events


def match_override_for(seed: dict[str, Any], season: str, mid: str) -> dict[str, Any]:
    """Return a narrowly scoped, source-reviewed correction for one match."""
    for item in seed.get("seasons", []) or []:
        if str(item.get("season") or "") != str(season):
            continue
        overrides = item.get("matchOverrides") or {}
        value = overrides.get(str(mid)) if isinstance(overrides, dict) else None
        return value if isinstance(value, dict) else {}
    return {}


def parse_detail(mid: str, raw: str, season: str, source_url: str, seed: dict[str, Any]) -> dict[str, Any]:
    soup = soup_from_html(raw)
    txt = text_from_html(raw)
    home, away = teams_from_soup(soup, txt)
    sh, sa, sdisp, played = score_from_soup(soup, txt)
    match_date, match_time = parse_date_time(soup, txt)
    competition = parse_competition(soup, txt)
    professional, professional_evidence = professional_competition_status(competition)
    match_type, match_label = classify_type(competition)
    correction = match_override_for(seed, season, str(mid))
    if correction.get("matchType"):
        match_type = str(correction["matchType"])
        match_label = str(correction.get("matchTypeLabel") or correction.get("label") or match_type)
    stage = str(correction.get("stage") or match_label)
    is_home = is_balkes(home)
    is_away = is_balkes(away)
    opponent = away if is_home else home if is_away else (away or home)
    gf = sh if is_home else sa if is_away else None
    ga = sa if is_home else sh if is_away else None
    result = ""
    if played and gf is not None and ga is not None:
        result = "W" if gf > ga else "D" if gf == ga else "L"

    officials = parse_officials(soup, txt)
    sections = parse_sections_raw(txt)
    lineups = parse_lineups_structured(soup, home, away, sections)
    events, goals, cards, substitutions = parse_structured_events(soup, home, away, txt)
    players = build_players_index_for_match(lineups, events)
    goal_scorers = [{"player": g.get("player") or g.get("scorer"), "team": g.get("team"), "minute": g.get("minute"), "goalType": g.get("goalType", "")} for g in goals]
    stadium = parse_stadium(soup)
    completeness = {
        "hasStadium": bool(stadium),
        "starting11Home": len(lineups.get("home", {}).get("starting11", [])),
        "starting11Away": len(lineups.get("away", {}).get("starting11", [])),
        "substitutesHome": len(lineups.get("home", {}).get("substitutes", [])),
        "substitutesAway": len(lineups.get("away", {}).get("substitutes", [])),
        "goals": len(goals),
        "cards": len(cards),
        "substitutions": len(substitutions),
        "players": len(players),
    }
    quality = "A" if home and away and played and match_date and (completeness["starting11Home"] or completeness["starting11Away"] or completeness["goals"] or completeness["cards"]) else "B" if home and away and match_date else "D"
    detail = {
        "id": str(mid),
        "matchCode": parse_match_code(soup, txt),
        "season": season,
        "competition": competition,
        "teamLevel": "professional" if professional else "non_professional",
        "teamLevelEvidence": professional_evidence,
        "competitionType": match_type,
        "competitionLabel": match_label,
        "stadium": stadium,
        "venue": stadium,
        "stage": stage,
        "stageLabel": stage,
        "date": match_date,
        "time": match_time,
        "dateDisplay": " - ".join(x for x in [match_date, match_time] if x),
        "homeTeam": home,
        "awayTeam": away,
        "matchType": match_type,
        "matchTypeLabel": match_label,
        "type": match_type,
        "typeLabel": match_label,
        "score": {"home": sh, "away": sa, "display": sdisp, "played": played},
        "balkes": {
            "isHome": bool(is_home),
            "isAway": bool(is_away),
            "opponent": opponent,
            "goalsFor": gf,
            "goalsAgainst": ga,
            "result": result,
        },
        "officials": officials,
        "referees": officials,
        "lineups": lineups,
        "players": players,
        "events": events,
        "goals": goals,
        "goalScorers": goal_scorers,
        "cards": cards,
        "substitutions": substitutions,
        "sections_raw": sections,
        "detailCompleteness": completeness,
        "quality": quality,
        "source": {"name": "TFF", "url": source_url, "retrievedAt": now(), "sourceType": "official_tff_match_detail"},
    }
    if correction:
        detail["dataCorrection"] = {
            "kind": "verified_match_classification",
            "reason": str(correction.get("reason") or "Registry override"),
            "sourceUrl": str(correction.get("sourceUrl") or source_url),
        }
    return detail


def detail_is_valid_for_season(detail: dict[str, Any], season: str, seed: dict[str, Any]) -> tuple[bool, str]:
    if not (is_balkes(detail.get("homeTeam")) or is_balkes(detail.get("awayTeam")) or is_balkes(json.dumps(detail.get("balkes", {}), ensure_ascii=False))):
        return False, "balkes_not_found"
    if not detail.get("date"):
        return False, "date_missing"
    if not date_in_season(detail["date"], season, seed):
        return False, f"date_out_of_season:{detail.get('date')}"
    if not detail.get("homeTeam") or not detail.get("awayTeam"):
        return False, "teams_missing"
    professional, evidence = professional_competition_status(detail.get("competition"))
    if not professional:
        return False, f"non_professional_team:{evidence}"
    # Skor yoksa da fikstür olarak kabul edelim; uygulama played=false gösterebilir.
    return True, "ok"


def fetch_detail_if_valid(mid: str, season: str, raw_root: Path, sleep_s: float, force: bool, seed: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    last_reason = "fetch_failed"
    # Modern TFF için pageID=29 asıl detay. İkinci URL bazı eski sayfalarda işe yarayabilir.
    for url in [tff_url(pageID=29, macId=mid), tff_url(macId=mid, pageID=528)]:
        ok, raw = fetch(url, raw_root / season / "matches" / f"{mid}.html", sleep_s, force)
        if not ok:
            continue
        detail = parse_detail(mid, raw, season, url, seed)
        valid, reason = detail_is_valid_for_season(detail, season, seed)
        if valid:
            return detail, "ok"
        last_reason = reason
    return None, last_reason


def parse_standings(raw: str) -> list[dict[str, Any]]:
    # Bu factory maç içindir. Puan tablosu Nix standings hattına bırakıldı.
    return []


def planned_urls_for_item(item: dict[str, Any]) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    plan = item.get("tffPlan") or {}
    page_id = str(item.get("targetPageID") or plan.get("pageID") or "").strip()
    group_id = str(item.get("targetGrupID") or plan.get("grupID") or "").strip()
    max_week = int(item.get("maxWeek") or plan.get("maxWeek") or 0)
    if not page_id:
        return urls
    base_params: dict[str, Any] = {"pageID": page_id}
    if group_id:
        base_params["grupID"] = group_id
    urls.append((f"target_pageID_{page_id}_group_{group_id or 'none'}", tff_url(**base_params)))
    for week in range(1, max_week + 1):
        params = dict(base_params)
        params["hafta"] = str(week)
        urls.append((f"target_pageID_{page_id}_group_{group_id or 'none'}_week_{week:02d}", tff_url(**params)))
    for u in item.get("targetUrls", []) or []:
        if isinstance(u, str) and u.strip():
            normalized = u.strip().replace("https://www.tff.org", "http://www.tff.org")
            normalized = normalized.replace("https://tff.org", "http://www.tff.org")
            urls.append(("target_extra_" + hashlib.sha1(normalized.encode()).hexdigest()[:8], normalized))
    return urls

def has_legacy_pageid_probe(item: dict[str, Any]) -> bool:
    probe = item.get("legacyPageIdProbe") or item.get("legacyPageIDProbe") or {}
    if not isinstance(probe, dict) or not probe.get("enabled", True):
        return False
    ranges = probe.get("pageIdRanges") or probe.get("pageIDRanges") or []
    if ranges:
        return True
    start = probe.get("start") or probe.get("pageIdStart") or probe.get("pageIDStart")
    end = probe.get("end") or probe.get("pageIdEnd") or probe.get("pageIDEnd")
    return start is not None and end is not None


def legacy_probe_ranges(item: dict[str, Any]) -> list[tuple[int, int]]:
    probe = item.get("legacyPageIdProbe") or item.get("legacyPageIDProbe") or {}
    out: list[tuple[int, int]] = []
    if not isinstance(probe, dict) or not probe.get("enabled", True):
        return out
    for r in probe.get("pageIdRanges") or probe.get("pageIDRanges") or []:
        if isinstance(r, dict):
            a = r.get("start") or r.get("from") or r.get("pageIdStart") or r.get("pageIDStart")
            b = r.get("end") or r.get("to") or r.get("pageIdEnd") or r.get("pageIDEnd")
        elif isinstance(r, (list, tuple)) and len(r) >= 2:
            a, b = r[0], r[1]
        else:
            continue
        try:
            ia, ib = int(a), int(b)
            out.append((min(ia, ib), max(ia, ib)))
        except Exception:
            continue
    if not out:
        try:
            a = int(probe.get("start") or probe.get("pageIdStart") or probe.get("pageIDStart"))
            b = int(probe.get("end") or probe.get("pageIdEnd") or probe.get("pageIDEnd"))
            out.append((min(a, b), max(a, b)))
        except Exception:
            pass
    return out


def legacy_probe_max_week(item: dict[str, Any]) -> int:
    probe = item.get("legacyPageIdProbe") or item.get("legacyPageIDProbe") or {}
    try:
        return int(probe.get("maxWeek") or item.get("maxWeek") or 40)
    except Exception:
        return 40


def legacy_probe_group_limit(item: dict[str, Any]) -> int:
    probe = item.get("legacyPageIdProbe") or item.get("legacyPageIDProbe") or {}
    try:
        return int(probe.get("groupLimit") or 40)
    except Exception:
        return 40


def legacy_probe_gateway_skip_after(item: dict[str, Any]) -> int:
    """Consecutive gateway/timeout errors before abandoning a dead branch.

    This is not a season duration/probe limit. It only prevents repeated 502/503/504
    requests on the same unreachable pageID/group branch. The season scan continues
    with the next pageID, so correctness is preserved without accepting guessed data.
    """
    probe = item.get("legacyPageIdProbe") or item.get("legacyPageIDProbe") or {}
    try:
        return max(1, int(probe.get("gatewaySkipAfter") or probe.get("httpErrorSkipAfter") or 3))
    except Exception:
        return 3


def is_gateway_fetch_error(err: str) -> bool:
    return str(err or "") in {"http_502", "http_503", "http_504", "timeout"}


def legacy_probe_should_expand_weeks(raw: str, selected_count_before: int, selected: set[str]) -> bool:
    # Haftalık sayfalara yalnızca sayfada Balkes ipucu varsa gir. Bu, modern ana sayfa
    # veya alakasız sezon sayfalarında binlerce gereksiz isteği engeller.
    if len(selected) > selected_count_before:
        return True
    return is_balkes(raw)


def discover_legacy_pageid_probe(item: dict[str, Any], raw_root: Path, sleep_s: float, force: bool = False) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Season-specific pageID window scanner for old professional seasons.

    v2.6 keeps the correctness model from v2.5 but adds a gateway guard:
    legacy TFF group branches that repeatedly return 502/503/504 or timeout are
    abandoned quickly, while the rest of the season pageID window continues.
    There is deliberately no per-season time cap; bad branches are skipped only
    after repeated unreachable responses and are recorded in diagnostics.
    """
    season = item["season"]
    selected: set[str] = set()
    all_ids: set[str] = set()
    diagnostics: list[dict[str, Any]] = []
    ranges = legacy_probe_ranges(item)
    max_week = legacy_probe_max_week(item)
    group_limit = legacy_probe_group_limit(item)
    gateway_skip_after = legacy_probe_gateway_skip_after(item)
    seen_urls: set[str] = set()

    def add_from_raw(label: str, raw: str) -> tuple[int, int]:
        before_sel = len(selected)
        before_all = len(all_ids)
        all_ids.update(extract_ids(raw))
        selected.update(extract_balkes_ids(raw))
        return len(selected) - before_sel, len(all_ids) - before_all

    def fetch_once(label: str, url: str) -> tuple[str, str]:
        if url in seen_urls:
            return "", "seen"
        seen_urls.add(url)
        path = raw_root / season / "legacy_pageid_probe" / f"{label}.html"
        ok, raw = fetch(url, path, sleep_s, force)
        err = FETCH_LAST_ERROR_BY_PATH.get(str(path), "")
        return (raw if ok else ""), err

    def diag_gateway(kind: str, page_id: int, err: str, **extra: Any) -> None:
        item_diag: dict[str, Any] = {"kind": kind, "pageID": page_id, "error": err}
        item_diag.update(extra)
        diagnostics.append(item_diag)

    for start, end in ranges:
        for page_id in range(start, end + 1):
            base_label = f"pageID_{page_id}"
            raw, err = fetch_once(base_label, tff_url(pageID=page_id))
            if not raw:
                if is_gateway_fetch_error(err):
                    diag_gateway("page_gateway_skip", page_id, err)
                continue
            sel_delta, all_delta = add_from_raw(base_label, raw)
            groups = extract_param(raw, "grupID")[:group_limit]
            page_hint = legacy_probe_should_expand_weeks(raw, len(selected) - sel_delta, selected)
            if sel_delta or page_hint:
                diagnostics.append({
                    "pageID": page_id,
                    "baseSelectedDelta": sel_delta,
                    "baseAllDelta": all_delta,
                    "groups": groups[:20],
                    "expandedWeeks": bool(max_week),
                })

            consecutive_group_gateway_errors = 0
            for gid in groups:
                if consecutive_group_gateway_errors >= gateway_skip_after:
                    diag_gateway(
                        "page_group_branch_abandoned",
                        page_id,
                        "consecutive_gateway_errors",
                        gatewayErrors=consecutive_group_gateway_errors,
                        remainingGroupsSkipped=True,
                    )
                    break

                group_label = f"pageID_{page_id}_group_{gid}"
                graw, gerr = fetch_once(group_label, tff_url(pageID=page_id, grupID=gid))
                if not graw:
                    if is_gateway_fetch_error(gerr):
                        consecutive_group_gateway_errors += 1
                        diag_gateway("group_gateway_skip", page_id, gerr, grupID=gid, consecutive=consecutive_group_gateway_errors)
                    continue

                consecutive_group_gateway_errors = 0
                g_sel_delta, g_all_delta = add_from_raw(group_label, graw)
                expand_weeks = legacy_probe_should_expand_weeks(graw, len(selected) - g_sel_delta, selected)
                if g_sel_delta or expand_weeks:
                    diagnostics.append({
                        "pageID": page_id,
                        "grupID": gid,
                        "groupSelectedDelta": g_sel_delta,
                        "groupAllDelta": g_all_delta,
                        "expandedWeeks": bool(max_week),
                    })
                if expand_weeks and max_week > 0:
                    consecutive_week_gateway_errors = 0
                    for week in range(1, max_week + 1):
                        if consecutive_week_gateway_errors >= gateway_skip_after:
                            diag_gateway(
                                "week_branch_abandoned",
                                page_id,
                                "consecutive_gateway_errors",
                                grupID=gid,
                                gatewayErrors=consecutive_week_gateway_errors,
                                remainingWeeksSkipped=True,
                            )
                            break
                        week_label = f"pageID_{page_id}_group_{gid}_week_{week:02d}"
                        wraw, werr = fetch_once(week_label, tff_url(pageID=page_id, grupID=gid, hafta=week))
                        if not wraw:
                            if is_gateway_fetch_error(werr):
                                consecutive_week_gateway_errors += 1
                                diag_gateway("week_gateway_skip", page_id, werr, grupID=gid, week=week, consecutive=consecutive_week_gateway_errors)
                            continue
                        consecutive_week_gateway_errors = 0
                        add_from_raw(week_label, wraw)
            if not groups and page_hint and max_week > 0:
                consecutive_week_gateway_errors = 0
                for week in range(1, max_week + 1):
                    if consecutive_week_gateway_errors >= gateway_skip_after:
                        diag_gateway(
                            "page_week_branch_abandoned",
                            page_id,
                            "consecutive_gateway_errors",
                            gatewayErrors=consecutive_week_gateway_errors,
                            remainingWeeksSkipped=True,
                        )
                        break
                    week_label = f"pageID_{page_id}_week_{week:02d}"
                    wraw, werr = fetch_once(week_label, tff_url(pageID=page_id, hafta=week))
                    if not wraw:
                        if is_gateway_fetch_error(werr):
                            consecutive_week_gateway_errors += 1
                            diag_gateway("page_week_gateway_skip", page_id, werr, week=week, consecutive=consecutive_week_gateway_errors)
                        continue
                    consecutive_week_gateway_errors = 0
                    add_from_raw(week_label, wraw)
    return sorted(selected, key=lambda x: int(x)), sorted(all_ids, key=lambda x: int(x)), diagnostics


def discover(item: dict[str, Any], raw_root: Path, sleep_s: float, force: bool = False) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    season = item["season"]
    selected, all_ids = set(), set()
    target_urls = planned_urls_for_item(item)
    if target_urls:
        log(f"{season}: hedef sezon planı kullanılıyor, urlSayısı={len(target_urls)}")
        for label, url in target_urls:
            ok, raw = fetch(url, raw_root / season / "planned" / f"{label}.html", sleep_s, force)
            if not ok:
                continue
            all_ids.update(extract_ids(raw))
            selected.update(extract_balkes_ids(raw))
        if selected:
            return sorted(selected, key=lambda x: int(x)), sorted(all_ids, key=lambda x: int(x)), []
        log(f"{season}: hedef planda Balkes selectedIds çıkmadı; all_ids={len(all_ids)}. Geniş fallback kapalı.")
        return [], sorted(all_ids, key=lambda x: int(x)), []

    if has_legacy_pageid_probe(item):
        ranges = legacy_probe_ranges(item)
        log(f"{season}: exact target yok; güvenli legacy pageID probe kullanılıyor, ranges={ranges}")
        return discover_legacy_pageid_probe(item, raw_root, sleep_s, force)

    for page_id in item.get("pageIds", []):
        url = tff_url(pageID=page_id)
        ok, raw = fetch(url, raw_root / season / "pages" / f"pageID_{page_id}.html", sleep_s, force)
        if not ok:
            continue
        all_ids.update(extract_ids(raw))
        selected.update(extract_balkes_ids(raw))
        for gid in extract_param(raw, "grupID")[:30]:
            gurl = tff_url(pageID=page_id, grupID=gid)
            ok2, graw = fetch(gurl, raw_root / season / "standings" / f"pageID_{page_id}_group_{gid}.html", sleep_s, force)
            if not ok2:
                continue
            all_ids.update(extract_ids(graw))
            selected.update(extract_balkes_ids(graw))
    return sorted(selected, key=lambda x: int(x)), sorted(all_ids, key=lambda x: int(x)), []


def match_signature(match: dict[str, Any]) -> str:
    b = match.get("balkes") or {}
    sc = match.get("score") or {}
    return "|".join([
        str(match.get("date") or ""),
        norm(b.get("opponent") or match.get("homeTeam") or match.get("awayTeam") or ""),
        "home" if b.get("isHome") else "away",
        str(sc.get("display") or "unplayed"),
    ])


def remove_superseded_unplayed(
    details: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Oynanan yeni tarih varken iptal/ertelenmiş eski lig kaydını çıkarır."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for detail in details:
        if detail.get("matchType") != "league":
            continue
        key = "|".join([
            norm(detail.get("competition")),
            norm(detail.get("homeTeam")),
            norm(detail.get("awayTeam")),
        ])
        groups.setdefault(key, []).append(detail)

    dropped_ids: set[str] = set()
    dropped: list[dict[str, Any]] = []
    for key, group in groups.items():
        played = [item for item in group if (item.get("score") or {}).get("played")]
        unplayed = [item for item in group if not (item.get("score") or {}).get("played")]
        if not played or not unplayed:
            continue
        kept = sorted(played, key=lambda item: (item.get("date") or "", str(item.get("id") or "")))[-1]
        for item in unplayed:
            match_id = str(item.get("id") or "")
            dropped_ids.add(match_id)
            dropped.append({
                "kept": str(kept.get("id") or ""),
                "dropped": match_id,
                "reason": "superseded_unplayed_league_fixture",
                "pair": key,
                "playedDate": kept.get("date"),
                "unplayedDate": item.get("date"),
            })
    return [item for item in details if str(item.get("id") or "") not in dropped_ids], dropped


def index_from_detail(d: dict[str, Any]) -> dict[str, Any]:
    keys = ["id", "matchCode", "season", "week", "standingsWeek", "competition", "competitionType", "competitionLabel", "teamLevel", "teamLevelEvidence", "stadium", "venue", "stage", "stageLabel", "date", "time", "dateDisplay", "homeTeam", "awayTeam", "matchType", "matchTypeLabel", "type", "typeLabel", "score", "balkes", "quality", "detailCompleteness"]
    out = {k: d.get(k) for k in keys if d.get(k) not in (None, "", {}, [])}
    out["detailUrl"] = f"seasons/{d['season']}/matches/{d['id']}.json"
    out["source"] = d["source"]
    return out



def season_year_start(season: str) -> int:
    try:
        return int(str(season)[:4])
    except Exception:
        return 9999


def has_known_match_ids(item: dict[str, Any]) -> bool:
    return bool(item.get("knownMatchIds"))


def has_planned_tff_target(item: dict[str, Any]) -> bool:
    """True only when the season has a season-specific TFF page/url target.

    This deliberately excludes knownMatchIds. A legacy season may have a few
    hand-verified match IDs without having a reliable season page. In that case
    we must fetch only those known IDs and must not run generic pageId discovery,
    because generic pages can expose modern-season macIds.
    """
    plan = item.get("tffPlan") or {}
    if str(item.get("targetPageID") or plan.get("pageID") or "").strip():
        return True
    if any(isinstance(u, str) and u.strip() for u in (item.get("targetUrls") or [])):
        return True
    return False


def has_exact_tff_target(item: dict[str, Any]) -> bool:
    """True when the season has an exact TFF page/url or explicit known match IDs."""
    return has_planned_tff_target(item) or has_known_match_ids(item) or has_legacy_pageid_probe(item)


def is_legacy_history_season(item: dict[str, Any], args: argparse.Namespace | None = None) -> bool:
    season = str(item.get("season") or "")
    cutoff = 2018
    if args is not None:
        cutoff = int(getattr(args, "legacy_target_cutoff_year", cutoff) or cutoff)
    return bool(item.get("legacySeason")) or season_year_start(season) <= cutoff


def season_skip_reason(item: dict[str, Any], args: argparse.Namespace | None = None) -> str:
    """Return a non-empty reason when this season should not hit TFF.

    Amateur-era seasons are intentionally skipped. Legacy professional seasons
    are also skipped when no exact season target/known macId exists, because the
    generic pageId fallback can surface modern-season macIds and waste hundreds
    of requests with 0 reliable hits.
    """
    for key in ["skipTff", "skipTffFetch", "noTffRecord", "amateurSeason"]:
        if bool(item.get(key)):
            return str(item.get("skipReason") or item.get("note") or key)
    status = norm(item.get("professionalStatus") or item.get("level") or "")
    if status == "amateur" or "amator" in status:
        return str(item.get("skipReason") or "amateur_season_no_tff_match_detail")
    strict = True if args is None else bool(getattr(args, "strict_legacy_targets", True))
    if strict and is_legacy_history_season(item, args) and not has_exact_tff_target(item):
        return str(item.get("skipReason") or "legacy_professional_missing_exact_tff_target_no_blind_scan")
    return ""


def process_season(item: dict[str, Any], args: argparse.Namespace, seed: dict[str, Any]) -> dict[str, Any]:
    season = item["season"]
    data_root = Path(args.data_root)
    raw_root = Path(args.raw_root)
    reports_root = Path(args.reports_root)
    log(f"=== {season} başladı ===")
    skip_reason = season_skip_reason(item, args)
    if skip_reason:
        log(f"{season}: TFF taraması atlandı -> {skip_reason}")
        quality = {
            "season": season,
            "skipped": True,
            "skipReason": skip_reason,
            "selectedIds": 0,
            "allDiscoveredIds": 0,
            "detailCandidates": 0,
            "candidateMode": "skip_no_tff_record",
            "matchesPublished": 0,
            "detailFiles": 0,
            "duplicatesDropped": 0,
            "rejectedReasons": {},
            "rejectedSamples": {},
            "standingsSkipped": True,
            "standingsSnapshots": 0,
            "balkesTableFound": False,
            "matchTypeCounts": {},
            "seasonGuard": {"start": season_bounds(season, seed)[0], "end": season_bounds(season, seed)[1]},
            "generatedAt": now(),
        }
        write_json(reports_root / "seasons" / f"{season}_quality.json", quality)
        return quality

    known = {str(x) for x in item.get("knownMatchIds", [])}
    legacy = is_legacy_history_season(item, args)
    planned_target = has_planned_tff_target(item)
    known_only = bool(item.get("knownOnly")) or (legacy and known and not planned_target and not has_legacy_pageid_probe(item))

    discovery_diagnostics: list[dict[str, Any]] = []
    if known_only:
        selected, all_ids = [], []
        candidates = sorted(known, key=lambda x: int(x))
        mode = "known_match_ids_only"
        log(f"{season}: known-only güvenli mod; generic pageId discovery kapalı, knownIds={len(candidates)}")
    else:
        selected, all_ids, discovery_diagnostics = discover(item, raw_root, args.sleep, args.force)
        if selected or known:
            candidates = sorted(set(selected) | known, key=lambda x: int(x))
            mode = "selected_or_known" if not has_legacy_pageid_probe(item) else "legacy_pageid_probe_selected_or_known"
        elif has_legacy_pageid_probe(item):
            # PageID probe sırasında sayfada macId olabilir ama Balıkesirspor satırı bulunmadıysa
            # all_ids fallback yapılmaz. Aksi halde yine alakasız sezon/lig havuzunu detay detay tararız.
            candidates = []
            mode = "legacy_pageid_probe_no_selected_ids"
        else:
            candidates = list(all_ids)
            mode = "all_discovered_fallback"
        if args.max_discovery_probe > 0:
            candidates = candidates[:args.max_discovery_probe]
    log(f"{season}: selectedIds={len(selected)}, allDiscoveredIds={len(all_ids)}, detailCandidates={len(candidates)}, candidateMode={mode}")

    season_dir = data_root / "seasons" / season
    matches_dir = season_dir / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)

    by_id: dict[str, dict[str, Any]] = {}
    fixture_by_id = {
        str(fixture.get("id")): fixture
        for fixture in item.get("knownFixtures", [])
        if isinstance(fixture, dict) and fixture.get("id")
    }
    rejected: dict[str, int] = {}
    rejected_samples: dict[str, list[str]] = {}

    def fetch_candidates(candidate_ids: list[str], phase: str) -> None:
        if not candidate_ids:
            return
        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
            futures = {
                executor.submit(
                    fetch_detail_if_valid, mid, season, raw_root,
                    args.sleep, args.force, seed,
                ): str(mid)
                for mid in candidate_ids
            }
            for i, future in enumerate(as_completed(futures), start=1):
                mid = futures[future]
                try:
                    detail, reason = future.result()
                except Exception as exc:
                    detail, reason = None, f"worker_error:{type(exc).__name__}"
                if detail:
                    fixture = fixture_by_id.get(str(mid)) or {}
                    week = int(fixture.get("week") or 0)
                    if week > 0:
                        detail["week"] = week
                        if detail.get("matchType") == "league":
                            detail["standingsWeek"] = week
                    if fixture.get("rowText") or fixture.get("sourceUrl"):
                        detail["clubFixture"] = {
                            "week": week,
                            "rowText": str(fixture.get("rowText") or ""),
                            "sourceUrl": str(fixture.get("sourceUrl") or ""),
                        }
                    by_id[mid] = detail
                else:
                    rejected[reason] = rejected.get(reason, 0) + 1
                    rejected_samples.setdefault(reason, [])
                    if len(rejected_samples[reason]) < 20:
                        rejected_samples[reason].append(mid)
                if i % 25 == 0 or i == len(candidate_ids):
                    log(f"{season}: {phase} {i}/{len(candidate_ids)}, hits={len(by_id)}")

    fetch_candidates([str(mid) for mid in candidates], "paralel detay")

    if (not by_id and selected and all_ids and bool(item.get("allowLegacyBroadFallback"))
            and not bool(item.get("knownOnly")) and has_planned_tff_target(item)):
        already = set(str(x) for x in candidates)
        extra = [str(x) for x in all_ids if str(x) not in already]
        limit = int(item.get("legacyBroadProbeLimit") or getattr(args, "legacy_broad_probe_limit", 350) or 0)
        if limit > 0:
            extra = extra[:limit]
        log(f"{season}: selectedIds 0 hit verdi; legacy geniş fallback başlıyor, extraCandidates={len(extra)}")
        candidates.extend(extra)
        fetch_candidates([str(mid) for mid in extra], "paralel legacy fallback")
        if extra:
            mode = mode + "+legacy_broad_after_zero_hits"

    by_sig: dict[str, dict[str, Any]] = {}
    duplicates = []
    for mid, d in by_id.items():
        sig = match_signature(d)
        if sig in by_sig:
            old = by_sig[sig]
            duplicates.append({"kept": old["id"], "dropped": mid, "signature": sig})
            if len(json.dumps(d, ensure_ascii=False)) > len(json.dumps(old, ensure_ascii=False)):
                by_sig[sig] = d
        else:
            by_sig[sig] = d

    details = sorted(by_sig.values(), key=lambda m: (m.get("date") or "", int(str(m.get("id") or 0))))
    details, superseded = remove_superseded_unplayed(details)
    duplicates.extend(superseded)

    if not details:
        existing_index = read_json(season_dir / "matches_index.json", [])
        existing_count = len(existing_index) if isinstance(existing_index, list) else 0
        quality = {
            "season": season,
            "selectedIds": len(selected),
            "allDiscoveredIds": len(all_ids),
            "detailCandidates": len(candidates),
            "candidateMode": mode,
            "knownOnly": bool(known_only),
            "plannedTarget": bool(planned_target),
            "legacyPageIdProbe": bool(has_legacy_pageid_probe(item)),
            "legacyProbeDiagnostics": discovery_diagnostics,
            "matchesPublished": existing_count,
            "newMatchesPublished": 0,
            "preservedExisting": existing_count > 0,
            "detailFiles": len(list(matches_dir.glob("*.json"))),
            "duplicatesDropped": len(duplicates),
            "rejectedReasons": rejected,
            "rejectedSamples": rejected_samples,
            "standingsSkipped": True,
            "standingsSnapshots": 0,
            "balkesTableFound": False,
            "matchTypeCounts": {},
            "seasonGuard": {"start": season_bounds(season, seed)[0], "end": season_bounds(season, seed)[1]},
            "generatedAt": now(),
        }
        write_json(reports_root / "seasons" / f"{season}_quality.json", quality)
        log(
            f"{season}: doğrulanmış yeni maç yok; "
            f"mevcut={existing_count} {'korundu' if existing_count else 'yok'}"
        )
        return quality

    for d in details:
        write_json(matches_dir / f"{d['id']}.json", d)
    published_ids = {str(detail["id"]) for detail in details}
    stale_files = [path for path in matches_dir.glob("*.json") if path.stem not in published_ids]
    for path in stale_files:
        path.unlink()
    index = [index_from_detail(d) for d in details]
    write_json(season_dir / "matches_index.json", index)
    write_json(season_dir / "standings_by_week.json", [])

    type_counts: dict[str, int] = {}
    wins = draws = losses = gf = ga = 0
    for m in index:
        mt = m.get("matchType") or "league"
        type_counts[mt] = type_counts.get(mt, 0) + 1
        b = m.get("balkes") or {}
        if b.get("result") == "W": wins += 1
        elif b.get("result") == "D": draws += 1
        elif b.get("result") == "L": losses += 1
        if b.get("goalsFor") is not None:
            gf += int(b.get("goalsFor") or 0)
        if b.get("goalsAgainst") is not None:
            ga += int(b.get("goalsAgainst") or 0)

    season_competition = details[0].get("competition", "") if details else ""
    write_json(season_dir / "season.json", {
        "id": season,
        "name": season,
        "competition": season_competition,
        "sourcePolicy": "TFF-only",
        "factoryVersion": FACTORY_VERSION,
        "updatedAt": now(),
        "summary": {"matches": len(index), "wins": wins, "draws": draws, "losses": losses, "goalsFor": gf, "goalsAgainst": ga, "goalDifference": gf - ga, "matchTypes": type_counts},
        "files": {"matchesIndex": f"seasons/{season}/matches_index.json", "standingsByWeek": f"seasons/{season}/standings_by_week.json"},
    })

    quality = {
        "season": season,
        "selectedIds": len(selected),
        "allDiscoveredIds": len(all_ids),
        "detailCandidates": len(candidates),
        "candidateMode": mode,
        "knownOnly": bool(known_only),
        "plannedTarget": bool(planned_target),
        "legacyPageIdProbe": bool(has_legacy_pageid_probe(item)),
        "legacyProbeDiagnostics": discovery_diagnostics,
        "matchesPublished": len(index),
        "newMatchesPublished": len(index),
        "preservedExisting": False,
        "detailFiles": len(list(matches_dir.glob("*.json"))),
        "staleDetailFilesPruned": len(stale_files),
        "duplicatesDropped": len(duplicates),
        "rejectedReasons": rejected,
        "rejectedSamples": rejected_samples,
        "standingsSkipped": True,
        "standingsSnapshots": 0,
        "balkesTableFound": False,
        "matchTypeCounts": type_counts,
        "seasonGuard": {"start": season_bounds(season, seed)[0], "end": season_bounds(season, seed)[1]},
        "generatedAt": now(),
    }
    write_json(reports_root / "seasons" / f"{season}_quality.json", quality)
    if duplicates:
        write_json(reports_root / "seasons" / f"{season}_duplicate_candidates.json", duplicates)
    return quality


def build_manifest(data_root: Path, processed: list[str]) -> None:
    seasons = []
    for p in sorted((data_root / "seasons").glob("*/matches_index.json"), reverse=True):
        arr = read_json(p, [])
        season_json = read_json(p.parent / "season.json", {})
        if isinstance(arr, list) and arr:
            item = {"id": p.parent.name, "name": p.parent.name, "matchCount": len(arr)}
            if isinstance(season_json, dict):
                if season_json.get("competition"):
                    item["competition"] = season_json.get("competition")
                if season_json.get("summary"):
                    item["summary"] = season_json.get("summary")
                if season_json.get("leagueSummary"):
                    item["leagueSummary"] = season_json.get("leagueSummary")
                if season_json.get("leagueStages"):
                    item["leagueStages"] = season_json.get("leagueStages")
            seasons.append(item)
    write_json(data_root / "manifest.json", {
        "app": "Balkes Hakkında",
        "schemaVersion": 3,
        "dataVersion": 1,
        "appVersion": "1.5.0-alpha02",
        "generatedAt": now(),
        "team": "Balıkesirspor",
        "availableSeasons": seasons,
        "global": {"playersIndexUrl": "players_index.json", "opponentsIndexUrl": "opponents_index.json", "searchIndexUrl": "search_index.json", "dataReportUrl": "data_report.json"},
        "appDataVersion": int(datetime.now().timestamp()),
        "appMinVersion": "1.5.0-alpha02",
        "lastUpdated": now(),
        "dataBaseUrl": DATA_BASE_URL,
        "factoryVersion": FACTORY_VERSION,
        "processedSeasonsInLastRun": processed,
    })


def rebuild_global_indexes(data_root: Path) -> None:
    opponents = {}
    players: dict[str, dict[str, Any]] = {}
    search = []
    for p in sorted((data_root / "seasons").glob("*/matches_index.json")):
        arr = read_json(p, [])
        for m in arr if isinstance(arr, list) else []:
            b = m.get("balkes") or {}
            opp = b.get("opponent")
            if opp:
                item = opponents.setdefault(norm(opp), {"name": opp, "matches": 0})
                item["matches"] += 1
            search.append({"type": "match", "season": m.get("season"), "id": m.get("id"), "title": f"{m.get('homeTeam','')} {m.get('score',{}).get('display','')} {m.get('awayTeam','')}", "date": m.get("date"), "url": m.get("detailUrl")})
            detail_url = str(m.get("detailUrl") or "")
            detail = read_json(data_root / detail_url, {}) if detail_url else {}
            for player in detail.get("players", []) if isinstance(detail, dict) else []:
                if not isinstance(player, dict) or not player.get("name"):
                    continue
                person_id = str(player.get("tffPersonId") or "")
                key = "id:" + person_id if person_id else "name:" + norm(player.get("name"))
                value = players.setdefault(key, {
                    "id": person_id or key,
                    "name": player.get("name"),
                    "tffPersonId": person_id,
                    "teams": set(),
                    "roles": set(),
                    "seasons": set(),
                    "matches": set(),
                })
                if player.get("team"):
                    value["teams"].add(player["team"])
                value["roles"].update(str(role) for role in player.get("roles", []) if role)
                if m.get("season"):
                    value["seasons"].add(str(m["season"]))
                if m.get("id"):
                    value["matches"].add(str(m["id"]))
    players_index = []
    for value in players.values():
        players_index.append({
            "id": value["id"],
            "name": value["name"],
            "tffPersonId": value["tffPersonId"],
            "teams": sorted(value["teams"], key=norm),
            "roles": sorted(value["roles"]),
            "seasons": sorted(value["seasons"], reverse=True),
            "matchCount": len(value["matches"]),
        })
    players_index.sort(key=lambda value: norm(value["name"]))
    write_json(data_root / "players_index.json", players_index)
    write_json(data_root / "opponents_index.json", sorted(opponents.values(), key=lambda x: norm(x["name"])))
    write_json(data_root / "search_index.json", search)


def build_data_report(data_root: Path, reports_root: Path, processed: list[dict[str, Any]]) -> None:
    manifest = read_json(data_root / "manifest.json", {})
    seasons = manifest.get("availableSeasons", []) if isinstance(manifest, dict) else []
    total = sum(int(s.get("matchCount") or 0) for s in seasons)
    write_json(data_root / "data_report.json", {
        "generatedAt": now(),
        "sourcePolicy": "TFF-only",
        "factoryVersion": FACTORY_VERSION,
        "totalAppMatches": total,
        "seasons": seasons,
        "playersIndexed": len(read_json(data_root / "players_index.json", [])),
        "opponentsIndexed": len(read_json(data_root / "opponents_index.json", [])),
        "notes": ["Puan tablosu bu factory içinde çekilmez; Nix standings hattı kullanılacak.", "Raw HTML repo'ya commitlenmez; artifact olarak saklanır."],
    })
    write_json(reports_root / "tff_factory_summary.json", {
        "generatedAt": now(),
        "status": "ok",
        "sourcePolicy": "TFF-only",
        "factoryVersion": FACTORY_VERSION,
        "processed": processed,
        "after": {"seasons": len(seasons), "matches": total},
        "safeToPush": total > 0,
    })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="sources/tff/registry/balkes_tff_seed_registry.json")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--raw-root", default="sources/tff/raw")
    ap.add_argument("--reports-root", default="reports/tff_factory")
    ap.add_argument("--start-season", default="2025-2026")
    ap.add_argument("--max-seasons", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--season-workers", type=int, default=2)
    ap.add_argument("--max-discovery-probe", type=int, default=1500)
    ap.add_argument("--legacy-broad-probe-limit", type=int, default=350)
    ap.add_argument("--strict-legacy-targets", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--legacy-target-cutoff-year", type=int, default=2018)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-standings", action="store_true", default=True)
    args = ap.parse_args()

    seed = read_json(args.seed, {})
    by = {s["season"]: s for s in seed.get("seasons", []) if isinstance(s, dict) and s.get("season")}
    queue = []
    seen = False
    for sid in seed.get("runOrder", []):
        if sid == args.start_season:
            seen = True
        if seen and sid in by:
            queue.append(by[sid])
    queue = queue[:max(1, args.max_seasons)]
    if not queue:
        raise SystemExit(f"start-season bulunamadı: {args.start_season}")

    log("queue=" + ", ".join(x["season"] for x in queue))
    processed_by_season: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, int(args.season_workers))) as executor:
        futures = {executor.submit(process_season, item, args, seed): item["season"] for item in queue}
        for future in as_completed(futures):
            season = futures[future]
            processed_by_season[season] = future.result()
    processed = [processed_by_season[item["season"]] for item in queue]

    processed_seasons = [x["season"] for x in processed]
    build_manifest(Path(args.data_root), processed_seasons)
    rebuild_global_indexes(Path(args.data_root))
    build_data_report(Path(args.data_root), Path(args.reports_root), processed)
    run_matches = sum(int(x.get("matchesPublished") or 0) for x in processed)
    if run_matches <= 0:
        raise SystemExit("HATA: Bu run hiç maç üretmedi; main'e basılmamalı.")
    log(f"DONE {FACTORY_VERSION}: processed={processed_seasons}, run_matches={run_matches}")


if __name__ == "__main__":
    main()
