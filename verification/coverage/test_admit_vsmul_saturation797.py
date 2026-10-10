import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import admit_vsmul_saturation797 as a


class Admission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = a.life.read_bound(a.QUAL / 'qualification.json', a.Q_SHA)
        cls.base, cls.before, cls.bt, cls.ledger = a.r.baseline()
        def doc(name):
            path = a.QUAL / name
            return a.life.read_bound(path, cls.q['input_pins'][str(path)])
        cls.single = doc('single-bits.json')
        cls.st = doc('single-toggle-bits.json')
        cls.at = doc('proposed-combined-toggle-bits.json')

    def test_actual_complete_offline_replay_no_EDA(self):
        with patch.object(a.r, 'invoke_run', side_effect=AssertionError('No EDA')):
            products, text = a.evaluate()
        self.assertEqual(text.splitlines(), self.ledger + [str(a.RUN / 'code.vdb')])
        status = products['status.json']
        self.assertEqual(status['aggregate_passed'], 797)
        self.assertTrue(status['coverage_admitted'])
        self.assertEqual(status['raw_gain']['primary_new_slots'], 114)
        self.assertEqual(status['raw_gain']['full_toggle_new_slots'], 122)
        self.assertEqual(status['raw_gain']['metrics'], dict(line=14, cond=61, branch=0, fsm=0))

    def test_actual_qualification(self):
        a.qualification(self.q)

    def test_qualification_identity_flags_and_skips(self):
        for key, value in (('run', '/foreign'), ('prepared_seal', '0'*64), ('status', 'PASS'),
                           ('coverage_admitted', True), ('EDA_launched', True), ('RTL_modified', True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                a.qualification(dict(self.q, **{key:value}))
        for value in (True, 1):
            bad = copy.deepcopy(self.q)
            bad['scalar']['skipped_unobservable_register_values'] = value
            with self.assertRaises(ValueError):
                a.qualification(bad)

    def test_native_no_skip_stop_or_incomplete(self):
        for key, value in (('skipped_unknown_bytes', 1), ('stopped_at_spike_index', 0),
                           ('incomplete_requests', [1]), ('non_bit_exact_instructions', 1)):
            bad = copy.deepcopy(self.q)
            bad['native']['architectural_vector_diff'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                a.qualification(bad)

    def test_typed_complete_comparison(self):
        for bad in ({'n':True}, {'n':1.0}, {'n':1, 'extra':0}, {}):
            with self.assertRaises(ValueError):
                a.exact({'n':1}, bad, 'typed')

    def test_complete6162_ordered796_prefix(self):
        after = a.full_union(self.before, self.single)
        self.assertEqual(after['tests'][:-1], self.before['tests'])
        self.assertEqual(sum(map(len, after['metrics'].values())), 6162)
        bad = copy.deepcopy(after)
        bad['tests'][0], bad['tests'][1] = bad['tests'][1], bad['tests'][0]
        with self.assertRaises(ValueError):
            a.c.exact_raw_union(self.before, self.single, bad)

    def test_metric_universe_shape_overflow_candidate(self):
        for mode in ('missing', 'shape', 'overflow', 'foreign', 'duplicate'):
            bad = copy.deepcopy(self.single)
            scope = next(iter(bad['metrics']['line']))
            if mode == 'missing':
                del bad['metrics']['line'][scope]
            elif mode == 'shape':
                bad['metrics']['line'][scope]['checksum'] = 'foreign'
            elif mode == 'overflow':
                bad['metrics']['line'][scope]['bits'] = hex(1 << bad['metrics']['line'][scope]['width'])
            else:
                bad['tests'] = ['/foreign.vdb' if mode == 'foreign' else self.before['tests'][0]]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                a.full_union(self.before, bad)

    def test_metric_OR_lost_or_extra_hit(self):
        after = a.full_union(self.before, self.single)
        scope = next(k for k, v in after['metrics']['line'].items() if int(v['bits'], 16))
        after['metrics']['line'][scope]['bits'] = '0x0'
        with self.assertRaises(ValueError):
            a.c.exact_raw_union(self.before, self.single, after)

    def test_complete2989_toggle_OR_and_corruption(self):
        a.toggle_or(self.bt, self.st, self.at)
        for mode in ('missing', 'shape', 'lost', 'negative', 'overflow'):
            bad = copy.deepcopy(self.at)
            scope = next(k for k, v in bad.items() if int(v['bits'], 16))
            if mode == 'missing':
                del bad[scope]
            elif mode == 'shape':
                bad[scope]['checksum'] = 'foreign'
            else:
                bad[scope]['bits'] = {'lost':'0x0', 'negative':'-0x1',
                    'overflow':hex(1 << bad[scope]['width'])}[mode]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                a.toggle_or(self.bt, self.st, bad)

    def test_membership_missing_extra_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'data'
            path.touch()
            pins = {str(path):a.life.digest(path)}
            a.membership(root, pins)
            with self.assertRaises(ValueError):
                a.membership(root, {})
            (root / 'extra').touch()
            with self.assertRaises(ValueError):
                a.membership(root, pins)
            (root / 'extra').unlink()
            (root / 'link').symlink_to(path)
            with self.assertRaises(ValueError):
                a.membership(root, pins)

    def test_pin_missing_or_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'missing'
            with self.assertRaises((ValueError, FileNotFoundError)):
                a.life.check({str(path):'0'*64})
            path.touch()
            with self.assertRaises(ValueError):
                a.life.check({str(path):'0'*64})

    def test_admit_requires_parent_authorization(self):
        import sys
        process = subprocess.run([sys.executable, '-B', a.__file__, 'admit', '--output', '/tmp/no-admit797', '--seal', '0'*64],
                                 capture_output=True, text=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('Separate explicit parent publication authority', process.stderr)
        self.assertFalse(Path('/tmp/no-admit797').exists())


if __name__ == '__main__':
    unittest.main()
