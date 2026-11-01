import json
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))

from audit_final_random_stimulus import audit_profile
from ara_verify.stimulus_coverage import collect_stimulus_coverage
from run_verilator_coverage import sha256


class FinalRandomStimulusAuditTests(unittest.TestCase):
    def test_frozen_elf_and_assembly_coverage_are_rechecked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "generated"
            prior_run = root / "prior"
            final_run = root / "final"
            rows = []
            manifest = []
            sources = []
            audited_cases = []
            for index in range(10):
                name = f"random_{index}"
                source = generated / "asm_test" / f"{name}.S"
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("main:\n  vsetvli t0, a0, e32,m1,ta,ma\n"
                                  "  vadd.vv v1,v2,v3\ntest_done:\n")
                sources.append(source)
                original = generated / "tests" / name / "input.elf"
                old = prior_run / "tests" / name / "input.elf"
                final = final_run / "tests" / name / "input.elf"
                for elf in (original, old, final):
                    elf.parent.mkdir(parents=True, exist_ok=True)
                    elf.write_bytes(f"ELF {index}".encode())
                rows.append({"name": name, "source_elf": str(original), "elf": str(old)})
                manifest.append({"name": name, "elf": str(old)})
                (final.parent / "inputs.json").write_text(json.dumps({
                    "binary": {"path": str(final), "sha256": sha256(final)}}))
                audited_cases.append({"name": name, "status": "PASS", "errors": [],
                                      "artifact_dir": str(final.parent)})
            (generated / "stimulus_coverage.json").write_text(json.dumps(
                collect_stimulus_coverage(sources, "random")))
            prior_summary = prior_run / "summary.json"
            prior_summary.write_text(json.dumps(rows))
            (final_run / "replay_manifest.json").write_text(json.dumps(manifest))
            (final_run / "independent_audit.json").write_text(json.dumps({
                "status": "PASS", "case_count": 10, "cases": audited_cases,
                "policy": {"require_trace": True, "require_vector": True,
                           "require_full_match": True}}))
            self.assertEqual(audit_profile("random", final_run, prior_summary)["issues"], [])
            (final_run / "tests/random_0/input.elf").write_bytes(b"changed")
            self.assertIn("ELF provenance mismatch: random_0",
                          audit_profile("random", final_run, prior_summary)["issues"])


if __name__ == "__main__":
    unittest.main()
