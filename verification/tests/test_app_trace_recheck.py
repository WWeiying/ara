import json
import tempfile
import unittest
from pathlib import Path

from ara_verify.artifacts import sha256, simulation_image
from ara_verify.recheck_app_trace import recheck

HEADER = "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,trap\n"


class AppTraceRecheckTests(unittest.TestCase):
    def test_rechecks_frozen_custom_instruction_without_changing_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "app_custom"
            artifact.mkdir()
            elf = artifact / "input.elf"
            elf.write_bytes(b"frozen elf")
            simv = root / "simv"
            simv.write_bytes(b"frozen simulator")
            Path(str(simv) + ".daidir").mkdir()
            (artifact / "inputs.json").write_text(json.dumps({
                "binary": {"path": str(elf), "sha256": sha256(elf)},
                "simv": {"path": str(simv), "image_sha256": simulation_image(simv)},
            }))
            (artifact / "console.log").write_text("Core Test *** SUCCESS ***\n")
            (artifact / "commit_trace.csv").write_text(
                HEADER
                + "1,cvx_req,-1,-1,2,0,00b5045b,0,0,0,00,00,0\n"
                + "2,cvx_resp,-1,-1,2,0,00000000,0,0,0,00,00,0\n"
                + "3,retire,0,0,-1,0,00b5045b,0,0,0,00,00,0\n"
            )
            summary = root / "summary.json"
            summary.write_text(json.dumps([
                {"name": "app:custom", "status": "FAIL", "returncode": 0,
                 "reason": "invalid commit trace: old classifier", "artifact_dir": str(artifact)},
                {"name": "app:already-pass", "status": "PASS", "returncode": 0,
                 "reason": "", "artifact_dir": str(artifact)},
                {"name": "app:long", "status": "TIMEOUT", "returncode": None,
                 "reason": "timeout after 300s", "artifact_dir": str(root / "app_long")},
            ]))

            report = recheck(summary)
            self.assertEqual(report["recheck_counts"],
                             {"PASS_AFTER_CHECKER_FIX": 1, "RECONFIRMED_PASS": 1,
                              "UNCHANGED": 1})
            elf.write_bytes(b"changed elf")
            report = recheck(summary)
            self.assertEqual(report["recheck_counts"], {"FAIL": 2, "UNCHANGED": 1})
            self.assertIn("frozen ELF identity mismatch", report["cases"][0]["issues"])


if __name__ == "__main__":
    unittest.main()
