import json
from pathlib import Path
import sys
import tempfile
import unittest

from cva6 import checker, run_contract, stimulus


CONFIG = {"xlen": 64, "ids": 8, "ports": 2, "fpga": 0, "accel": 9,
          "load": 1, "store": 2, "ctrl": 3, "fences": [50, 51, 52, 53, 54]}


def row(cycle, **values):
    result = dict.fromkeys(checker.NUMERIC_FIELDS, 0)
    result.update(cycle=cycle, epoch=1, phase="pre", label="unit", empty=1,
                  in_ready=1, no_ld=1, no_st=1, resp_ready=1, out_ready=1)
    result.update(values)
    return result


def fixture():
    """Hand-written seven-edge LOAD lifecycle; no DUT-derived reference logic."""
    identity = {"head_seq": 1, "head_id": 0, "head_kind": 1,
                "head_insn": 0x02006087, "head_rs2": 0xcafe0001}
    output = {"out_valid": 1, "out_fire": 1, "a_full": 1, "out_seq": 1,
              "out_id": 0, "out_insn": 0x02006087, "out_rs2": 0xcafe0001, "out_frm": 2}
    return [
        row(1, hs=1, accept=1, seq=1, id=0, pc=0x80000004, kind=1,
            view=1, issue_fu=9),
        row(2, ex_valid=1, ex_seq=1, ex_kind=1, empty=0, spec_ld=1,
            no_ld=0, pending_next=1, **identity),
        row(3, usage=1, empty=0, pending=1, c0_acc=1, commit=1,
            in_valid=1, pop=1, ld_pop=1, spec_ld=1, no_ld=0, **identity),
        row(4, disp_ld=1, no_ld=0, **output),
        row(5, disp_ld=1, no_ld=0, resp_valid=1, resp_seq=1,
            result_valid=1, result_seq=1),
        row(6, disp_ld=1, no_ld=0, ld_done=1),
        row(7),
    ]


def encode(rows):
    return "".join(json.dumps(r) + "\n" for r in rows)


def canceled_fixture():
    rows = fixture()[:3]
    rows[2].update(c0_acc=0, commit=0, in_valid=0, pop=0, ld_pop=0, flush=1)
    return rows + [row(4)]


def retoken(rows, seq):
    for r in rows:
        for key in ("seq", "ex_seq", "head_seq", "out_seq", "resp_seq", "result_seq"):
            if r[key]:
                r[key] = seq
        for key in ("head_insn", "out_insn"):
            if r[key]:
                r[key] = checker.insn(seq, 1)
        for key in ("head_rs2", "out_rs2"):
            if r[key]:
                r[key] = 0xcafe0000 + seq
        if r["pc"]:
            r["pc"] = 0x80000000 + 4 * seq
    return rows


