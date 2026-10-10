import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "uvm" / "analyze_store_b_ab.py"
SPEC = importlib.util.spec_from_file_location("analyze_store_b_ab", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StoreBAbAnalysisTest(unittest.TestCase):
    def test_matches_request_and_delayed_response_by_id(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.vcs.log"
            log.write_text("\n".join([
                "[CVXIF/EVENT] cycle=10 req_fire=1 req_id=2 insn=020661a7 "
                "resp_fire=0 resp_id=2 exc=0",
                "[CVXIF/EVENT] cycle=12 req_fire=0 req_id=2 insn=020661a7 "
                "resp_fire=1 resp_id=2 exc=0",
                "[CVXIF/EVENT] cycle=15 req_fire=1 req_id=3 insn=0205e007 "
                "resp_fire=1 resp_id=3 exc=0",
            ]))
            result = MODULE.summarize(MODULE.events(log), "020661a7")
            self.assertEqual(result["store_count"], 1)
            self.assertEqual(result["response_latency_sum"], 2)
            self.assertEqual(result["response_to_next_request_sum"], 3)
            self.assertEqual(result["unanswered_requests"], 0)

    def test_rejects_response_without_matching_request(self):
        with self.assertRaisesRegex(ValueError, "response without request"):
            MODULE.summarize([{"cycle": 10, "request": False, "response": True,
                               "response_id": 1}], "020661a7")


if __name__ == "__main__":
    unittest.main()
