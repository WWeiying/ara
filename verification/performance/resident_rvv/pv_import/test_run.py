"""Fail-closed receipt/source selection tests; no EDA invocation."""
from collections import Counter
from pathlib import Path
import tempfile
import unittest

import run


def fixture_log():
    lines = []
    for (w, h, t, m, phase), count in run.expected_cases().items():
        seeds = 1 if phase == 1 else w*h*4
        coeff = 0 if phase == 1 else 3 if phase == 2 else t
        lines.extend([f'IMPORT_CASE_PASS words={w} heads={h} tokens={t} mode={m} '
                      f'cancel={phase} seeds={seeds} coefficients={coeff} '
                      'sourcewords=96 cmdpops=4 sentinels=4']*count)
    for (w, h, t), count in run.expected_invalid().items():
        lines.extend([f'IMPORT_INVALID_PASS words={w} heads={h} tokens={t}']*count)
    lines.append('IMPORT_PASS cases=170 good=108 invalid=44 cancelled=18 sourcewords=12096 '
                 'cmdpops=504 sentinels=504 latency=12600 held_done=1020 seed_stalls=1 '
                 'coefficient_stalls=1 full_credit=1 unequal=1')
    return '\n'.join(lines)+'\n'


class Receipts(unittest.TestCase):
    def test_complete(self):
        checked = run.check_log(fixture_log())
        self.assertEqual(len(checked['cases']), 126)
        self.assertEqual(len(checked['invalid']), 44)
        self.assertEqual(checked['totals']['good'], 108)

    def test_matrix_independently(self):
        rows = run.expected_cases()
        self.assertEqual(sum(rows.values()), 126)
        self.assertEqual(Counter({p: sum(n for k, n in rows.items() if k[4] == p)
                                  for p in range(4)}), {0: 108, 1: 6, 2: 6, 3: 6})
        for w in (4, 6, 8):
            for h in (1, 2):
                for t in (1, 8, 9, 63, 64):
                    for m in range(3):
                        self.assertEqual(rows[w, h, t, m, 0], 4 if (t, m) == (9, 1) else 1)

    def test_missing_duplicate_unknown(self):
        log = fixture_log()
        first = log.splitlines()[0]+'\n'
        for bad in (log.replace(first, '', 1), log+first, log+'IMPORT_OTHER x=1\n',
                    log+log.splitlines()[-1]+'\n', log.rsplit('IMPORT_PASS', 1)[0]):
            with self.subTest(bad=bad[-120:]), self.assertRaises(ValueError):
                run.check_log(bad)

    def test_count_and_protocol_mutations(self):
        changes = [('sourcewords=96', 'sourcewords=95'), ('cmdpops=4', 'cmdpops=5'),
                   ('sentinels=4', 'sentinels=3'), ('seeds=16', 'seeds=15'),
                   ('coefficients=1', 'coefficients=2'), ('latency=12600', 'latency=12599'),
                   ('seed_stalls=1', 'seed_stalls=0'), ('coefficient_stalls=1', 'coefficient_stalls=0'),
                   ('full_credit=1', 'full_credit=0'), ('unequal=1', 'unequal=0'),
                   ('held_done=1020', 'held_done=1019'), ('invalid=44', 'invalid=43'),
                   ('cancel=1 seeds=1', 'cancel=1 seeds=0'),
                   ('cancel=2 seeds=16 coefficients=3', 'cancel=2 seeds=16 coefficients=4'),
                   ('cancel=3 seeds=16 coefficients=1', 'cancel=3 seeds=15 coefficients=1')]
        for old, new in changes:
            with self.subTest(old=old):
                self.assertIn(old, fixture_log())
                with self.assertRaises(ValueError):
                    run.check_log(fixture_log().replace(old, new, 1))

    def test_diagnostics_and_malformed(self):
        for diagnostic in ('Error: broken', 'Fatal: broken', 'Warning-[ABC] broken',
                           '$fatal broken', 'Assertion failed', 'x ASSERT FAILED y'):
            with self.subTest(diagnostic=diagnostic), self.assertRaises(ValueError):
                run.check_log(fixture_log()+diagnostic+'\n')
        for text in ('x=1 x=2', 'x=-1', 'x=1 garbage', 'x=01', ' x=1', 'x=1  y=2'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                run.fields(text)


class Provenance(unittest.TestCase):
    def setUp(self):
        self.sources = [str(run.FROZEN/p) for p in run.SOURCES]
        self.pins = dict.fromkeys(self.sources+[str(run.FROZEN/p) for p in (run.HEADER, *run.CONTRACTS)], 'hash')
        self.filelist = '\n'.join(['+define+TARGET_VERILATOR', '+define+NR_LANES=4',
            '+define+COMMON_CELLS_ASSERTS_OFF',
            '+incdir+'+str(run.FROZEN/'hardware/deps/common_cells/include'), *self.sources])

    def test_select_preserves_order_and_pins(self):
        selected, defines = run.select_sources(self.filelist, self.pins)
        self.assertEqual(selected, self.sources)
        self.assertNotIn('+define+TARGET_VERILATOR', defines)
        self.assertIn('+define+COMMON_CELLS_ASSERTS_OFF', defines)

    def test_missing_unpinned_duplicate(self):
        for path in self.pins:
            pins = dict(self.pins)
            del pins[path]
            with self.subTest(path=path), self.assertRaises(ValueError):
                run.select_sources(self.filelist, pins)
        for bad in (self.filelist.replace(self.sources[0], ''), self.filelist+'\n'+self.sources[0],
                    self.filelist.replace('+incdir+', '+unrecognized+'),
                    self.filelist+'\nrelative.sv'):
            with self.assertRaises(ValueError):
                run.select_sources(bad, self.pins)

    def test_assertion_and_header_flags(self):
        for flag in ('SYNTHESIS', 'UVM', 'ASSERTS_OFF', 'XSIM', 'TARGET_SRAM_MC', 'X+SYNTHESIS=1'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                run.select_sources(self.filelist+'\n+define+'+flag, self.pins)

    def test_live_service_log_excluded_and_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'inputs').mkdir()
            source = out/'inputs/tb.sv'
            source.write_text('snapshot')
            (out/'service.log').write_text('still changing')
            (out/'run.log').write_text('closed')
            pins = {str(source): run.sha(source)}
            run.verify(pins)
            artifacts = run.collect_artifacts(out, pins)
            self.assertEqual(set(artifacts), {str(source), str(out/'run.log')})
            source.write_text('drift')
            with self.assertRaisesRegex(ValueError, 'identity drift'):
                run.verify(pins)

    def test_contract_and_header_closure(self):
        tb = (run.HERE/'tb.sv').read_text()
        run.check_command_contract(tb, tb)
        with self.assertRaisesRegex(ValueError, 'command differs'):
            run.check_command_contract(tb, tb.replace('logic [1:0] ntr_red;', 'logic ntr_red;'))
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'operand_queue.sv'
            source.write_text('`include "common_cells/assertions.svh"')
            run.check_headers(source)
            source.write_text('`include "untracked.svh"')
            with self.assertRaises(ValueError):
                run.check_headers(source)


if __name__ == '__main__':
    unittest.main()
