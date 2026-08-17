import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ara_verify.rvv_postprocess import RvvPostprocessOptions, postprocess_existing_run


class RvvPostprocessTest(unittest.TestCase):
    def test_rebuilds_result_without_rerunning_simulation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "run"
            case = output / "tests" / "random_0"
            case.mkdir(parents=True)
            elf = root / "random_0.o"
            elf.write_bytes(b"elf")
            (case / "rtl.command.json").write_text(json.dumps({
                "command": [
                    "/tmp/simv", f"+PRELOAD={elf}", "+ntb_random_seed=7",
                    f"+COMMIT_TRACE={case / 'ara_commit_trace.csv'}",
                    f"+VECTOR_TRACE={case / 'ara_vector_trace.csv'}",
                ]
            }))
            (case / "rtl_console.log").write_text("Core Test *** SUCCESS ***\n")

            with patch("ara_verify.rvv_postprocess._elf_entry", return_value=0x80000000), \
                 patch("ara_verify.rvv_postprocess.unobservable_vector_scalar_write_indices",
                       return_value={11}), \
                 patch("ara_verify.rvv_postprocess.compare_commit_prefix",
                       return_value={"status": "PREFIX"}), \
                 patch("ara_verify.rvv_postprocess.validate_trace", return_value={"rows": 3}), \
                 patch("ara_verify.rvv_postprocess.compare_vector_commits",
                       return_value={"status": "PREFIX"}) as vector_compare:
                results = postprocess_existing_run(
                    RvvPostprocessOptions(output=output), root
                )

            self.assertEqual(results[0]["status"], "PASS")
            self.assertEqual(results[0]["seed"], 7)
            self.assertTrue(results[0]["postprocessed_existing_artifacts"])
            self.assertTrue((output / "summary.json").is_file())
            self.assertEqual(vector_compare.call_args.kwargs["stop_spike_index"], 11)

    def test_scalar_match_does_not_accept_vector_prefix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "run"
            case = output / "tests" / "random_0"
            case.mkdir(parents=True)
            elf = root / "random_0.o"
            elf.write_bytes(b"elf")
            (case / "rtl.command.json").write_text(json.dumps({
                "command": [
                    "/tmp/simv", f"+PRELOAD={elf}",
                    f"+COMMIT_TRACE={case / 'ara_commit_trace.csv'}",
                    f"+VECTOR_TRACE={case / 'ara_vector_trace.csv'}",
                ]
            }))
            (case / "rtl_console.log").write_text("Core Test *** SUCCESS ***\n")

            with patch("ara_verify.rvv_postprocess._elf_entry", return_value=0x80000000), \
                 patch("ara_verify.rvv_postprocess.unobservable_vector_scalar_write_indices",
                       return_value=set()), \
                 patch("ara_verify.rvv_postprocess.compare_commit_prefix",
                       return_value={"status": "MATCH"}), \
                 patch("ara_verify.rvv_postprocess.validate_trace", return_value={"rows": 3}), \
                 patch("ara_verify.rvv_postprocess.compare_vector_commits",
                       return_value={"status": "PREFIX"}):
                results = postprocess_existing_run(
                    RvvPostprocessOptions(output=output), root
                )

            self.assertEqual(results[0]["status"], "VECTOR_MISMATCH")

    def test_reports_missing_command_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "run"
            case = output / "tests" / "random_0"
            case.mkdir(parents=True)
            results = postprocess_existing_run(RvvPostprocessOptions(output=output), root)
            self.assertEqual(results[0]["status"], "ARTIFACT_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
