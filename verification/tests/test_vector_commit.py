import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ara_verify.spike_trace import SpikeCommit
from ara_verify.vector_commit import (
    ArchActivity,
    VectorCommitComparisonError,
    VectorRetire,
    _advance_unknown_state,
    _architectural_compare_mask,
    _deshuffle_byte,
    _is_non_bit_exact_vector_result,
    _map_spike_commits,
    _vector_scalar_source_unknown,
    compare_vector_commits,
    unobservable_vector_scalar_write_indices,
)


class VectorCommitComparisonTests(unittest.TestCase):
    def test_spike_mapping_can_preserve_a_strict_prefix(self):
        commits = [
            SpikeCommit(
                pc=0, instruction=0x57, gpr_writes={}, fpr_writes={},
                vector_writes={}, csr_writes={}, memory_accesses=(),
            )
        ]
        retires = {
            1: VectorRetire(pc=0, instruction=0x57),
            2: VectorRetire(pc=4, instruction=0x57),
        }
        with self.assertRaises(VectorCommitComparisonError):
            _map_spike_commits(retires, commits)
        self.assertEqual(
            _map_spike_commits(retires, commits, allow_incomplete_tail=True),
            {1: 0},
        )

    def test_vcpop_unknown_checks_only_active_source_and_predicate_bits(self):
        commit = SpikeCommit(
            pc=0, instruction=0x418827D7, gpr_writes={15: 0}, fpr_writes={},
            vector_writes={}, csr_writes={}, memory_accesses=(), vector_sew=8,
            vector_lmul="mf8", vector_vl=7, vector_vstart=0, vector_vtype=5,
            vector_tail_agnostic=False, vector_mask_agnostic=False,
        )
        self.assertTrue(_vector_scalar_source_unknown(commit, {24: 1 << 3}))
        self.assertTrue(_vector_scalar_source_unknown(commit, {0: 1 << 2}))
        self.assertFalse(_vector_scalar_source_unknown(commit, {24: 1 << 7}))
        self.assertFalse(
            _vector_scalar_source_unknown(
                commit, {24: 1 << 3}, {24: 0, 0: 0}
            )
        )
        self.assertTrue(
            _vector_scalar_source_unknown(
                commit, {24: 1 << 3}, {24: 0, 0: 1 << 3}
            )
        )
        unmasked = SpikeCommit(
            **{**commit.__dict__, "instruction": commit.instruction | (1 << 25)}
        )
        self.assertFalse(_vector_scalar_source_unknown(unmasked, {0: 1 << 2}))

    def test_vfirst_ignores_unknown_bits_after_a_definite_first_bit(self):
        commit = SpikeCommit(
            pc=0, instruction=0x4188A0D7, gpr_writes={1: 0}, fpr_writes={},
            vector_writes={}, csr_writes={}, memory_accesses=(), vector_sew=8,
            vector_lmul="mf8", vector_vl=7, vector_vstart=0, vector_vtype=5,
            vector_tail_agnostic=False, vector_mask_agnostic=False,
        )
        # Source and predicate are definitely one at bit 0, so uncertainty at
        # later bits cannot alter vfirst's scalar result.
        self.assertFalse(
            _vector_scalar_source_unknown(
                commit, {24: 1 << 3}, {24: 1, 0: (1 << 0) | (1 << 3)}
            )
        )
        # An uncertain effective bit before the first definite one can become
        # the first match and therefore makes the result unobservable.
        self.assertTrue(
            _vector_scalar_source_unknown(
                commit, {24: 1 << 1}, {24: 1 << 3, 0: (1 << 1) | (1 << 3)}
            )
        )

    def test_vector_scalar_unknown_is_checked_without_vrf_write_activity(self):
        producer = SpikeCommit(
            pc=0, instruction=0x57, gpr_writes={}, fpr_writes={},
            vector_writes={}, csr_writes={}, memory_accesses=(), vector_sew=64,
            vector_lmul="m1", vector_vl=1, vector_vstart=0, vector_vtype=3,
            vector_tail_agnostic=False, vector_mask_agnostic=False,
        )
        scalar_move = SpikeCommit(
            pc=4, instruction=0x436020D7, gpr_writes={1: 0}, fpr_writes={},
            vector_writes={}, csr_writes={}, memory_accesses=(), vector_sew=64,
            vector_lmul="m1", vector_vl=1, vector_vstart=0, vector_vtype=3,
            vector_tail_agnostic=False, vector_mask_agnostic=False,
        )

        def make_source_unknown(unknown_state, *_args):
            unknown_state[22] = 1

        with mock.patch(
            "ara_verify.vector_commit._parse_vector_trace",
            return_value=(4, 1024, {1: object()}),
        ), mock.patch(
            "ara_verify.vector_commit._parse_architecture_mapping",
            return_value=({}, {}, set()),
        ), mock.patch(
            "ara_verify.vector_commit._map_architecture_retires",
            return_value={1: object()},
        ), mock.patch(
            "ara_verify.vector_commit._spike_from_entry",
            return_value=[producer, scalar_move],
        ), mock.patch(
            "ara_verify.vector_commit._map_spike_commits",
            return_value={1: 0},
        ), mock.patch(
            "ara_verify.vector_commit._advance_unknown_state",
            side_effect=make_source_unknown,
        ):
            self.assertEqual(
                unobservable_vector_scalar_write_indices(
                    Path("spike.log"), Path("commit.csv"), Path("vector.csv"), 0
                ),
                {1},
            )

    def test_vector_scalar_unknown_uses_only_element_zero_at_current_sew(self):
        instruction = 0x436020D7  # vmv.x.s x1, v22
        commit = SpikeCommit(
            pc=0, instruction=instruction, gpr_writes={1: 0}, fpr_writes={},
            vector_writes={}, csr_writes={}, memory_accesses=(), vector_sew=16,
            vector_lmul="m1", vector_vl=1, vector_vstart=0, vector_vtype=1,
            vector_tail_agnostic=False, vector_mask_agnostic=False,
        )
        self.assertFalse(_vector_scalar_source_unknown(commit, {22: 0}))
        self.assertTrue(_vector_scalar_source_unknown(commit, {22: 1 << 8}))
        self.assertFalse(_vector_scalar_source_unknown(commit, {22: 1 << 16}))

    def test_agnostic_tail_unknown_survives_undisturbed_operation(self):
        vlen_bits = 128
        unknown = {}
        pre_state = {1: 0}
        agnostic = ArchActivity(
            instruction=0x020000D7, vd=1, eew=0, vl=5, vstart=0
        )
        agnostic_commit = SpikeCommit(
            pc=0, instruction=agnostic.instruction, gpr_writes={}, fpr_writes={},
            vector_writes={1: 0}, csr_writes={}, memory_accesses=(),
            vector_sew=8, vector_lmul="m1", vector_vl=5, vector_vstart=0,
            vector_vtype=0xC0, vector_tail_agnostic=True,
            vector_mask_agnostic=True,
        )
        _advance_unknown_state(
            unknown, agnostic, agnostic_commit, pre_state, vlen_bits
        )
        self.assertEqual(unknown[1] & 0xFFFFFFFFFF, 0)
        self.assertNotEqual(unknown[1] >> 40, 0)

        undisturbed = ArchActivity(
            instruction=0x5E0800D7, vd=1, eew=0, vl=5, vstart=0
        )
        undisturbed_commit = SpikeCommit(
            pc=4, instruction=undisturbed.instruction,
            gpr_writes={}, fpr_writes={}, vector_writes={1: 0},
            csr_writes={}, memory_accesses=(), vector_sew=8,
            vector_lmul="m1", vector_vl=5, vector_vstart=0,
            vector_vtype=0, vector_tail_agnostic=False,
            vector_mask_agnostic=False,
        )
        _advance_unknown_state(
            unknown, undisturbed, undisturbed_commit, {1: 0}, vlen_bits
        )
        self.assertEqual(unknown[1] & 0xFFFFFFFFFF, 0)
        self.assertNotEqual(unknown[1] >> 40, 0)

    def test_only_unordered_fp_sums_are_non_bit_exact(self):
        self.assertTrue(_is_non_bit_exact_vector_result(0x07891FD7))
        self.assertTrue(_is_non_bit_exact_vector_result((0x31 << 26) | (1 << 12) | 0x57))
        self.assertFalse(_is_non_bit_exact_vector_result((0x03 << 26) | (1 << 12) | 0x57))
        self.assertFalse(_is_non_bit_exact_vector_result((0x33 << 26) | (1 << 12) | 0x57))

    def test_non_bit_exact_reduction_taints_estimate_source_byte(self):
        vlen_bits = 1024
        unknown = {}
        reduction = ArchActivity(
            instruction=0xC4C596D7, vd=13, eew=3, vl=10, vstart=0
        )
        reduction_commit = SpikeCommit(
            pc=0, instruction=reduction.instruction, gpr_writes={},
            fpr_writes={}, vector_writes={13: 0}, csr_writes={},
            memory_accesses=(), vector_sew=32, vector_lmul="m1",
            vector_vl=10, vector_vstart=0, vector_vtype=0,
            vector_tail_agnostic=False, vector_mask_agnostic=False,
        )
        _advance_unknown_state(
            unknown, reduction, reduction_commit,
            {0: (1 << vlen_bits) - 1, 13: 0}, vlen_bits
        )
        self.assertEqual(unknown[13] & ((1 << 64) - 1), (1 << 64) - 1)
        self.assertEqual(unknown[13] >> 64, 0)

        estimate = ArchActivity(
            instruction=0x4ED21FD7, vd=31, eew=2, vl=10, vstart=0
        )
        estimate_commit = SpikeCommit(
            pc=4, instruction=estimate.instruction, gpr_writes={},
            fpr_writes={}, vector_writes={31: 0}, csr_writes={},
            memory_accesses=(), vector_sew=32, vector_lmul="m1",
            vector_vl=10, vector_vstart=0, vector_vtype=0,
            vector_tail_agnostic=False, vector_mask_agnostic=False,
        )
        _advance_unknown_state(
            unknown, estimate, estimate_commit, {13: 0, 31: 0}, vlen_bits
        )
        self.assertEqual(unknown[31] & ((1 << 64) - 1), (1 << 64) - 1)
        self.assertEqual(unknown[31] >> 64, 0)

        widening = ArchActivity(
            instruction=0xC2D72ED7, vd=29, eew=1, vl=14, vstart=0
        )
        widening_commit = SpikeCommit(
            pc=8, instruction=widening.instruction, gpr_writes={},
            fpr_writes={}, vector_writes={29: 0}, csr_writes={},
            memory_accesses=(), vector_sew=8, vector_lmul="mf8",
            vector_vl=14, vector_vstart=0, vector_vtype=5,
            vector_tail_agnostic=False, vector_mask_agnostic=False,
        )
        _advance_unknown_state(
            unknown, widening, widening_commit,
            {13: 0, 14: 0, 29: 0}, vlen_bits
        )
        self.assertEqual(unknown[29] & ((1 << 128) - 1), (1 << 128) - 1)
        self.assertEqual(unknown[29] >> 128, 0)

    def test_deshuffle_matches_ara_intra_lane_element_order(self):
        # Ara bit-reverses the element slot within each 64-bit lane for EW16/EW8.
        self.assertEqual(_deshuffle_byte(4, nr_lanes=4, eew=1), 8)
        self.assertEqual(_deshuffle_byte(2, nr_lanes=4, eew=1), 16)
        self.assertEqual(_deshuffle_byte(1, nr_lanes=4, eew=0), 16)
        self.assertEqual(_deshuffle_byte(2, nr_lanes=4, eew=0), 8)

    def test_mask_destination_skips_tail_bits(self):
        activity = ArchActivity(
            instruction=0x61DFB157, vd=2, eew=1, vl=14, vstart=0
        )
        mask = _architectural_compare_mask(
            activity, register=2, byte=1, vlen_bits=1024,
            pre_state={0: (1 << 1024) - 1}, destination_registers={2},
        )
        self.assertEqual(mask, 0x3F)

    def test_mask_destination_tail_is_unknown_under_tu_and_taints_data_use(self):
        vlen_bits = 1024
        unknown = {}
        mask_result = ArchActivity(
            instruction=0x6F9DA4D7, vd=9, eew=1, vl=61, vstart=0
        )
        mask_commit = SpikeCommit(
            pc=0, instruction=mask_result.instruction, gpr_writes={},
            fpr_writes={}, vector_writes={9: 0}, csr_writes={},
            memory_accesses=(), vector_sew=16, vector_lmul="m1",
            vector_vl=61, vector_vstart=0, vector_vtype=0,
            vector_tail_agnostic=False, vector_mask_agnostic=False,
        )
        _advance_unknown_state(
            unknown, mask_result, mask_commit, {9: 0}, vlen_bits
        )
        self.assertEqual(unknown[9] & ((1 << 61) - 1), 0)
        self.assertNotEqual(unknown[9] >> 61, 0)

        multiply = ArchActivity(
            instruction=0x96F4A5D7, vd=11, eew=1, vl=61, vstart=0
        )
        multiply_commit = SpikeCommit(
            pc=4, instruction=multiply.instruction, gpr_writes={},
            fpr_writes={}, vector_writes={11: 0}, csr_writes={},
            memory_accesses=(), vector_sew=16, vector_lmul="m1",
            vector_vl=61, vector_vstart=0, vector_vtype=0,
            vector_tail_agnostic=False, vector_mask_agnostic=False,
        )
        _advance_unknown_state(
            unknown, multiply, multiply_commit,
            {9: 0, 11: 0, 15: 0}, vlen_bits,
        )
        self.assertEqual(unknown[11] & ((1 << 48) - 1), 0)
        self.assertNotEqual(unknown[11] >> 48, 0)

    def test_vmsof_propagates_agnostic_source_into_prefix_result(self):
        vlen_bits = 1024
        unknown = {18: 1 << 1}
        vmsof = ArchActivity(
            instruction=0x512128D7, vd=17, eew=1, vl=146, vstart=0
        )
        commit = SpikeCommit(
            pc=0, instruction=vmsof.instruction, gpr_writes={}, fpr_writes={},
            vector_writes={17: 0}, csr_writes={}, memory_accesses=(),
            vector_sew=16, vector_lmul="m8", vector_vl=146, vector_vstart=0,
            vector_vtype=0, vector_tail_agnostic=False,
            vector_mask_agnostic=False,
        )
        # Element zero is masked off. Element one is active and its source bit
        # is agnostic, so both its result and later prefix state are uncertain.
        _advance_unknown_state(
            unknown, vmsof, commit,
            {0: ((1 << 146) - 1) & ~1, 17: 1, 18: 1 << 2}, vlen_bits,
        )
        self.assertTrue(unknown[17] & (1 << 1))
        self.assertTrue(unknown[17] & (1 << 2))
        self.assertFalse(unknown[17] & 1)

    def test_mask_comparison_propagates_source_element_uncertainty(self):
        vlen_bits = 1024
        # vmsleu.vv v3,v16,v8: taint one byte of e16 element five in v16.
        unknown = {16: 0xFF << (8 * 10)}
        compare = ArchActivity(
            instruction=0x730401D7, vd=3, eew=1, vl=146, vstart=0
        )
        commit = SpikeCommit(
            pc=0, instruction=compare.instruction, gpr_writes={}, fpr_writes={},
            vector_writes={3: 0}, csr_writes={}, memory_accesses=(),
            vector_sew=16, vector_lmul="m8", vector_vl=146, vector_vstart=0,
            vector_vtype=0, vector_tail_agnostic=False,
            vector_mask_agnostic=False,
        )
        _advance_unknown_state(
            unknown, compare, commit, {3: 0, 8: 0, 16: 0}, vlen_bits
        )
        self.assertTrue(unknown[3] & (1 << 5))
        self.assertFalse(unknown[3] & (1 << 4))

    def test_data_destination_keeps_active_elements_strict(self):
        activity = ArchActivity(
            instruction=0x94C8BE57, vd=28, eew=3, vl=61, vstart=0
        )
        mask = _architectural_compare_mask(
            activity, register=30, byte=2, vlen_bits=1024,
            pre_state={0: (1 << 1024) - 1}, destination_registers={28, 29, 30, 31},
        )
        self.assertEqual(mask, 0xFF)

    def test_tail_undisturbed_and_prestart_bytes_remain_strict(self):
        activity = ArchActivity(
            instruction=0xA7083A57, vd=20, eew=3, vl=29, vstart=4
        )
        prestart = _architectural_compare_mask(
            activity, register=20, byte=0, vlen_bits=1024,
            pre_state={0: 0}, destination_registers={20, 21},
            tail_agnostic=False, mask_agnostic=False,
        )
        tail = _architectural_compare_mask(
            activity, register=21, byte=120, vlen_bits=1024,
            pre_state={0: 0}, destination_registers={20, 21},
            tail_agnostic=False, mask_agnostic=False,
        )
        self.assertEqual(prestart, 0xFF)
        self.assertEqual(tail, 0xFF)

    def _write_fixture(self, root: Path, actual_word: str = "0000000044332211"):
        instruction = "02000057"
        pc = "0000000080000000"
        commit_trace = root / "commit.csv"
        commit_trace.write_text(
            "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap\n"
            f"1,arch_start,0,-1,0,0000000000000000,{instruction},0,0,0,00,00,0,0\n"
            f"2,retire,0,0,-1,{pc},{instruction},0,0,0,00,00,0,0\n",
            encoding="utf-8",
        )
        vector_trace = root / "vector.csv"
        vector_trace.write_text(
            "cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,wdata,nr_lanes,vlen_bits\n"
            "0,config,0,0,0,0,00000000,0,0,0,0,0,0,00,0000000000000000,4,1024\n"
            f"1,alloc,0,0,0,0,{instruction},1,1,2,1,0,0,00,0000000000000000,4,1024\n"
            f"3,write,0,0,0,0,{instruction},1,1,2,1,0,4,0f,{actual_word},4,1024\n"
            f"4,done,0,0,0,0,{instruction},1,1,2,1,0,0,00,0000000000000000,4,1024\n",
            encoding="utf-8",
        )
        spike_log = root / "spike.log"
        spike_log.write_text(
            f"core   0: 3 0x{pc} (0x{instruction}) v1 0x0000000044332211\n",
            encoding="utf-8",
        )
        return spike_log, commit_trace, vector_trace

    def test_compares_one_vector_instruction_writeback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._write_fixture(root)
            result = compare_vector_commits(*paths, entry=0x80000000, selected_index=1)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["compared_instructions"], 1)
            self.assertEqual(result["compared_bytes"], 4)
            self.assertEqual(result["instructions"][0]["pc"], "0x0000000080000000")

    def test_reports_exact_first_vector_byte_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._write_fixture(root, actual_word="0000000044332210")
            result = compare_vector_commits(*paths, entry=0x80000000, selected_index=1)
            self.assertEqual(result["status"], "MISMATCH")
            mismatch = result["first_mismatch"]["first_mismatch"]
            self.assertEqual(mismatch["register"], "v1")
            self.assertEqual(mismatch["byte"], 0)
            self.assertEqual(mismatch["expected"], "0x11")
            self.assertEqual(mismatch["actual"], "0x10")
            self.assertEqual(mismatch["source"], "ALU")

    def test_unknown_write_data_is_not_reported_as_a_false_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._write_fixture(root, actual_word="xxxxxxxxxxxxxxxx")
            result = compare_vector_commits(*paths, entry=0x80000000, selected_index=1)
            self.assertEqual(result["status"], "UNOBSERVABLE")
            record = result["instructions"][0]
            self.assertEqual(record["compared_bytes"], 0)
            self.assertEqual(record["unknown_write_bytes"], 4)

    def test_reports_changed_destination_byte_missing_from_partial_writeback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike, commit, vector = self._write_fixture(root)
            # Establish a known old destination, then make the checked request
            # change two active words while Ara only writes the first one.
            spike.write_text(
                "core   0: 3 0x0000000080000000 (0x020000d7) "
                "v1 0x8877665588776655\n"
                "core   0: 3 0x0000000080000004 (0x02000057) "
                "v1 0x4433221144332211\n",
                encoding="utf-8",
            )
            commit.write_text(
                "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap\n"
                "1,arch_start,0,-1,0,0000000000000000,020000d7,0,0,0,00,00,0,0\n"
                "2,retire,0,0,-1,0000000080000000,020000d7,0,0,0,00,00,0,0\n"
                "3,arch_start,1,-1,1,0000000000000000,02000057,0,0,0,00,00,0,0\n"
                "4,retire,1,0,-1,0000000080000004,02000057,0,0,0,00,00,0,0\n",
                encoding="utf-8",
            )
            vector.write_text(
                "cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,wdata,nr_lanes,vlen_bits\n"
                "0,config,0,0,0,0,00000000,0,0,0,0,0,0,00,0000000000000000,4,1024\n"
                "1,alloc,0,0,0,0,020000d7,1,1,2,2,0,0,00,0000000000000000,4,1024\n"
                "2,write,0,0,0,0,020000d7,1,1,2,2,0,4,ff,8877665588776655,4,1024\n"
                "2,done,0,0,0,0,020000d7,1,1,2,2,0,0,00,0000000000000000,4,1024\n"
                "3,alloc,1,1,0,0,02000057,1,1,2,2,0,0,00,0000000000000000,4,1024\n"
                "4,write,1,1,0,0,02000057,1,1,2,2,0,4,0f,0000000044332211,4,1024\n"
                "4,done,1,1,0,0,02000057,1,1,2,2,0,0,00,0000000000000000,4,1024\n",
                encoding="utf-8",
            )
            result = compare_vector_commits(
                spike, commit, vector, entry=0x80000000, selected_index=2
            )
            self.assertEqual(result["status"], "MISMATCH")
            mismatch = result["first_mismatch"]["first_mismatch"]
            self.assertEqual(mismatch["reason"], "missing_changed_vrf_write")
            self.assertEqual(mismatch["register"], "v1")
            self.assertEqual(mismatch["byte"], 4)

    def test_unordered_fp_reduction_is_not_compared_bit_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike, commit, vector = self._write_fixture(
                root, actual_word="0000000044332210"
            )
            unordered = "040010d7"  # vfredusum.vs v1,v0,v0
            for path in (spike, commit, vector):
                path.write_text(
                    path.read_text(encoding="utf-8").replace("02000057", unordered),
                    encoding="utf-8",
                )
            result = compare_vector_commits(
                spike, commit, vector, entry=0x80000000, selected_index=1
            )
            self.assertEqual(result["status"], "UNOBSERVABLE")
            self.assertEqual(result["non_bit_exact_instructions"], 1)
            self.assertEqual(result["instructions"][0]["status"], "NON_BIT_EXACT")
            self.assertIsNone(result["first_mismatch"])

    def test_observable_prefix_is_not_failed_by_later_unknown_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike, commit, vector = self._write_fixture(root)
            with spike.open("a", encoding="utf-8") as file:
                file.write(
                    "core   0: 3 0x0000000080000004 (0x02000157) "
                    "v2 0x0000000000000000\n"
                )
            with commit.open("a", encoding="utf-8") as file:
                file.write(
                    "3,arch_start,1,-1,1,0000000000000000,02000157,0,0,0,00,00,0,0\n"
                    "4,retire,1,0,-1,0000000080000004,02000157,0,0,0,00,00,0,0\n"
                )
            with vector.open("a", encoding="utf-8") as file:
                file.write(
                    "3,alloc,1,1,0,0,02000157,1,2,2,1,0,0,00,0000000000000000,4,1024\n"
                    "4,write,1,1,0,0,02000157,1,2,2,1,0,8,0f,xxxxxxxxxxxxxxxx,4,1024\n"
                    "4,done,1,1,0,0,02000157,1,2,2,1,0,0,00,0000000000000000,4,1024\n"
                )
            result = compare_vector_commits(spike, commit, vector, entry=0x80000000)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["compared_instructions"], 2)
            self.assertEqual(result["unobservable_instructions"], 1)

    def test_trapped_architecture_request_does_not_consume_next_retirement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike, commit, vector = self._write_fixture(root)
            trapped = "eb1b0907"
            valid = "02000057"
            commit.write_text(
                "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap\n"
                f"1,arch_start,0,-1,2,0000000000000000,{trapped},0,0,0,00,00,0,0\n"
                f"1,cvx_req,-1,-1,2,0000000000000000,{trapped},0,0,0,00,00,0,0\n"
                "1,cvx_resp,-1,-1,2,0000000000000000,00000000,0,0,0,00,00,0,1\n"
                f"2,arch_start,1,-1,3,0000000000000000,{valid},0,0,0,00,00,0,0\n"
                f"3,retire,0,0,-1,0000000080000000,{valid},0,0,0,00,00,0,0\n",
                encoding="utf-8",
            )
            vector.write_text(
                vector.read_text(encoding="utf-8").replace(
                    ",0,0,0,0,02000057,", ",1,0,0,0,02000057,"
                ),
                encoding="utf-8",
            )
            result = compare_vector_commits(spike, commit, vector, entry=0x80000000)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["trapped_requests"], [0])
            self.assertEqual(result["instructions"][0]["arch_seq"], 1)

    def test_incomplete_tail_reports_a_compared_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike, commit, vector = self._write_fixture(root)
            with vector.open("a", encoding="utf-8") as file:
                file.write(
                    "5,alloc,1,1,0,0,020000d7,1,2,2,1,0,0,00,"
                    "0000000000000000,4,1024\n"
                )
            with commit.open("a", encoding="utf-8") as file:
                file.write(
                    "5,arch_start,1,-1,1,0000000000000000,020000d7,0,0,0,00,00,0,0\n"
                )
            result = compare_vector_commits(spike, commit, vector, entry=0x80000000)
            self.assertEqual(result["status"], "PREFIX")
            self.assertEqual(result["compared_instructions"], 1)
            self.assertEqual(result["incomplete_requests"], [1])
            self.assertEqual(result["unretired_requests"], [1])


if __name__ == "__main__":
    unittest.main()
