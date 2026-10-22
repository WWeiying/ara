"""Offline oracle, evidence-admission and stimulus-discrimination tests."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cva6 import run_mmu_early_ppn as runner


HEADER = "id prev mode va ppn old_page current_page hit early ni valid pa exception prev_pa prev_valid prev_exception"
PAGE = {-1: 0, 0: 0, 1: 2, 2: 1}


def evidence(rows):
    lines = [HEADER]
    for r in rows:
        addr = runner.oracle(r["mode"], r["va"], r["ppn"])
        fields = [r["id"], r["prev"], r["mode"], r["va"], r["ppn"],
                  PAGE[r["prev"]], PAGE[r["mode"]], 1, addr // 4096,
                  runner.ni(addr), 1, addr, 0,
                  runner.oracle(r["prev"], 0x1552345080, 0x80000), 1, 0]
        lines.append(" ".join(str(v) if i < 3 else f"{v:016x}" for i, v in enumerate(fields)))
    console = (f"MMU_EARLY_PPN_COMPLETE cases={len(rows)} checks={len(rows)*11+2} errors=0\n"
               "$finish called\n")
    return "\n".join(lines) + "\n", console


def historical_ppn(r, stale_only=False):
    """Negative controls only, never used to compute an accepted expectation."""
    if r["mode"] < 0:
        return r["va"] % 2**56 // 4096
    ppn = r["ppn"]
    bits = {0: 0, 1: 9, 2: 18, -1: 0}[r["prev"]]
    if bits:
        if stale_only:
            mask = 2**bits - 1
            ppn = (ppn & ~mask) | ((r["va"] // 4096) & mask)
        else:
            mask = (2**bits - 1) * 4096
            ppn = (ppn & ~mask) | (r["va"] & mask)
    return ppn


class TestOracle(unittest.TestCase):
    def test_uart_superpage_next_page(self):
        for mode in (1, 2):
            self.assertEqual(runner.oracle(mode, 0x1088, 0xC0000), 0xC0001088)
            self.assertEqual(runner.ni(0xC0001088), 0)
            self.assertEqual(runner.ni(0xC0000088), 1)

    def test_ctrl_inside_gigapage(self):
        self.assertEqual(runner.oracle(2, 0x10001088, 0xC0000), 0xD0001088)
        self.assertEqual(runner.ni(0xD0001088), 0)
        self.assertEqual(runner.ni(0xD0000088), 1)

    def test_alignment_is_not_silently_rounded(self):
        for mode, ppn in ((1, 1), (2, 0x200)):
            with self.assertRaisesRegex(ValueError, "unaligned"):
                runner.oracle(mode, 0, ppn)

    def test_high_ppn(self):
        self.assertEqual(runner.oracle(2, 0x3FFFFFFF, 1 << 43),
                         (1 << 55) + 0x3FFFFFFF)

    def test_bypass_truncation(self):
        self.assertEqual(runner.oracle(-1, 0xFFFFFFC000001FFF, 0), 0xFFFFC000001FFF)

    def test_illegal_mode_and_ppn(self):
        for mode, ppn in ((3, 0), (0, -1), (0, 1 << 44)):
            with self.assertRaises(ValueError):
                runner.oracle(mode, 0, ppn)

    def test_plan_all_pairs_and_walking_bits(self):
        rows = runner.cases()
        self.assertEqual({(r['prev'], r['mode']) for r in rows},
                         {(a, b) for a in range(-1, 3) for b in range(-1, 3)})
        for mode in range(3):
            self.assertEqual({r['bit'] for r in rows if r['mode'] == mode and r['family'] == 'vpn_walk'},
                             set(range(27)))
            self.assertEqual({r['bit'] for r in rows if r['mode'] == mode and r['family'] == 'ppn_walk'},
                             set(range(9 * mode, 44)))

    def test_both_old_and_stale_only_formulas_are_detected(self):
        for stale in (False, True):
            mismatches = [r for r in runner.cases() if historical_ppn(r, stale) !=
                          runner.oracle(r['mode'], r['va'], r['ppn']) // 4096]
            self.assertGreater(len(mismatches), 50)
            self.assertTrue(any(r['mode'] == 0 for r in mismatches))
            self.assertTrue(any(r['mode'] == 1 for r in mismatches))
            self.assertTrue(any(r['mode'] == 2 for r in mismatches))

    def test_mutant_changes_only_page_size_source(self):
        line = b"if (dtlb_is_page[CVA6Cfg.PtLevels-1-level]) begin"
        source = b"prefix\n" + line + b"\nsuffix\n"
        self.assertEqual(runner.stale_page_mutant(source),
                         b"prefix\nif (dtlb_is_page_q[CVA6Cfg.PtLevels-1-level]) begin\nsuffix\n")
        for bad in (b"", source * 2, runner.stale_page_mutant(source)):
            with self.assertRaisesRegex(ValueError, 'uniquely'):
                runner.stale_page_mutant(bad)


class TestEvidence(unittest.TestCase):
    def setUp(self):
        self.rows = runner.cases()
        self.trace, self.console = evidence(self.rows)

    def test_complete_pass(self):
        out = runner.audit_trace(self.trace, self.console, self.rows)
        self.assertEqual(out['status'], 'PASS')
        self.assertEqual(out['functional_coverage']['passing_cases'], 278)

    def test_empty_plan(self):
        with self.assertRaises(ValueError):
            runner.audit_trace(HEADER + '\n', self.console, [])

    def test_truncated(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            runner.audit_trace('\n'.join(self.trace.splitlines()[:-1]), self.console, self.rows)

    def test_duplicate_id(self):
        lines = self.trace.splitlines()
        lines[2] = lines[1]
        with self.assertRaisesRegex(ValueError, 'input differs'):
            runner.audit_trace('\n'.join(lines), self.console, self.rows)

    def test_wrong_input(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['va'] += 1
        with self.assertRaisesRegex(ValueError, 'input differs'):
            runner.audit_trace(self.trace, self.console, rows)

    def test_unknown(self):
        lines = self.trace.splitlines()
        fields = lines[1].split()
        fields[8] = 'x'
        lines[1] = ' '.join(fields)
        with self.assertRaisesRegex(ValueError, 'unknown/X'):
            runner.audit_trace('\n'.join(lines), self.console, self.rows)

    def test_incorrect_checks(self):
        with self.assertRaisesRegex(ValueError, 'check count'):
            runner.audit_trace(self.trace, self.console.replace('checks=3060', 'checks=1'), self.rows)

    def test_previous_value_really_checked(self):
        lines = self.trace.splitlines()
        fields = lines[1].split()
        fields[13] = '0'
        lines[1] = ' '.join(fields)
        console = self.console.replace('errors=0', 'errors=1') + 'EARLY_PPN_TEST_FAILED\n'
        out = runner.audit_trace('\n'.join(lines), console, self.rows)
        self.assertEqual(out['failures'][0]['field'], 'prev_pa')
        self.assertEqual(out['status'], 'FAIL')

    def test_original_numeric_failure_not_accepted(self):
        lines = self.trace.splitlines()
        fields = lines[2].split()
        fields[8], fields[9] = 'c0000', '1'
        lines[2] = ' '.join(fields)
        console = self.console.replace('errors=0', 'errors=2') + 'EARLY_PPN_TEST_FAILED\n'
        out = runner.audit_trace('\n'.join(lines), console, self.rows)
        self.assertEqual({f['field'] for f in out['failures']}, {'early', 'ni'})
        self.assertEqual(out['status'], 'FAIL')
        self.assertEqual(out['functional_coverage']['passing_cases'], len(self.rows) - 1)

    def test_unaccounted_sv_error(self):
        with self.assertRaisesRegex(ValueError, 'unaccounted'):
            runner.audit_trace(self.trace, self.console.replace('errors=0', 'errors=1'), self.rows)

    def test_bad_page_encoding(self):
        lines = self.trace.splitlines()
        fields = lines[7].split()
        fields[6] = '3'
        lines[7] = ' '.join(fields)
        with self.assertRaisesRegex(ValueError, 'page-transition'):
            runner.audit_trace('\n'.join(lines), self.console, self.rows)

    def test_finish_and_unexpected_errors(self):
        for console in (self.console.replace('$finish called', ''),
                        self.console + 'UVM_ERROR unexpected\n', self.console + 'Fatal: bad\n',
                        self.console + 'Error: TLB multiple hit\n', self.console + '$stop at time 10\n'):
            with self.assertRaises(ValueError):
                runner.audit_trace(self.trace, console, self.rows)

    def test_duplicate_completion(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            runner.audit_trace(self.trace, self.console * 2, self.rows)


if __name__ == '__main__':
    unittest.main()
