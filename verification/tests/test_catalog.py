import json
import tempfile
import unittest
from pathlib import Path

from ara_verify.catalog import ManifestError, _read_make_variable, load_catalog


class MakeVariableTests(unittest.TestCase):
    def test_continuation_without_space(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Makefrag"
            path.write_text("tests = vadd \\\n  vsub\\\n  vmul\n", encoding="utf-8")
            self.assertEqual(_read_make_variable(path, "tests"), ["vadd", "vsub", "vmul"])

    def test_missing_variable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Makefrag"
            path.write_text("other = value\n", encoding="utf-8")
            with self.assertRaises(ManifestError):
                _read_make_variable(path, "tests")


class CatalogTests(unittest.TestCase):
    def _repo(self, root: Path) -> Path:
        (root / "apps/foo").mkdir(parents=True)
        (root / "apps/foo/main.c").write_text("int main(void) {}\n", encoding="utf-8")
        makefrag = root / "apps/riscv-tests/isa/rv64uv/Makefrag"
        makefrag.parent.mkdir(parents=True)
        makefrag.write_text("rv64uv_sc_tests = vadd \\\n vsub\n", encoding="utf-8")
        for test in ("vadd", "vsub"):
            (makefrag.parent / f"{test}.c").write_text(
                "int main(void) { return 0; }\n", encoding="utf-8"
            )
        return root

    def test_discovery_and_suite_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory))
            manifest = root / "suites.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "defaults": {"timeout_s": 10},
                "catalogs": {
                    "apps": {"kind": "app", "root": "apps"},
                    "rvv": {
                        "kind": "rvv",
                        "makefrag": "apps/riscv-tests/isa/rv64uv/Makefrag",
                        "variable": "rv64uv_sc_tests"
                    }
                },
                "suites": {
                    "smoke": {"tests": ["app:foo", "rvv:vadd"]},
                    "all": {"include": ["app:*", "rvv:*"]}
                }
            }), encoding="utf-8")
            catalog = load_catalog(root, manifest)
            self.assertEqual([test.name for test in catalog.resolve_suite("smoke")], ["app:foo", "rvv:vadd"])
            self.assertEqual(len(catalog.resolve_suite("all")), 3)
            self.assertEqual([test.name for test in catalog.select(["rvv:v*"])], ["rvv:vadd", "rvv:vsub"])

    def test_rejects_rvv_entry_without_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory))
            (root / "apps/riscv-tests/isa/rv64uv/vsub.c").unlink()
            manifest = root / "suites.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "defaults": {"timeout_s": 10},
                "catalogs": {
                    "rvv": {
                        "kind": "rvv",
                        "makefrag": "apps/riscv-tests/isa/rv64uv/Makefrag",
                        "variable": "rv64uv_sc_tests"
                    }
                },
                "suites": {"all": {"include": ["rvv:*"]}}
            }), encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "RVV test vsub.*source is missing"):
                load_catalog(root, manifest)
