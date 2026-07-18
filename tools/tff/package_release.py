#!/usr/bin/env python3
"""Kalite kapısı geçmiş TFF verisini tekrarlanabilir bir yerel sürüme paketler."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class ReleaseError(RuntimeError):
    """Veri seti güvenle paketlenemediğinde kullanılır."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReleaseError(f"JSON okunamadı: {path}") from error
    if not isinstance(value, dict):
        raise ReleaseError(f"JSON nesnesi bekleniyordu: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_release_id(value: object, manifest_sha: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-.")
    return candidate or manifest_sha[:12]


def is_transient(path: Path) -> bool:
    name = path.name
    return (
        name.startswith(".")
        or name.endswith(".tmp")
        or name.endswith(".part")
        or name.endswith(".before-standings-repair")
    )


def release_files(data_root: Path) -> list[Path]:
    files = [
        path for path in data_root.rglob("*")
        if path.is_file() and not any(is_transient(part) for part in path.relative_to(data_root).parents)
        and not is_transient(path)
    ]
    return sorted(files, key=lambda path: path.relative_to(data_root).as_posix())


def write_deterministic_zip(data_root: Path, destination: Path, files: Iterable[Path]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            strict_timestamps=True,
        ) as archive:
            for source in files:
                relative = source.relative_to(data_root).as_posix()
                info = zipfile.ZipInfo(f"data/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                with source.open("rb") as input_file, archive.open(info, "w") as output_file:
                    for block in iter(lambda: input_file.read(1024 * 1024), b""):
                        output_file.write(block)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_archive(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if "data/manifest.json" not in names:
                raise ReleaseError("ZIP içinde data/manifest.json bulunamadı.")
            damaged = archive.testzip()
            if damaged:
                raise ReleaseError(f"ZIP CRC doğrulaması başarısız: {damaged}")
    except (OSError, zipfile.BadZipFile) as error:
        raise ReleaseError("ZIP doğrulanamadı.") from error


def package_release(data_root: Path, output_dir: Path) -> dict[str, Any]:
    data_root = data_root.resolve()
    output_dir = output_dir.resolve()
    if not data_root.is_dir():
        raise ReleaseError(f"Veri klasörü bulunamadı: {data_root}")
    if output_dir == data_root or data_root in output_dir.parents:
        raise ReleaseError("Paket klasörü veri klasörünün içinde olamaz.")

    manifest_path = data_root / "manifest.json"
    completion_path = data_root / "reports" / "completion.json"
    manifest = read_json(manifest_path)
    completion = read_json(completion_path)
    errors = completion.get("errors")
    if completion.get("readyToPublish") is not True or (isinstance(errors, list) and errors):
        raise ReleaseError("Kalite kapısı geçilmedi; readyToPublish=true ve errors=[] gerekli.")

    seasons = manifest.get("availableSeasons")
    if not isinstance(seasons, list) or not seasons:
        raise ReleaseError("Manifestte yayımlanabilir sezon bulunamadı.")

    files = release_files(data_root)
    if manifest_path not in files or completion_path not in files:
        raise ReleaseError("Manifest veya tamamlanma raporu paket listesine girmedi.")

    manifest_sha = sha256_file(manifest_path)
    release_id = safe_release_id(manifest.get("appDataVersion"), manifest_sha)
    archive_name = f"tff-data-v{release_id}.zip"
    archive_path = output_dir / archive_name
    write_deterministic_zip(data_root, archive_path, files)
    verify_archive(archive_path)

    archive_sha = sha256_file(archive_path)
    uncompressed_bytes = sum(path.stat().st_size for path in files)
    metadata = {
        "schemaVersion": 1,
        "releaseId": release_id,
        "createdAt": utc_now(),
        "dataVersion": manifest.get("dataVersion"),
        "appDataVersion": manifest.get("appDataVersion"),
        "dataBaseUrl": manifest.get("dataBaseUrl"),
        "archive": {
            "file": archive_name,
            "root": "data/",
            "sha256": archive_sha,
            "bytes": archive_path.stat().st_size,
            "uncompressedBytes": uncompressed_bytes,
            "fileCount": len(files),
        },
        "manifest": {
            "file": "data/manifest.json",
            "sha256": manifest_sha,
            "seasonCount": len(seasons),
        },
        "quality": {
            "status": completion.get("status"),
            "readyToPublish": True,
            "summary": completion.get("summary", {}),
            "warnings": completion.get("warnings", []),
        },
    }

    checksum_path = output_dir / f"{archive_name}.sha256"
    metadata_path = output_dir / f"tff-data-v{release_id}.release.json"
    atomic_text(checksum_path, f"{archive_sha}  {archive_name}\n")
    atomic_text(
        metadata_path,
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    metadata["paths"] = {
        "archive": str(archive_path),
        "checksum": str(checksum_path),
        "metadata": str(metadata_path),
    }
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Doğrulanmış TFF veri sürümü paketleyici")
    parser.add_argument("--data-root", default="generated/tff-data")
    parser.add_argument("--output-dir", default="local-releases/tff-data")
    args = parser.parse_args()
    try:
        result = package_release(Path(args.data_root), Path(args.output_dir))
    except ReleaseError as error:
        print(f"Paketleme durduruldu: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
