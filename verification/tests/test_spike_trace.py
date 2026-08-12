import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ara_verify.spike_trace import compare_commit_prefix, parse_spike_commits


ARA_HEADER = (
    "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,"
    "mem_addr,mem_rmask,mem_wmask,trap\n"
)
ARA_MEMORY_HEADER = (
    "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,"
    "mem_addr,mem_rmask,mem_wmask,mem_wdata,trap\n"
)


class SpikeTraceTests(unittest.TestCase):
    def test_commit_comparison_streams_input_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            spike.write_text(
                "core 0: 3 0x0000000080000000 (0x00100093) x1 0x1\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,00100093,1,"
                "0000000000000001,0,00,00,0\n",
                encoding="utf-8",
            )

            with patch.object(Path, "read_text", side_effect=AssertionError("not streaming")):
                result = compare_commit_prefix(spike, ara, 0x80000000)

            self.assertEqual(result["status"], "MATCH")

    def test_parse_vector_and_scalar_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spike.log"
            path.write_text(
                "core   0: 3 0x0000000080000000 (0x0d857b57) "
                "x22 0x0000000000000010 v2 0x1234 c3104_vl 0x10\n",
                encoding="utf-8",
            )
            commits = parse_spike_commits(path)
            self.assertEqual(commits[0].gpr_writes[22], 0x10)
            self.assertEqual(commits[0].vector_writes[2], 0x1234)
            self.assertEqual(commits[0].csr_writes[3104], 0x10)

    def test_parse_vector_context_uses_pre_instruction_vstart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spike.log"
            path.write_text(
                "core   0: 3 0x0000000080000000 (0x00007057) "
                "c3105_vtype 0x00000000000000c1\n"
                "core   0: 3 0x0000000080000002 (0x00809073) "
                "c8_vstart 0x0000000000000003\n"
                "core   0: 3 0x0000000080000004 (0x02000057) "
                "e16 mf2 l14 v1 0x1234 c8_vstart 0x0000000000000000\n",
                encoding="utf-8",
            )
            commits = parse_spike_commits(path)
            vector = commits[2]
            self.assertEqual(vector.vector_sew, 16)
            self.assertEqual(vector.vector_lmul, "mf2")
            self.assertEqual(vector.vector_vl, 14)
            self.assertEqual(vector.vector_vstart, 3)
            self.assertEqual(vector.vector_vtype, 0xC1)
            self.assertTrue(vector.vector_tail_agnostic)
            self.assertTrue(vector.vector_mask_agnostic)

    def test_matching_prefix_reports_next_reference_instruction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            spike.write_text(
                "core 0: 3 0x0000000000001000 (0x00000297) x5 0x1000\n"
                "core 0: 3 0x0000000080000000 (0x00100093) x1 0x1\n"
                "core 0: 3 0x0000000080000004 (0x00200113) x2 0x2\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,00100093,1,0000000000000001,0,00,00,0\n",
                encoding="utf-8",
            )
            result = compare_commit_prefix(spike, ara, 0x80000000)
            self.assertEqual(result["status"], "PREFIX")
            self.assertEqual(result["matched_instructions"], 1)
            self.assertEqual(result["next_spike"]["pc"], "0x0000000080000004")
            self.assertEqual(
                result["matched_prefix_scalar_state"]["nonzero_registers"],
                {"x1": "0x0000000000000001"},
            )

    def test_scalar_value_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            spike.write_text(
                "core 0: 3 0x0000000080000000 (0x00100093) x1 0x1\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,00100093,1,0000000000000002,0,00,00,0\n",
                encoding="utf-8",
            )
            result = compare_commit_prefix(spike, ara, 0x80000000)
            self.assertEqual(result["status"], "MISMATCH")
            self.assertEqual(result["mismatch"]["reason"], "gpr_value")

    def test_explicitly_unobservable_register_value_keeps_structure_strict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            spike.write_text(
                "core 0: 3 0x0000000080000000 (0x436020d7) x1 0x1\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,436020d7,1,0000000000000002,0,00,00,0\n",
                encoding="utf-8",
            )
            strict = compare_commit_prefix(spike, ara, 0x80000000)
            relaxed = compare_commit_prefix(spike, ara, 0x80000000, {0})
            self.assertEqual(strict["status"], "MISMATCH")
            self.assertEqual(relaxed["status"], "MATCH")
            self.assertEqual(relaxed["skipped_unobservable_register_values"], 1)

            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000004,436020d7,1,0000000000000002,0,00,00,0\n",
                encoding="utf-8",
            )
            wrong_pc = compare_commit_prefix(spike, ara, 0x80000000, {0})
            self.assertEqual(wrong_pc["status"], "MISMATCH")
            self.assertEqual(wrong_pc["mismatch"]["reason"], "pc_or_instruction")

    def test_unobservable_register_value_stops_before_dependent_scalar_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            spike.write_text(
                "core 0: 3 0x0000000080000000 (0x436020d7) x1 0x1\n"
                "core 0: 3 0x0000000080000004 (0x0030d29b) x5 0x0\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,436020d7,1,0000000000000002,0,00,00,0\n"
                + "2,retire,0,0,-1,0000000080000004,0030d29b,5,0000000000000001,0,00,00,0\n",
                encoding="utf-8",
            )

            result = compare_commit_prefix(spike, ara, 0x80000000, {0})

            self.assertEqual(result["status"], "PREFIX")
            self.assertIsNone(result["mismatch"])
            self.assertEqual(result["matched_instructions"], 1)
            self.assertEqual(result["stopped_at_unobservable"]["index"], 0)

    def test_missing_ara_scalar_write_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            spike.write_text(
                "core 0: 3 0x0000000080000000 (0x00100093) x1 0x1\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,00100093,0,0,0,00,00,0\n",
                encoding="utf-8",
            )
            result = compare_commit_prefix(spike, ara, 0x80000000)
            self.assertEqual(result["status"], "MISMATCH")
            self.assertEqual(result["mismatch"]["reason"], "gpr_write_set")

    def test_unknown_ara_scalar_value_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            spike.write_text(
                "core 0: 3 0x0000000080000000 (0x0002b383) x7 0x1234\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,0002b383,7,xxxxxxxxxxxxxxxx,0,ff,00,0\n",
                encoding="utf-8",
            )
            result = compare_commit_prefix(spike, ara, 0x80000000)
            self.assertEqual(result["status"], "MISMATCH")
            self.assertEqual(result["mismatch"]["reason"], "unknown_register_value")
            self.assertEqual(result["mismatch"]["ara"]["rd_value"], "xxxxxxxxxxxxxxxx")

    def test_fpr_write_uses_fpr_namespace_including_f0(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for register in (0, 7):
                with self.subTest(register=register):
                    spike = root / f"spike_f{register}.log"
                    ara = root / f"ara_f{register}.csv"
                    spike.write_text(
                        "core 0: 3 0x0000000080000000 (0x02000053) "
                        f"f{register} 0x3ff0000000000000\n",
                        encoding="utf-8",
                    )
                    ara.write_text(
                        ARA_HEADER
                        + "1,retire,0,0,-1,0000000080000000,02000053,"
                        f"{register},3ff0000000000000,0,00,00,0\n",
                        encoding="utf-8",
                    )
                    result = compare_commit_prefix(spike, ara, 0x80000000)
                    self.assertEqual(result["status"], "MATCH")
                    self.assertEqual(result["matched_floating_writes"], 1)
                    self.assertEqual(
                        result["matched_prefix_floating_state"]["nonzero_registers"],
                        {f"f{register}": "0x3ff0000000000000"},
                    )

    def test_unaligned_scalar_store_address_mask_and_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            spike.write_text(
                "core 0: 3 0x0000000080000000 (0x00112023) "
                "mem 0x0000000000001002 0x0000000011223344\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_MEMORY_HEADER
                + "1,retire,0,0,-1,0000000080000000,00112023,0,0,"
                "0000000000001002,00,3c,0000112233440000,0\n",
                encoding="utf-8",
            )
            result = compare_commit_prefix(spike, ara, 0x80000000)
            self.assertEqual(result["status"], "MATCH")
            self.assertEqual(result["matched_scalar_memory_accesses"], 1)

    def test_trap_marked_rvfi_row_omitted_by_spike_is_accounted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            spike.write_text(
                "core 0: 3 0x0000000080000000 (0x00100093) x1 0x1\n"
                "core 0: 3 0x0000000080000100 (0x00200113) x2 0x2\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,00100093,1,0000000000000001,0,00,00,0\n"
                + "2,retire,1,0,-1,0000000080000004,00000073,0,0,0,00,00,1\n"
                + "3,retire,2,0,-1,0000000080000100,00200113,2,0000000000000002,0,00,00,0\n",
                encoding="utf-8",
            )

            result = compare_commit_prefix(spike, ara, 0x80000000)

            self.assertEqual(result["status"], "MATCH")
            self.assertEqual(result["ara_retired_instructions"], 3)
            self.assertEqual(result["ara_committed_instructions"], 2)
            self.assertEqual(result["ara_trap_events"], 1)