class CVA6ContractTests(unittest.TestCase):
    def replay(self, rows):
        return checker.check_trace(checker.parse_trace(encode(rows)), CONFIG, require_coverage=False)

    def test_minimal_independent_lifecycle(self):
        report = self.replay(fixture())
        self.assertEqual(report["events"], {"accept": 1, "enqueue": 1, "pop": 1,
                                           "deliver": 1, "response": 1, "ld_done": 1})
        self.assertEqual(report["coverage"]["response_without_memory_done"], 1)

    def test_missing_coverage_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "missing coverage"):
            checker.check_evidence("CVA6_CONTRACT_COMPLETE cycles=7\n", encode(fixture()), CONFIG)

    def test_log_is_not_pass_oracle(self):
        valid = "CVA6_CONTRACT_COMPLETE cycles=7\n"
        checker.check_log(valid, 7)
        for log in ("", valid * 2, "CVA6_CONTRACT_COMPLETE cycles=6\n", valid + "Error: assertion\n",
                    valid + "Fatal: fail\n", valid + "CONTRACT_FAIL\n",
                    valid + "Assertion failed\n", valid + "Error-[SVA] failure\n"):
            with self.subTest(log=log), self.assertRaises(ValueError):
                checker.check_log(log, 7)
        with self.assertRaises(ValueError):
            checker.check_log(valid, 7, returncode=1)

    def test_malformed_unknown_duplicate_and_truncated_trace(self):
        valid = encode(fixture())
        invalid = ["", valid.rstrip(), valid + "{}\n", valid.replace('"cycle": 1', '"cycle": "x"', 1),
                   valid.replace('"cycle": 1', '"cycle": 1, "cycle": 1', 1),
                   valid.replace('"phase": "pre"', '"phase": "post"', 1),
                   valid.replace('"epoch": 1', '"epoch": 2', 1),
                   valid.replace('"cycle": 2', '"cycle": 1', 1),
                   valid.replace('"accept": 1', '"accept": 2', 1)]
        for text in invalid:
            with self.subTest(text=text[:60]), self.assertRaises(ValueError):
                checker.parse_trace(text)

    def test_observed_signal_mutations_fail_closed(self):
        mutations = [(1, "ex_valid", 0), (1, "ex_seq", 2), (1, "pending_next", 0),
                     (2, "commit_id", 1), (2, "pop", 0), (2, "ld_pop", 0),
                     (2, "head_kind", 2), (2, "head_insn", 0), (2, "authorized_next", 1),
                     (3, "out_seq", 2), (3, "out_rs2", 0), (3, "out_fire", 0),
                     (3, "disp_ld", 0), (4, "disp_ld", 0), (4, "result_seq", 2),
                     (5, "ld_done", 0), (6, "pending", 1)]
        for index, key, value in mutations:
            rows = fixture()
            rows[index][key] = value
            with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                self.replay(rows)

    def test_valid_is_not_handshake_and_payload_must_hold(self):
        rows = fixture()
        held = {**rows[3], "out_ready": 0, "out_fire": 0}
        rows.insert(3, held)
        for i, r in enumerate(rows, 1):
            r["cycle"] = i
        self.assertEqual(self.replay(rows)["coverage"]["held_output_cycles"], 1)
        rows[4]["out_seq"] = 2
        with self.assertRaises(ValueError):
            self.replay(rows)

    def test_orphan_completion_and_duplicate_response(self):
        rows = fixture()
        rows[-1]["ld_done"] = 1
        with self.assertRaisesRegex(ValueError, "underflow"):
            self.replay(rows)
        rows = fixture()
        rows[-1].update(resp_valid=1, resp_seq=1, result_valid=1, result_seq=1)
        with self.assertRaisesRegex(ValueError, "orphan/duplicate"):
            self.replay(rows)

    def test_wrong_commit_id_releases_nothing(self):
        rows = fixture()
        rows[2].update(c0_id=1, commit_id=1)
        with self.assertRaisesRegex(ValueError, "in_valid"):
            self.replay(rows)

    def test_port1_requires_older_ack(self):
        rows = fixture()
        rows[2].update(c0_acc=0, c0_valid=1, c0_id=7, c1_acc=1, c1_id=0, ack0=1)
        self.replay(rows)
        rows[2]["ack0"] = 0
        with self.assertRaisesRegex(ValueError, "commit"):
            self.replay(rows)

    def test_fence_stall_independent_of_consistency(self):
        rows = fixture()
        rows[4].update(view=4, issue_fu=3, issue_op=50, cons=0, stall=1)
        self.replay(rows)
        rows[4]["stall"] = 0
        with self.assertRaisesRegex(ValueError, "stall"):
            self.replay(rows)

    def test_incomplete_drain_fails(self):
        with self.assertRaisesRegex(ValueError, "outstanding"):
            self.replay(fixture()[:4])

    def test_flush_cancels_speculative_queue_and_clears_maps(self):
        rows = canceled_fixture()
        report = self.replay(rows)
        self.assertEqual(report["events"]["cancel"], 1)
        self.assertNotIn("deliver", report["events"])
        for key in ("pending_next", "authorized_next"):
            broken = canceled_fixture()
            broken[2][key] = 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.replay(broken)
        rows[3]["spec_ld"] = 1
        with self.assertRaises(ValueError):
            self.replay(rows)

    def test_flush_preserves_spilled_payload_and_dispatched_count(self):
        rows = fixture()
        rows.insert(3, {**rows[3], "flush": 1, "out_ready": 0, "out_fire": 0})
        for i, r in enumerate(rows, 1):
            r["cycle"] = i
        self.assertEqual(self.replay(rows)["coverage"]["flush_spill_preserved"], 1)
        rows[4]["disp_ld"] = 0
        with self.assertRaisesRegex(ValueError, "disp_ld"):
            self.replay(rows)

    def test_canceled_and_responded_id_reuse_need_fresh_authorization(self):
        for previous, name in ((canceled_fixture(), "canceled"), (fixture(), "responded")):
            next_rows = retoken(fixture(), 2)
            next_rows.insert(2, {**next_rows[2], "c0_acc": 0, "commit": 0,
                                "in_valid": 0, "pop": 0, "ld_pop": 0, "pending_next": 1})
            rows = previous + next_rows
            for i, r in enumerate(rows, 1):
                r["cycle"] = i
            with self.subTest(previous=name):
                self.assertGreater(self.replay(rows)["coverage"][f"reuse_{name}_wait"], 0)
                rows[len(previous) + 2]["authorized"] = 1
                with self.assertRaisesRegex(ValueError, "authorized"):
                    self.replay(rows)

    def test_stimulus_is_bounded_and_deterministic(self):
        rows = stimulus.schedule()
        self.assertLess(len(rows), stimulus.MAX_CYCLES)
        self.assertEqual(rows, stimulus.schedule())
        self.assertEqual(len(stimulus.render(rows).splitlines()), len(rows))
        self.assertEqual([r["seq"] for r in rows if r["seq"]], list(range(1, 12)))
        self.assertEqual(sum(r["flush"] for r in rows), 1)

    def test_expected_stimulus_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            checker.check_trace(fixture(), CONFIG, expected_stimulus=[])

    def test_type_extraction_is_exact_and_fails_on_changed_shape(self):
        source = "\n".join(f"localparam type {name} = struct packed {{ logic x; }},"
                           for name in run_contract.TYPE_NAMES)
        output = run_contract.extract_types(source)
        for name in run_contract.TYPE_NAMES:
            self.assertIn(f"typedef struct packed {{ logic x; }} {name};", output)
        for changed in (source + source, source.replace("struct packed", "struct", 1),
                        source.replace("logic x;", "struct packed {logic y;} x;", 1)):
            with self.assertRaises(ValueError):
                run_contract.extract_types(changed)

    def test_runner_rejects_outside_existing_and_linked_output(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            with self.assertRaises(ValueError):
                run_contract.validate_output(directory / "run")
            target = directory / "target"
            target.mkdir()
            (directory / "link").symlink_to(target)
            with self.assertRaises(ValueError):
                run_contract.validate_output(directory / "link" / "run")
        with self.assertRaises(ValueError):
            run_contract.validate_output(run_contract.ROOT / "verification/out")

    def test_execute_records_nonzero_and_timeout(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            failed = run_contract.execute([sys.executable, "-c", "raise SystemExit(7)"],
                                          directory / "failed", 5)
            self.assertEqual(failed["returncode"], 7)
            timed = run_contract.execute([sys.executable, "-c", "import time; time.sleep(30)"],
                                         directory / "timeout", 0.05)
            self.assertTrue(timed["timeout"])
            self.assertEqual(timed["returncode"], -1)


if __name__ == "__main__":
    unittest.main()
