"""Host-side negative tests for source selection and fail-closed evidence checks."""
import tempfile
from pathlib import Path
import unittest

import run


def passing_log():
    shapes = [(t,w,s) for t in (1,9,64) for w in (4,6,8) for s in (0,1)]
    shapes += [(9,w,1) for w in (4,6,8)]
    rows = [f'READER_SHAPE_PASS tokens={t} words={w} stalls={s} coefficients={t} values={t*w} reads={t*w}'
            for t,w,s in shapes]
    rows += [f'READER_CANCEL_PASS words={w} reads=1 delivered=0' for w in (4,6,8)]
    rows += ['READER_PASS cases=40 good=21 invalid=16 cancelled=3 writes=2048 '
             'reads=2829 values=2826 coefficients=474 latency=2829 '
             'coefficient_stalls=1 value_stalls=1 full_credit=1 busy_rejects=1 '
             'held_done=240 final_stalls=1 max_credit=2']
    return '\n'.join(rows)+'\n'


class EvidenceTests(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(run.check_log(passing_log())['measured_read_latency_cycles'], 1)

    def test_negative_receipts(self):
        log = passing_log()
        mutations = [
            log.replace('READER_PASS', 'READER_MISSING'),
            log+log.splitlines()[-1]+'\n',
            '\n'.join(log.splitlines()[1:]),
            log+log.splitlines()[0]+'\n',
            log.replace('coefficients=1 values=4', 'coefficients=0 values=4', 1),
            log.replace('reads=2829', 'reads=2828'),
            log.replace('latency=2829', 'latency=2828'),
            log.replace('full_credit=1', 'full_credit=0'),
            log.replace('held_done=240', 'held_done=239'),
            log.replace('delivered=0', 'delivered=1', 1),
            log.replace('max_credit=2', 'max_credit=3'),
            log.replace('invalid=16', 'invalid=15'),
            log.replace('max_credit=2', 'max_credit=2 max_credit=2'),
            log+'Error: context assertion failed\n',
            log+'Fatal: unexpected read\n',
        ]
        for mutated in mutations:
            with self.subTest(log=mutated[-160:]), self.assertRaises(ValueError):
                run.check_log(mutated)

    def test_closed_formula_is_bijection(self):
        for word in range(8):
            indices = [16*word+lane+offset for lane in range(4) for offset in (0,8,4,12)]
            self.assertEqual(sorted(indices), list(range(16*word,16*(word+1))))
        values = [(i*40503+97)&65535 for i in range(64*128)]
        self.assertEqual(len(set(values)), len(values))
        self.assertTrue(all(v != (v ^ 65535) for v in values))

    def test_source_selection(self):
        frozen = Path('/frozen')
        names = [str(frozen/p) for p in run.SOURCES]
        pins = dict.fromkeys(names, 'digest')
        text = '\n'.join(['+define+NR_LANES=4', '+define+TARGET_VERILATOR']+names+['/live/unrelated.sv'])
        selected, defines = run.select_sources(text, pins, frozen)
        self.assertEqual(selected, names)
        self.assertEqual(defines, ['+define+NR_LANES=4'])
        for bad, bad_pins in ((text.replace(names[0], '/live/tc_sram.sv'), pins),
                              (text+'\n'+names[0], pins), (text, {}),
                              (text+'\n-f /live/extra.f', pins),
                              (text+'\n+define+SYNTHESIS', pins)):
            with self.subTest(text=bad[-100:]), self.assertRaises(ValueError):
                run.select_sources(bad, bad_pins, frozen)

    def test_pin_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'input'
            path.write_bytes(b'original')
            pins = {str(path): run.sha(path)}
            run.verify(pins)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                run.verify(pins)

    def test_live_service_logs_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out/'inputs').mkdir()
            source = out/'inputs/tb.sv'
            source.write_text('frozen')
            (out/'tests.log').write_text('closed result')
            for name in ('worker.log', 'stdout.log', 'service-stdout.txt'):
                (out/name).write_text('still running')
            pins = {str(source): run.sha(source)}
            artifacts = run.collect_artifacts(out, pins)
            self.assertEqual(set(artifacts), {str(source), str(out/'tests.log')})
            for name in ('worker.log', 'stdout.log', 'service-stdout.txt'):
                (out/name).write_text('more output after report generation')
            run.verify(artifacts)
            (out/'tests.log').write_text('changed closed gate log')
            with self.assertRaises(ValueError):
                run.verify(artifacts)


if __name__ == '__main__':
    unittest.main()
