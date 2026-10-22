import importlib.util
import unittest
import csv
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "uvm" / "analyze_store_b_probe.py"
SPEC = importlib.util.spec_from_file_location("analyze_store_b_probe", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StoreBProbeAnalysisTest(unittest.TestCase):
    def test_extended_probe_keeps_base_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probe.csv"
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=sorted(MODULE.REQUIRED) + ["ar_addr"])
                writer.writeheader()
                writer.writerow({**dict.fromkeys(MODULE.REQUIRED, 0),
                                 "cycle": 42, "cvx_req_insn": "020661a7",
                                 "ar_addr": "deadbeef"})
            rows = MODULE.load(path)
            self.assertEqual(rows[0]["cycle"], 42)
            self.assertEqual(rows[0]["cvx_req_insn"], 0x020661a7)
            self.assertNotIn("ar_addr", rows[0])
            path.write_text("cycle,ar_addr\n42,deadbeef\n")
            with self.assertRaisesRegex(ValueError, "unexpected probe columns"):
                MODULE.load(path)

    def test_tracks_b_after_early_store_response_and_next_request(self):
        rows = [{**dict.fromkeys(MODULE.REQUIRED, 0), "cycle": cycle}
                for cycle in range(11)]
        store = int("020661a7", 16)
        rows[1].update(cvx_req_valid=1, cvx_req_insn=store, seq_wait=1)
        rows[2].update(cvx_req_valid=1, cvx_req_ready=1, cvx_req_insn=store,
                       cvx_resp_valid=1)
        rows[3].update(cvx_req_valid=1, cvx_req_ready=1, cvx_req_insn=0x0205e007)
        rows[5]["wlast_fire"] = 1
        rows[6].update(b_valid=1, b_ready=1)
        rows[7]["store_complete"] = 1
        rows[9].update(cvx_req_valid=1, cvx_req_insn=store)

        result = MODULE.first_store(rows, store)
        self.assertEqual(result["first_store_accept"], 2)
        self.assertEqual(result["next_accepted_request"], 3)
        self.assertEqual(result["first_wlast_fire"], 5)
        self.assertEqual(result["first_b_fire"], 6)
        self.assertEqual(result["first_vstu_complete"], 7)
        self.assertEqual(result["next_store_offer"], 9)

    def test_interval_counts_commit_slots_and_handshakes(self):
        rows = [{**dict.fromkeys(MODULE.REQUIRED, 0), "cycle": cycle}
                for cycle in range(4)]
        rows[1].update(commit_ack=3, cvx_req_valid=1, cvx_req_ready=1,
                       seq_wait=1, vstu_pending_b=1)
        rows[2].update(ara_req_valid=1, ara_req_ready=0, b_valid=1, b_ready=1)
        counts = MODULE.interval_counts(rows, 1, 3)
        self.assertEqual(counts["commit_slots"], 2)
        self.assertEqual(counts["cvx_request_fires"], 1)
        self.assertEqual(counts["sequencer_wait_cycles"], 1)
        self.assertEqual(counts["b_fires"], 1)
        with self.assertRaisesRegex(ValueError, "not fully covered"):
            MODULE.interval_counts(rows, 1, 5)


if __name__ == "__main__":
    unittest.main()
