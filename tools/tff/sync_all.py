#!/usr/bin/env python3
"""Balıkesirspor TFF arşivini tek komutla üretir."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent


def log(message: str) -> None:
    print(f"\n[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def run(command: list[str], env: dict[str, str]) -> None:
    log("Çalışıyor: " + " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def selected_runtime_registry(path: Path, seasons: list[str]) -> None:
    if not seasons:
        return
    registry = read_json(path, {}) or {}
    known = {item.get("season") for item in registry.get("seasons", [])}
    missing = [season for season in seasons if season not in known]
    if missing:
        raise SystemExit("Registry'de bulunmayan sezon: " + ", ".join(missing))
    registry["runOrder"] = seasons
    write_json(path, registry)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="TFF arşivinden tüm Balıkesirspor maçlarını ve haftalık puan tablolarını üretir"
    )
    parser.add_argument("--output", default="generated/tff-data")
    parser.add_argument("--cache", default=".cache/tff")
    parser.add_argument("--workers", type=int, default=min(12, max(6, (os.cpu_count() or 4))))
    parser.add_argument("--season-workers", type=int, default=2)
    parser.add_argument("--season", action="append", help="Yalnızca bu sezon; birden çok kez verilebilir")
    parser.add_argument("--delay", type=float, default=0.06)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--force", action="store_true", help="HTML önbelleğini yok sayıp yeniden indir")
    parser.add_argument("--standings-mode", choices=["auto", "official-only", "computed-only"], default="auto")
    parser.add_argument("--no-standings", action="store_true")
    args = parser.parse_args()

    output = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    cache = (ROOT / args.cache).resolve() if not Path(args.cache).is_absolute() else Path(args.cache)
    registry = cache / "runtime_registry.json"
    report_root = output / "reports"
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("TFF_BASE_URL", "http://www.tff.org/Default.aspx")
    env.setdefault("TFF_FETCH_TIMEOUT", str(args.timeout))
    detail_workers = max(1, args.workers // max(1, args.season_workers))

    discovery = [
        sys.executable, str(TOOLS / "discover_club_fixtures.py"),
        "--registry", str(TOOLS / "balkes_tff_seed_registry.json"),
        "--output", str(registry),
        "--report", str(report_root / "club_fixture_discovery.json"),
        "--cache-dir", str(cache / "club_fixtures"),
        "--raw-dir", str(cache / "raw"),
        "--target-cache-dir", str(cache / "standings_targets"),
        "--workers", str(min(6, args.workers)),
        "--timeout", str(args.timeout),
        "--delay", str(args.delay),
        "--allow-empty",
    ]
    for season in args.season or []:
        discovery.extend(["--season", season])
    if args.force:
        discovery.append("--force")
    run(discovery, env)
    selected_runtime_registry(registry, args.season or [])

    runtime = read_json(registry, {}) or {}
    queue = [str(value) for value in runtime.get("runOrder", [])]
    if not queue:
        raise SystemExit("Çalıştırılacak sezon bulunamadı.")
    start_season = queue[0]
    max_seasons = len(queue)

    factory = [
        sys.executable, str(TOOLS / "tff_factory.py"),
        "--seed", str(registry),
        "--data-root", str(output),
        "--raw-root", str(cache / "raw"),
        "--reports-root", str(report_root / "factory"),
        "--start-season", start_season,
        "--max-seasons", str(max_seasons),
        "--workers", str(detail_workers),
        "--season-workers", str(max(1, args.season_workers)),
        "--sleep", str(args.delay),
        "--max-discovery-probe", "2500",
        "--legacy-broad-probe-limit", "0",
        "--strict-legacy-targets",
        "--skip-standings",
    ]
    if args.force:
        factory.append("--force")
    run(factory, env)

    # Önceki yarım koşudan kalan altyapı/PAF ve artık JSON dosyalarını da
    # temizle; böylece yalnız bu turda işlenen sezonlara güvenmeyiz.
    run([
        sys.executable, str(TOOLS / "sanitize_export.py"),
        "--data-root", str(output),
        "--report", str(report_root / "sanitization.json"),
    ], env)

    if not args.no_standings:
        standings = [
            sys.executable, str(TOOLS / "tff_standings_builder.py"),
            "--seed", str(registry),
            "--data-root", str(output),
            "--raw-root", str(cache / "standings"),
            "--reports-root", str(report_root / "standings"),
            "--penalties", str(TOOLS / "standings_penalties.json"),
            "--start-season", start_season,
            "--max-seasons", str(max_seasons),
            "--mode", args.standings_mode,
            "--probe-limit", "5000",
            "--workers", str(detail_workers),
            "--week-workers", str(max(2, min(6, detail_workers))),
            "--season-workers", str(max(1, args.season_workers)),
            "--detail-fetch-mode", "missing",
            "--week-param-mode", "smart",
            "--sleep", str(args.delay),
        ]
        for season in args.season or []:
            standings.extend(["--season", season])
        if args.force:
            standings.append("--force")
        run(standings, env)

    validation = [
        sys.executable, str(TOOLS / "validate_export.py"),
        "--data-root", str(output),
        "--report", str(report_root / "validation.json"),
        "--registry", str(registry),
        "--discovery-report", str(report_root / "club_fixture_discovery.json"),
    ]
    run(validation, env)
    log(f"TAMAMLANDI: {output}")
    log(f"Uygulama verisi: {output / 'manifest.json'}")
    log(f"Kalite raporu: {report_root / 'validation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
