import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ara_verify.spike_trace import CommitComparisonError, compare_commit_prefix, parse_spike_commits


ARA_HEADER = (
    "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,"
    "mem_addr,mem_rmask,mem_wmask,trap\n"
)
ARA_MEMORY_HEADER = (
    "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,"
    "mem_addr,mem_rmask,mem_wmask,mem_wdata,trap\n"
)


class SpikeTraceTests(unittest.TestCase):
    def test_unshifted_store_operand_is_explicit_and_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); spike=root/'spike'; ara=root/'ara'
            spike.write_text('core 0: 3 0x80000000 (0x00502223) mem 0x80001004 0x81\n')
            def write(value):
                ara.write_text(ARA_MEMORY_HEADER+
                    '1,retire,0,0,-1,80000000,00502223,0,0,80001004,00,f0,%x,0\n'%value)
            write(0x81)
            result=compare_commit_prefix(spike,ara,0x80000000,rvfi_store_data_layout='unshifted')
            self.assertEqual(result['status'],'MATCH')
            self.assertEqual(result['rvfi_store_data_layout'],'unshifted')
            self.assertEqual(compare_commit_prefix(spike,ara,0x80000000)['status'],'MISMATCH')
            write(0x80)
            self.assertEqual(compare_commit_prefix(spike,ara,0x80000000,
                rvfi_store_data_layout='unshifted')['status'],'MISMATCH')
            with self.assertRaises(CommitComparisonError):
                compare_commit_prefix(spike,ara,0x80000000,rvfi_store_data_layout='guess')

    def test_fault_probe_options_must_be_paired(self):
        for kwargs in ({"fault_vector_trace": Path("vector")}, {"fault_probe_log": Path("probe")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(CommitComparisonError):
                compare_commit_prefix(Path("spike"), Path("ara"), 0, **kwargs)

    def test_probed_partial_row_requires_all_checked_csrs_and_not_just_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike, ara, exceptions = root / "spike", root / "ara", root / "exceptions"
            exceptions.write_text("Exception @  20000, PC: 0000000080000004, "
                                  "Cause: Load Address Misaligned, \n")
            proof = {"index": 1, "pc": "0x0000000080000004", "instruction": "0xeece8a07",
                     "probe_next_time": 20000, "expected_fault_csrs": {
                         "0x341": 0x80000004, "0x342": 4, "0x343": 0x800050d1}}
            prefix = ("core 0: 3 0x80000000 (0x00100093) x1 0x1\n"
                      "core 0: 3 0x80000004 (0xeece8a07) e32 mf2 l3 "
                      "v20 0x0 c8_vstart 0x2 mem 0x800050ac\n")
            for omitted in (None, 0x341, 0x342, 0x343, "wrong_cause", "overwrite"):
                with self.subTest(omitted=omitted):
                    body = ""
                    rows = [(0x80000000, 0x00100093, 1, 1)]
                    reads = [(0x342, 4), (0x341, 0x80000004), (0x343, 0x800050d1)]
                    for i, (csr, value) in enumerate(reads):
                        if csr == omitted:
                            continue
                        if csr == 0x342 and omitted == "wrong_cause":
                            value = 5
                        if csr == 0x343 and omitted == "overwrite":
                            body += "core 0: 3 0x80001006 (0x34301073) c835_mtval 0x0\n"
                            rows.append((0x80001006, 0x34301073, 0, 0))
                        insn = csr << 20 | 0x2373
                        pc = 0x80001000 + i * 4
                        body += f"core 0: 3 0x{pc:x} (0x{insn:08x}) x6 0x{value:x}\n"
                        rows.append((pc, insn, 6, value))
                    spike.write_text(prefix + body)
                    ara.write_text(ARA_HEADER + "".join(
                        f"{i+1},retire,{i},0,-1,{pc:016x},{insn:08x},{rd},{value:016x},0,00,00,0\n"
                        for i, (pc, insn, rd, value) in enumerate(rows)))
                    with patch("ara_verify.vector_commit.prove_load_faults", return_value=[proof]):
                        result = compare_commit_prefix(
                            spike, ara, 0x80000000, rtl_exception_log=exceptions,
                            fault_vector_trace=root / "vector", fault_probe_log=root / "probe")
                    self.assertEqual(result["status"], "MATCH" if omitted is None else "MISMATCH")
                    default = compare_commit_prefix(spike, ara, 0x80000000, rtl_exception_log=exceptions)
                    self.assertEqual(default["status"], "MISMATCH")

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

    def test_fault_csr_evidence_requires_checked_reads_before_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike, ara, exceptions = root / "spike", root / "ara", root / "exceptions"
            exceptions.write_text("Exception @  20000, PC: 0000000080000004, "
                                  "Cause: Load Address Misaligned, \n")
            prefix = ("core 0: 3 0x80000000 (0x00100093) x1 0x1\n"
                      "core 0: 3 0x80000004 (0x27df7f07) e32 mf2 l8 c8_vstart 0x0\n")
            reads = [(0x34202373, 4), (0x34102373, 0x80000004),
                     (0x34302373, 0x80000002)]

            def write_traces(corrupt=None, overwrite=False):
                rows = [(0x80000000, 0x00100093, 1, 1)]
                body = ""
                if overwrite:
                    body += "core 0: 3 0x80001000 (0x34301073) c835_mtval 0x0\n"
                    rows.append((0x80001000, 0x34301073, 0, 0))
                for i, (insn, value) in enumerate(reads):
                    pc = 0x80001000 + (i + int(overwrite)) * 4
                    body += f"core 0: 3 0x{pc:x} (0x{insn:08x}) x6 0x{value:x}\n"
                    rows.append((pc, insn, 6, value ^ (1 if corrupt == i else 0)))
                spike.write_text(prefix + body)
                ara.write_text(ARA_HEADER + "".join(
                    f"{i+1},retire,{i},0,-1,{pc:016x},{insn:08x},{rd},{value:016x},0,00,00,0\n"
                    for i, (pc, insn, rd, value) in enumerate(rows)))

            write_traces()
            result = compare_commit_prefix(spike, ara, 0x80000000,
                                           rtl_exception_log=exceptions)
            self.assertEqual(result["status"], "MATCH")
            self.assertEqual(result["aligned_vector_faults"][0]["matched_fault_csrs"],
                             {"0x341": 0x80000004, "0x342": 4, "0x343": 0x80000002})
            for field in range(3):
                write_traces(corrupt=field)
                result = compare_commit_prefix(spike, ara, 0x80000000,
                                               rtl_exception_log=exceptions)
                self.assertEqual(result["status"], "MISMATCH")
            write_traces(overwrite=True)
            result = compare_commit_prefix(spike, ara, 0x80000000,
                                           rtl_exception_log=exceptions)
            self.assertNotIn("0x343", result["aligned_vector_faults"][0]["matched_fault_csrs"])

    def test_vector_fault_alignment_requires_matching_exception_and_handler(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            exceptions = root / "trace_hart_0.log"
            spike.write_text(
                "core 0: 3 0x0000000080000000 (0x00100093) x1 0x1\n"
                "core 0: 3 0x0000000080000004 (0x07678e87) "
                "e64 m1 l2 c8_vstart 0x1\n"
                "core 0: 3 0x0000000080001000 (0x34102373) "
                "x6 0x0000000080000004\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,00100093,1,0000000000000001,0,00,00,0\n"
                + "2,retire,1,0,-1,0000000080001000,34102373,6,0000000080000004,0,00,00,0\n",
                encoding="utf-8",
            )
            exceptions.write_text(
                "Exception @  20000, PC: 0000000080000004, "
                "Cause: Load Address Misaligned, \n",
                encoding="utf-8",
            )

            without_proof = compare_commit_prefix(spike, ara, 0x80000000)
            aligned = compare_commit_prefix(
                spike, ara, 0x80000000, rtl_exception_log=exceptions
            )
            self.assertEqual(without_proof["status"], "MISMATCH")
            self.assertEqual(aligned["status"], "MATCH")
            self.assertEqual(aligned["matched_instructions"], 2)
            self.assertEqual(aligned["aligned_vector_faults"][0]["pc"], "0x0000000080000004")

            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,00100093,1,0000000000000001,0,00,00,0\n"
                + "2,retire,1,0,-1,0000000080002000,34102373,6,0000000080000004,0,00,00,0\n",
                encoding="utf-8",
            )
            wrong_handler = compare_commit_prefix(
                spike, ara, 0x80000000, rtl_exception_log=exceptions
            )
            self.assertEqual(wrong_handler["status"], "MISMATCH")
            self.assertEqual(
                wrong_handler["mismatch"]["reason"], "vector_fault_handler_pc_mismatch"
            )

            ara.write_text(
                ARA_HEADER
                + "1,retire,0,0,-1,0000000080000000,00100093,1,0000000000000001,0,00,00,0\n"
                + "2,retire,1,0,-1,0000000080001000,34102373,6,0000000080000008,0,00,00,0\n",
                encoding="utf-8",
            )
            wrong_mepc = compare_commit_prefix(
                spike, ara, 0x80000000, rtl_exception_log=exceptions
            )
            self.assertEqual(wrong_mepc["status"], "MISMATCH")
            self.assertEqual(wrong_mepc["mismatch"]["reason"], "gpr_value")

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

    def test_equal_unobservable_value_does_not_hide_later_mismatch(self):
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
                + "1,retire,0,0,-1,0000000080000000,436020d7,1,0000000000000001,0,00,00,0\n"
                + "2,retire,0,0,-1,0000000080000004,0030d29b,5,0000000000000001,0,00,00,0\n",
                encoding="utf-8",
            )

            result = compare_commit_prefix(spike, ara, 0x80000000, {0})

            self.assertEqual(result["status"], "MISMATCH")
            self.assertEqual(result["matched_instructions"], 1)
            self.assertEqual(result["mismatch"]["reason"], "gpr_value")
            self.assertIsNone(result["stopped_at_unobservable"])
            self.assertEqual(result["skipped_unobservable_register_values"], 0)

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

    def test_explicit_terminal_ecall_matches_spike_handler_tail_only(self):
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
                + "2,retire,1,0,-1,0000000080000004,00000073,0,0,0,00,00,1\n",
                encoding="utf-8",
            )
            self.assertEqual(compare_commit_prefix(spike, ara, 0x80000000)["status"], "PREFIX")
            result = compare_commit_prefix(
                spike, ara, 0x80000000, terminal_ecall_pc=0x80000004,
            )
            self.assertEqual(result["status"], "TERMINAL_MATCH")
            self.assertEqual(result["terminal_ecall"]["pc"], "0x0000000080000004")
            self.assertEqual(result["matched_instructions"], 1)
            self.assertEqual(result["ara_committed_instructions"], 1)

            self.assertEqual(compare_commit_prefix(
                spike, ara, 0x80000000, terminal_ecall_pc=0x80000008,
            )["status"], "PREFIX")
            ara.write_text(ara.read_text().replace("00000073", "00100073"), encoding="utf-8")
            self.assertEqual(compare_commit_prefix(
                spike, ara, 0x80000000, terminal_ecall_pc=0x80000004,
            )["status"], "PREFIX")

    def test_explicit_success_tohost_store_matches_spike_tail_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike = root / "spike.log"
            ara = root / "ara.csv"
            spike.write_text(
                "core 0: 3 0x0000000080000000 (0x00102023) mem 0x80003000 0x1\n"
                "core 0: 3 0x0000000080000004 (0x0ff0000f)\n",
                encoding="utf-8",
            )
            ara.write_text(
                ARA_MEMORY_HEADER
                + "1,retire,0,0,-1,0000000080000000,00102023,0,0,"
                "0000000080003000,00,0f,0000000000000001,0\n",
                encoding="utf-8",
            )
            self.assertEqual(compare_commit_prefix(spike, ara, 0x80000000)["status"], "PREFIX")
            result = compare_commit_prefix(
                spike, ara, 0x80000000, terminal_tohost_address=0x80003000)
            self.assertEqual(result["status"], "TERMINAL_TOHOST_MATCH")
            self.assertEqual(result["terminal_tohost"]["write_value"], "0x1")
            self.assertEqual(result["matched_instructions"], 1)
            self.assertEqual(compare_commit_prefix(
                spike, ara, 0x80000000, terminal_tohost_address=0x80003008
            )["status"], "PREFIX")
            spike.write_text(spike.read_text().replace("0x1\n", "0x2\n"), encoding="utf-8")
            ara.write_text(ara.read_text().replace("0000000000000001", "0000000000000002"),
                           encoding="utf-8")
            self.assertEqual(compare_commit_prefix(
                spike, ara, 0x80000000, terminal_tohost_address=0x80003000
            )["status"], "PREFIX")
