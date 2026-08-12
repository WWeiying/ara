import tempfile
import unittest
from pathlib import Path

from ara_verify.trace import TraceValidationError, is_vector_instruction, validate_trace


HEADER = "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,trap\n"


class TraceTests(unittest.TestCase):
    def test_vector_instruction_classifier(self):
        self.assertTrue(is_vector_instruction(0x0205E007))
        self.assertTrue(is_vector_instruction(0x0D0572D7))
        self.assertTrue(is_vector_instruction(0x00905073))
        self.assertFalse(is_vector_instruction(0xF1462507))
        self.assertFalse(is_vector_instruction(0x30005073))

    def test_valid_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            path.write_text(
                HEADER
                + "1,retire,0,0,-1,0,00000013,0,0,0,00,00,0\n"
                + "2,cvx_req,-1,-1,3,0,0205e007,0,0,0,00,00,0\n"
                + "2,cvx_resp,-1,-1,3,0,00000000,0,0,0,00,00,0\n"
                + "3,retire,1,0,-1,0,0205e007,0,0,0,00,00,0\n",
                encoding="utf-8",
            )
            summary = validate_trace(path)
            self.assertEqual(summary["retire_count"], 2)
            self.assertEqual(summary["cvx_request_count"], 1)

    def test_rejects_orphan_response(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            path.write_text(
                HEADER + "1,cvx_resp,-1,-1,3,0,00000000,0,0,0,00,00,0\n",
                encoding="utf-8",
            )
            with self.assertRaises(TraceValidationError):
                validate_trace(path)

    def test_valid_backend_uop_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            path.write_text(
                HEADER
                + "1,arch_start,0,-1,3,0,0205e007,0,0,0,00,00,0\n"
                + "2,uop_alloc,0,2,3,0,0205e007,0,0,0,00,00,0\n"
                + "3,cvx_req,-1,-1,3,0,0205e007,0,0,0,00,00,0\n"
                + "3,cvx_resp,-1,-1,3,0,00000000,0,0,0,00,00,0\n"
                + "4,retire,0,0,-1,0,0205e007,0,0,0,00,00,0\n"
                + "5,uop_done,0,2,3,0,0205e007,0,0,0,00,00,0\n",
                encoding="utf-8",
            )
            summary = validate_trace(path)
            self.assertEqual(summary["architecture_request_count"], 1)
            self.assertEqual(summary["backend_uop_done_count"], 1)

    def test_allows_discarded_vector_csr_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            path.write_text(
                HEADER
                + "1,cvx_req,-1,-1,3,0,c2002073,0,0,0,00,00,0\n"
                + "1,cvx_resp,-1,-1,3,0,00000000,0,0,0,00,00,0\n"
                + "2,cvx_req,-1,-1,4,0,c2002073,0,0,0,00,00,0\n"
                + "2,cvx_resp,-1,-1,4,0,00000000,0,0,0,00,00,0\n"
                + "3,retire,0,0,-1,0,c2002073,0,0,0,00,00,0\n",
                encoding="utf-8",
            )
            summary = validate_trace(path)
            self.assertEqual(summary["cvx_replay_count"], 1)

    def test_allows_adjacent_side_effect_free_vector_csr_read_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            path.write_text(
                HEADER
                + "1,arch_start,0,-1,1,0,c20023f3,0,0,0,00,00,0\n"
                + "1,cvx_req,-1,-1,1,0,c20023f3,0,0,0,00,00,0\n"
                + "1,cvx_resp,-1,-1,1,0,00000000,0,0,0,00,00,0\n"
                + "2,arch_start,1,-1,2,0,c20023f3,0,0,0,00,00,0\n"
                + "2,cvx_req,-1,-1,2,0,c20023f3,0,0,0,00,00,0\n"
                + "2,cvx_resp,-1,-1,2,0,00000000,0,0,0,00,00,0\n"
                + "3,cvx_req,-1,-1,3,0,c20023f3,0,0,0,00,00,0\n"
                + "3,cvx_resp,-1,-1,3,0,00000000,0,0,0,00,00,0\n"
                + "4,retire,0,0,-1,0,c20023f3,7,4f,0,00,00,0\n"
                + "5,retire,1,0,-1,0,c20023f3,7,4f,0,00,00,0\n",
                encoding="utf-8",
            )

            summary = validate_trace(path)

            self.assertEqual(summary["cvx_replay_count"], 1)
            self.assertEqual(summary["arch_request_replay_count"], 1)

    def test_rejects_replayed_vector_data_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            path.write_text(
                HEADER
                + "1,cvx_req,-1,-1,3,0,0205e007,0,0,0,00,00,0\n"
                + "1,cvx_resp,-1,-1,3,0,00000000,0,0,0,00,00,0\n"
                + "2,cvx_req,-1,-1,4,0,0205e007,0,0,0,00,00,0\n"
                + "2,cvx_resp,-1,-1,4,0,00000000,0,0,0,00,00,0\n"
                + "3,retire,0,0,-1,0,0205e007,0,0,0,00,00,0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(TraceValidationError, "sequence length mismatch"):
                validate_trace(path)

    def test_allows_exception_response_without_rvfi_retire(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            path.write_text(
                HEADER
                + "1,cvx_req,-1,-1,3,0,6efe2157,0,0,0,00,00,0\n"
                + "2,cvx_resp,-1,-1,3,0,00000000,0,0,0,00,00,1\n",
                encoding="utf-8",
            )
            summary = validate_trace(path)
            self.assertEqual(summary["cvx_exception_count"], 1)

    def test_rejects_pending_backend_uop(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            path.write_text(
                HEADER
                + "1,arch_start,0,-1,3,0,0205e007,0,0,0,00,00,0\n"
                + "2,uop_alloc,0,2,3,0,0205e007,0,0,0,00,00,0\n"
                + "3,cvx_req,-1,-1,3,0,0205e007,0,0,0,00,00,0\n"
                + "3,cvx_resp,-1,-1,3,0,00000000,0,0,0,00,00,0\n"
                + "4,retire,0,0,-1,0,0205e007,0,0,0,00,00,0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(TraceValidationError, "backend uops in flight"):
                validate_trace(path)
