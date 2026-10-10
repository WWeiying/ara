import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reconcile_fulltrace import reconcile, resolve_source_paths


class ReconcileFullTraceTests(unittest.TestCase):
    def prepare(self, root: Path) -> tuple[Path, Path]:
        plan = root / "plan.json"
        plan.write_text(json.dumps({
            "status": "FAIL",
            "simv_sha256": "simv-hash",
            "cases": [
                {"name": "q3_K", "mode": "rvv", "status": "FAIL",
                 "elf_sha256": "elf-hash"},
                {"name": "q3_K", "mode": "qbs", "status": "PASS",
                 "elf_sha256": "other-hash"},
            ],
            "output_manifest": {
                "schema_version": 1,
                "qbs_pairs": [{"format": "q3_K", "rvv_run": "old-rvv",
                               "qbs_run": "old-qbs"}],
                "akv_pair": {},
            },
        }))
        run = root / "override"
        run.mkdir()
        (run / "uvm_result.json").write_text(json.dumps({
            "status": "PASS", "elf_sha256": "elf-hash",
            "simv_sha256": "simv-hash",
        }))
        return plan, run

    def test_requires_override_for_every_failed_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, _ = self.prepare(root)
            with self.assertRaisesRegex(ValueError, "no verified override"):
                reconcile(plan, {}, root / "out")

    def test_rejects_different_simulator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, run = self.prepare(root)
            result = json.loads((run / "uvm_result.json").read_text())
            result["simv_sha256"] = "different"
            (run / "uvm_result.json").write_text(json.dumps(result))
            with patch("reconcile_fulltrace.check_hashes"):
                with self.assertRaisesRegex(ValueError, "simulator differs"):
                    reconcile(plan, {"q3_K/rvv": run}, root / "out")

    def test_keeps_original_runs_and_replaces_only_verified_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, run = self.prepare(root)
            with patch("reconcile_fulltrace.check_hashes"), \
                 patch("reconcile_fulltrace.audit_campaign",
                       return_value={"status": "PASS"}):
                audit = reconcile(plan, {"q3_K/rvv": run}, root / "out")
            manifest = json.loads((root / "out/paired_manifest.json").read_text())
            self.assertEqual(audit["status"], "PASS")
            self.assertEqual(manifest["qbs_pairs"][0]["rvv_run"], str(run))
            self.assertEqual(manifest["qbs_pairs"][0]["qbs_run"], "old-qbs")

    def test_accepts_verified_case_left_untouched_by_stopped_campaign(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, run = self.prepare(root)
            payload = json.loads(plan.read_text())
            payload["cases"][0]["status"] = None
            plan.write_text(json.dumps(payload))
            with patch("reconcile_fulltrace.check_hashes"), \
                 patch("reconcile_fulltrace.audit_campaign",
                       return_value={"status": "PASS"}):
                audit = reconcile(plan, {"q3_K/rvv": run}, root / "out")
            self.assertEqual(audit["status"], "PASS")

    def test_resolves_frozen_sources_from_explicit_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, run = self.prepare(root)
            source_root = root / "sources"
            source_root.mkdir()
            payload = json.loads(plan.read_text())
            pair = payload["output_manifest"]["qbs_pairs"][0]
            pair["qbs_app"] = "apps/qbs"
            pair["rvv_app"] = "apps/rvv"
            for name in ("qbs", "rvv"):
                (source_root / "apps" / name).mkdir(parents=True)
            akv = payload["output_manifest"]["akv_pair"]
            for name in ("rvv_elf", "akv_elf", "rvv_asm", "akv_asm"):
                akv[name] = f"inputs/{name}"
                (source_root / "inputs").mkdir(exist_ok=True)
                (source_root / akv[name]).touch()
            plan.write_text(json.dumps(payload))
            with patch("reconcile_fulltrace.check_hashes"), \
                 patch("reconcile_fulltrace.audit_campaign",
                       return_value={"status": "PASS"}):
                reconcile(plan, {"q3_K/rvv": run}, root / "out", source_root)
            manifest = json.loads((root / "out/paired_manifest.json").read_text())
            self.assertEqual(manifest["qbs_pairs"][0]["qbs_app"],
                             str(source_root / "apps/qbs"))
            self.assertEqual(manifest["akv_pair"]["rvv_asm"],
                             str(source_root / "inputs/rvv_asm"))
            provenance = json.loads((root / "out/provenance.json").read_text())
            self.assertEqual(provenance["source_root"], str(source_root))
            self.assertEqual(json.loads(plan.read_text()), payload)

    def test_rejects_relative_source_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "sources"
            source_root.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (source_root / "escape").symlink_to(outside, target_is_directory=True)
            for source in ("../outside", "escape"):
                with self.subTest(source=source):
                    manifest = {"qbs_pairs": [{"qbs_app": source}], "akv_pair": {}}
                    with self.assertRaises(ValueError):
                        resolve_source_paths(manifest, source_root)

    def test_preserves_absolute_source_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "sources"
            source_root.mkdir()
            outside = root / "outside"
            outside.mkdir()
            manifest = {
                "qbs_pairs": [{name: str(outside) for name in ("qbs_app", "rvv_app")}],
                "akv_pair": {name: str(outside) for name in
                             ("rvv_elf", "akv_elf", "rvv_asm", "akv_asm")},
            }
            original = json.loads(json.dumps(manifest))
            resolve_source_paths(manifest, source_root)
            self.assertEqual(manifest, original)


if __name__ == "__main__":
    unittest.main()
