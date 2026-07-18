import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from package_release import ReleaseError, package_release  # noqa: E402


class PackageReleaseTest(unittest.TestCase):
    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def clean_tree(self, root: Path) -> None:
        self.write_json(root / "manifest.json", {
            "appDataVersion": 1770000000,
            "dataVersion": 1,
            "dataBaseUrl": "https://raw.githubusercontent.com/Sinanjam/Balkes-Hakkinda/main/data/",
            "availableSeasons": [{"id": "2025-2026", "matchCount": 1}],
        })
        self.write_json(root / "reports" / "completion.json", {
            "status": "clean_with_source_limits",
            "readyToPublish": True,
            "summary": {"seasons": 1, "matches": 1},
            "errors": [],
            "warnings": ["kaynak kısıtı"],
        })
        self.write_json(root / "seasons" / "2025-2026" / "matches_index.json", [{"id": "1"}])
        (root / "reports" / "validation.json.before-standings-repair").write_text(
            "geçici", encoding="utf-8"
        )

    def test_creates_verified_deterministic_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            data = base / "generated" / "tff-data"
            output = base / "releases"
            self.clean_tree(data)

            first = package_release(data, output)
            second = package_release(data, output)
            archive = Path(first["paths"]["archive"])

            self.assertEqual(first["archive"]["sha256"], second["archive"]["sha256"])
            self.assertTrue(Path(first["paths"]["checksum"]).is_file())
            self.assertTrue(Path(first["paths"]["metadata"]).is_file())
            with zipfile.ZipFile(archive) as zipped:
                self.assertIn("data/manifest.json", zipped.namelist())
                self.assertIn("data/reports/completion.json", zipped.namelist())
                self.assertFalse(any("before-standings-repair" in name for name in zipped.namelist()))
                self.assertIsNone(zipped.testzip())

    def test_rejects_incomplete_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            data = base / "data"
            self.clean_tree(data)
            self.write_json(data / "reports" / "completion.json", {
                "status": "error",
                "readyToPublish": False,
                "errors": ["eksik"],
            })
            with self.assertRaises(ReleaseError):
                package_release(data, base / "releases")


if __name__ == "__main__":
    unittest.main()
