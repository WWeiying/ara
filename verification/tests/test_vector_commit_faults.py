import copy
import csv
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ara_verify.spike_trace import CommitComparisonError, SpikeCommit, compare_commit_prefix
from ara_verify.vector_commit import (
    ArchActivity, VectorCommitComparisonError, VectorWrite,
    _fault_probe_pair, _prove_load_fault_bytes, compare_vector_commits,
    prove_load_faults, unobservable_vector_scalar_write_indices,
)


class LoadFaultByteProofTests(unittest.TestCase):
    def setUp(self):
        self.insn = 0xeece8a07
        self.commit = SpikeCommit(
            0x800005c2, self.insn, {}, {}, {reg: 0 for reg in range(20, 28)}, {8: 2}, (),
            vector_sew=32, vector_lmul="mf2", vector_vl=3, vector_vstart=1,
        )
        self.pre = {reg: 0 for reg in range(20, 28)}
        self.prior = {(reg, byte): (0, None) for reg in self.pre for byte in range(128)}
        maintenance = [self.write(20, lane, word, 3, 255, row=word * 4 + lane)
                       for word in range(4) for lane in range(4)]
        loads = [[self.write(reg, 1, 0, 4, 15, row=20 + reg)] for reg in range(20, 28)]
        self.groups = [maintenance] + loads

    def write(self, reg, lane, word, source, be, row):
        return VectorWrite(row, row + 10, 126, 0, lane, source, self.insn,
                           2, reg * 4 + word, be, 0, 255)

    def prove(self, groups=None, commit=None, unknown=None, prior=None):
        groups = self.groups if groups is None else groups
        activity = ArchActivity(self.insn, writes=[write for group in groups for write in group])
        return _prove_load_fault_bytes(activity, commit or self.commit, self.pre, unknown or {},
                                       self.prior if prior is None else prior, groups, 2, 4, 1024)

    def test_required_bytes_count_even_when_pre_and_post_are_identical(self):
        result = self.prove()
        self.assertEqual(result["required_load_bytes"], 32)
        self.assertEqual(result["verified_load_bytes"], 32)
        self.assertEqual(result["accepted_byte_events"], 160)
        self.assertEqual(result["duplicate_bytes"], 4)
        self.assertEqual(result["full_destination_bytes"], 1024)

    def test_missing_or_disabled_load_is_not_replaced_by_maintenance(self):
        for group in ([], [replace(self.groups[1][0], be=0)]):
            with self.subTest(group=group), self.assertRaisesRegex(
                    VectorCommitComparisonError, "missing required"):
                self.prove([self.groups[0], group] + self.groups[2:])

    def test_missing_maintenance_byte_fails_even_if_later_load_restores_it(self):
        groups = copy.deepcopy(self.groups)
        groups[0][1] = replace(groups[0][1], be=254)
        with self.assertRaisesRegex(VectorCommitComparisonError, "incomplete maintenance"):
            self.prove(groups)

    def test_corrupt_then_restored_maintenance_is_rejected(self):
        groups = copy.deepcopy(self.groups)
        groups[0][1] = replace(groups[0][1], data=1)
        with self.assertRaisesRegex(VectorCommitComparisonError, "maintenance changed"):
            self.prove(groups)

    def test_load_mismatch_and_unknown_data_fail(self):
        for bad in (replace(self.groups[1][0], data=1),
                    replace(self.groups[1][0], known_be=254)):
            with self.subTest(bad=bad), self.assertRaises(VectorCommitComparisonError):
                self.prove([self.groups[0], [bad]] + self.groups[2:])

    def test_duplicate_loads_within_and_across_uops_fail(self):
        for groups in ([self.groups[0], self.groups[1] * 2] + self.groups[2:],
                       self.groups + [self.groups[1]]):
            with self.subTest(groups=len(groups)), self.assertRaisesRegex(
                    VectorCommitComparisonError, "duplicate"):
                self.prove(groups)

    def test_load_outside_completed_interval_and_wrong_eew_fail(self):
        for bad in (replace(self.groups[1][0], lane=2), replace(self.groups[1][0], eew=3)):
            with self.subTest(bad=bad), self.assertRaises(VectorCommitComparisonError):
                self.prove([self.groups[0], [bad]] + self.groups[2:])

    def test_maintenance_after_load_fails(self):
        with self.assertRaisesRegex(VectorCommitComparisonError, "out-of-order"):
            self.prove(self.groups[1:] + self.groups[:1])

    def test_accepted_cycle_order_not_allocation_order_controls_duplicates(self):
        for cycle in (self.groups[1][0].cycle, self.groups[1][0].cycle + 1):
            groups = copy.deepcopy(self.groups)
            groups[0][1] = replace(groups[0][1], cycle=cycle)
            with self.subTest(cycle=cycle), self.assertRaisesRegex(
                    VectorCommitComparisonError, "accepted-cycle order"):
                self.prove(groups)

    def test_untouched_destination_poststate_is_checked(self):
        state = dict(self.commit.vector_writes)
        state[26] = 1 << (8 * 100)
        with self.assertRaisesRegex(VectorCommitComparisonError, "full destination poststate"):
            self.prove(commit=replace(self.commit, vector_writes=state))

    def test_partial_unknown_or_missing_concrete_prestate_is_rejected(self):
        for kwargs in ({"unknown": {26: 255 << 32}}, {"prior": {}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(VectorCommitComparisonError):
                self.prove(**kwargs)

    def test_identity_uses_concrete_history_only_without_clearing_unknown(self):
        group = self.groups[0]
        unknown = {20: 255}
        prior = dict(self.prior)
        prior[(20, 0)] = (0x5a, None)
        group = [replace(group[0], data=0x5a)] + group[1:]
        activity = ArchActivity(self.insn, writes=group)
        commit = replace(self.commit, vector_writes={}, vector_vstart=0, csr_writes={8: 0})
        result = _prove_load_fault_bytes(activity, commit, self.pre, unknown, prior,
                                         [group], 0, 4, 1024)
        self.assertEqual(result["preserved_unknown_bytes"], 1)
        self.assertEqual(unknown, {20: 255})
        with self.assertRaises(VectorCommitComparisonError):
            _prove_load_fault_bytes(activity, commit, self.pre, {}, prior, [group], 0, 4, 1024)


ROOT = Path(__file__).resolve().parents[2]
PROBE_ROOT = ROOT / "verification/out/fault-vstart-20260927-01"
ARCHIVE = ROOT / "verification/out/batch-exploration-20260926-03/cases"


@unittest.skipUnless((PROBE_ROOT / "seed1402/console.log").exists(), "archived probe logs unavailable")
class ArchivedLoadFaultTests(unittest.TestCase):
    def paths(self, seed):
        case = PROBE_ROOT / f"seed{seed}"
        spike = next(ARCHIVE.glob(f"*seed{seed}-*/tests/*/spike_commit.log"))
        return spike, case / "commit_trace.csv", case / "vector_trace.csv", case / "console.log"

    def scalar(self, paths, exception_log=None):
        spike, commit, vector, probe = paths
        seed = 1401 if "1401" in str(spike) else 1402
        case = PROBE_ROOT / f"seed{seed}"
        args = json.loads((case / "command.json").read_text())["command"]
        exit_pc = int(next(arg.split("=")[1] for arg in args if arg.startswith("+COMMIT_EXIT_PC=")), 16)
        unknown = unobservable_vector_scalar_write_indices(spike, commit, vector, 0x80000000)
        return compare_commit_prefix(
            spike, commit, 0x80000000, terminal_ecall_pc=exit_pc,
            unobservable_register_value_indices=unknown,
            rtl_exception_log=exception_log or case / "trace_hart_0.log",
            fault_vector_trace=vector, fault_probe_log=probe,
        )

    def test_both_archived_streams_compare_to_completion(self):
        for seed, required, accepted, preserved in ((1401, 0, 256, 16), (1402, 32, 928, 0)):
            with self.subTest(seed=seed):
                paths = self.paths(seed)
                scalar = self.scalar(paths)
                self.assertEqual(scalar["status"], "TERMINAL_MATCH")
                vector = compare_vector_commits(*paths[:3], 0x80000000,
                    aligned_vector_faults=scalar["aligned_vector_faults"], fault_probe_log=paths[3])
                self.assertEqual(vector["status"], "PASS")
                proof = vector["verified_probed_load_faults"][0]
                self.assertEqual(proof["required_load_bytes"], required)
                self.assertEqual(proof["accepted_byte_events"], accepted)
                self.assertEqual(proof["preserved_unknown_bytes"], preserved)

    def test_probe_missing_wrong_or_duplicate_fields_fail(self):
        original = self.paths(1402)[3].read_text()
        changes = [
            ("phase=NEXT", "phase=MISSING"), ("actual_q=2", "actual_q=1"),
            ("actual_q=2", "actual_q=x"), ("csr_vstart_d=2", "csr_vstart_d=0"),
            ("csr_vstart_q=1", "csr_vstart_q=0"), ("exception_vstart=2", "exception_vstart=0"),
            ("cause=4", "cause=5"), ("tval=800050d1", "tval=800050d5"),
            ("arch_seq=126", "arch_seq=127"), ("current_insn=eece8a07", "current_insn=eece8a87"),
            ("req_trans_id=7", "req_trans_id=6"), ("resp_ready=1", "resp_ready=0"),
            ("cycle=2062", "cycle=2063"), ("rst_n=1", "rst_n=0"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "probe"
            paths = self.paths(1402)
            for before, after in changes:
                with self.subTest(field=before):
                    self.assertIn(before, original)
                    probe.write_text(original.replace(before, after))
                    with self.assertRaises(VectorCommitComparisonError):
                        prove_load_faults(*paths[:3], probe, 0x80000000)
            lines = [line for line in original.splitlines() if line.startswith("[ARA_FAULT_VSTART]")]
            for content in (lines[0], "\n".join(lines + [lines[1]]),
                            "\n".join(lines).replace("cause=4", "cause=4 cause=4")):
                probe.write_text(content)
                with self.assertRaises(VectorCommitComparisonError):
                    _fault_probe_pair(probe)

    def test_probe_time_must_match_the_exception_trace(self):
        paths = self.paths(1402)
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "probe"
            probe.write_text(paths[3].read_text().replace("time=20720000", "time=20720001"))
            with self.assertRaisesRegex(CommitComparisonError, "identity/timing"):
                self.scalar((*paths[:3], probe))

    def test_missing_required_byte_in_real_trace_is_rejected(self):
        paths = self.paths(1402)
        with tempfile.TemporaryDirectory() as directory:
            vector = Path(directory) / "vector.csv"
            rows = list(csv.DictReader(io.StringIO(paths[2].read_text())))
            removed = False
            for row in rows:
                if (row["arch_seq"] == "126" and row["event"] == "write" and
                        row["source"] == "4" and int(row["be"], 16)):
                    row["be"] = "00"
                    removed = True
                    break
            self.assertTrue(removed)
            with vector.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(VectorCommitComparisonError, "missing required"):
                prove_load_faults(paths[0], paths[1], vector, paths[3], 0x80000000)

    def test_fault_csr_corruption_or_omission_fails(self):
        paths = self.paths(1402)
        original = list(csv.DictReader(io.StringIO(paths[1].read_text())))
        with tempfile.TemporaryDirectory() as directory:
            commit = Path(directory) / "commit.csv"
            for csr in (0x341, 0x342, 0x343):
                for omit in (False, True):
                    with self.subTest(csr=csr, omit=omit):
                        rows = copy.deepcopy(original)
                        target = next(row for row in rows if row["event"] == "retire" and
                                      int(row["cycle"]) > 2055 and int(row["rd"]) != 0 and
                                      int(row["insn"], 16) >> 20 == csr)
                        if omit:
                            rows.remove(target)
                        else:
                            target["rd_wdata"] = f'{int(target["rd_wdata"], 16) ^ 1:016x}'
                        with commit.open("w", newline="") as stream:
                            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                            writer.writeheader()
                            writer.writerows(rows)
                        result = self.scalar((paths[0], commit, paths[2], paths[3]))
                        self.assertEqual(result["status"], "MISMATCH")

    def test_vector_requires_same_scalar_proof_and_all_csrs(self):
        paths = self.paths(1402)
        scalar = self.scalar(paths)
        for missing in ("0x341", "0x342", "0x343", "load_fault_proof"):
            faults = copy.deepcopy(scalar["aligned_vector_faults"])
            if missing == "load_fault_proof":
                del faults[0][missing]
            else:
                del faults[0]["matched_fault_csrs"][missing]
            with self.subTest(missing=missing), self.assertRaisesRegex(
                    VectorCommitComparisonError, "scalar fault CSR"):
                compare_vector_commits(*paths[:3], 0x80000000,
                    aligned_vector_faults=faults, fault_probe_log=paths[3])

    def test_partial_fault_cannot_use_legacy_zero_or_identity_fallback(self):
        paths = self.paths(1402)
        original = list(csv.DictReader(io.StringIO(paths[2].read_text())))
        faults = [{"index": 403, "pc": "0x00000000800005c2", "instruction": "0xeece8a07"}]
        with tempfile.TemporaryDirectory() as directory:
            vector = Path(directory) / "vector.csv"
            for mode in ("zero_all", "delete_all", "delete_loads"):
                with self.subTest(mode=mode):
                    rows = []
                    for row in copy.deepcopy(original):
                        if row["arch_seq"] == "126" and row["event"] == "write":
                            if mode == "delete_all" or (mode == "delete_loads" and row["source"] == "4"):
                                continue
                            if mode == "zero_all":
                                row["be"] = "00"
                        rows.append(row)
                    with vector.open("w", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                        writer.writeheader()
                        writer.writerows(rows)
                    result = compare_vector_commits(paths[0], paths[1], vector, 0x80000000,
                                                    aligned_vector_faults=faults)
                    self.assertNotEqual(result["status"], "PASS")
                    self.assertNotIn(126, result["verified_zero_write_traps"])
                    with self.assertRaises(VectorCommitComparisonError):
                        prove_load_faults(paths[0], paths[1], vector, paths[3], 0x80000000)

    def test_missing_probe_file_uses_checker_error(self):
        paths = self.paths(1402)
        with self.assertRaises(VectorCommitComparisonError):
            prove_load_faults(*paths[:3], paths[3].with_name("nonexistent-probe"), 0x80000000)


if __name__ == "__main__":
    unittest.main()
