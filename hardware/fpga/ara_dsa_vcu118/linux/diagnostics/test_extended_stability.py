import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from extended_stability import (PROFILES, STRESSORS, DEFERRED, extended_plan,
                                result_status, validate_extended)


class ExtendedTests(unittest.TestCase):
    def test_inventory_and_bounds(self):
        for profile in PROFILES:
            plan = list(extended_plan('/tmp/test', profile))
            self.assertTrue(plan)
            self.assertEqual(len(plan), len(set(s[0] for s in plan)))
            for _, command, timeout, _ in plan:
                self.assertGreater(timeout, 0)
                self.assertLessEqual(timeout, 14400)
                self.assertNotIn('/dev/mem', command)
                self.assertNotIn('--all', command)
                command.encode('ascii')
        for profile, spec in STRESSORS.items():
            self.assertEqual(len(list(extended_plan('/tmp/t', profile))), len(spec)+2)
        self.assertEqual(len(list(extended_plan('/tmp/t', 'rvv_context'))), 32)
        self.assertEqual(len(list(extended_plan('/tmp/t', 'soak4h'))), 98)
        self.assertEqual(len(list(extended_plan('/tmp/t', 'soak24h'))), 578)
        self.assertIn('dual_ddr', DEFERRED)

    def test_reference_reduced_not_substituted(self):
        for p in PROFILES:
            full = list(extended_plan('/tmp/t', p))
            ref = list(extended_plan('/tmp/t', p, True))
            self.assertLessEqual(len(ref), len(full))
        with self.assertRaises(ValueError):
            list(extended_plan('/tmp/t', 'unbounded'))

    def test_upstream_metrics_and_skips(self):
        good = ('stress-ng: metrc: [12] atomic 100 3.00 1.00 1.00\n'
                'stress-ng: info: [12] skipped: 0\n'
                'stress-ng: info: [12] failed: 0\n'
                'stress-ng: info: [12] successful run completed in 3 secs\n')
        kind = ('stress', ['atomic'])
        self.assertEqual(result_status(0, kind, good, '/tmp/t'), 'passed')
        for output in (good.replace('100 ', '0 '), good.replace('skipped: 0', 'skipped: 1'),
                       good.replace('failed: 0', 'failed: 1'), good.replace('atomic', 'cpu')):
            with self.assertRaises(ValueError):
                result_status(0, kind, output, '/tmp/t')
        self.assertEqual(result_status(4, kind, 'not implemented', '/tmp/t'), 'skipped_unsupported')
        with self.assertRaises(ValueError):
            result_status(3, kind, good, '/tmp/t')
        with self.assertRaises(ValueError):
            result_status(0, ('stress', ['atomic', 'futex']), good, '/tmp/t')

    def test_memory_and_rvv_oracles(self):
        good = 'got  32MB (33554432 bytes)\nLoop 1/2:\nLoop 2/2:\nDone.\n'
        validate_extended(('memtester', 32, 2), good, '/tmp/t')
        for output in (good.replace('32MB', '16MB'), good.replace('Loop 2/2:', ''), good+'FAILURE: mismatch'):
            with self.assertRaises(ValueError):
                validate_extended(('memtester', 32, 2), output, '/tmp/t')
        rvv = 'RVV fallback userspace PASS\nRVV context switch and fault return PASS\n'
        validate_extended(('rvv',), rvv, '/tmp/t')
        with self.assertRaises(ValueError):
            validate_extended(('rvv',), rvv.splitlines()[0], '/tmp/t')
        with self.assertRaises(ValueError):
            validate_extended(None, '[ 2.01] Kernel panic: fault', '/tmp/t')

    def test_runner_records_timeout_and_skip_without_reset(self):
        import linux_stability
        class FakePort:
            def __init__(self, *args, **kwargs):
                self.wire = bytearray()
                self.first = True
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def write(self, data):
                self.wire.extend(data)
            def read(self, size):
                import re
                if self.first:
                    self.first = False
                    return b'/ # '
                if mode == 'timeout':
                    raise TimeoutError('fixture no response')
                token = re.findall(rb'ARA_ST_[a-f0-9]+_\d+', self.wire)[-1]
                return b'not implemented\n'+token+b':4\n'
        for mode in ('timeout', 'skip'):
            with tempfile.TemporaryDirectory() as root:
                out = Path(root)/'run'
                steps = [('atomic', 'fixture', 1, ('stress', ['atomic']))]
                argv = ['runner', '--out', str(out), '--serial-wheel', 'fixture',
                        '--extended-profile', 'atomic_threads']
                with patch.object(sys, 'argv', argv), patch.dict(sys.modules, {'serial': types.SimpleNamespace(Serial=FakePort)}), \
                     patch('extended_stability.extended_plan', return_value=steps), \
                     patch('linux_stability.time.sleep'), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(linux_stability.main(), 1)
                report = json.loads((out/'report.json').read_text())
                self.assertFalse(report['passed'])
                self.assertFalse(report['reset'])
                self.assertEqual(report['counts']['not_run'], 0)
                self.assertEqual(report['counts']['passed'], 0)
                self.assertEqual(report['counts']['failed'], int(mode == 'timeout'))
                self.assertEqual(report['counts']['skipped'], int(mode == 'skip'))


if __name__ == '__main__':
    unittest.main()
