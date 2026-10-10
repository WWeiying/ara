import copy
import json
import tempfile
from pathlib import Path
import unittest

import report_dispatcher_four_union762 as report


class FourUnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = json.loads((report.life.OUT / 'native-population-union-full761-agent-20261007-03/config.json').read_bytes())
        cls.capture = json.loads((report.CAPTURE / 'config.json').read_bytes())

    def test_exact_four_added_all_other_rows_unchanged(self):
        plan, indices = report.merge_plan(self.previous['plan'], self.capture['plan'])
        changes = [(i, b['raw_index']) for i, (a, g) in enumerate(zip(self.previous['plan']['groups'], plan['groups']))
                   for before, b in zip(a['rows'], g['rows']) if before != b]
        self.assertEqual(changes, [(3, 31), (3, 32), (3, 34), (3, 37)])
        self.assertEqual(indices, [3])
        self.assertEqual(plan['targets'], 128)
        self.assertEqual(plan['protected'], 335)

    def test_duplicate_target_rejected(self):
        plan = copy.deepcopy(self.previous['plan'])
        next(r for r in plan['groups'][3]['rows'] if r['raw_index'] == 31)['target'] = True
        with self.assertRaises(ValueError):
            report.merge_plan(plan, self.capture['plan'])

    def test_native_signature_drift_rejected(self):
        c = copy.deepcopy(self.capture)
        c['plan']['groups'][1]['rows'][0]['attributes']['fromid'] = 'foreign'
        with self.assertRaises(ValueError):
            report.merge_plan(self.previous['plan'], c['plan'])

    def test_private_current_entry_retains_protected_verifier(self):
        ns = report.namespace()
        self.assertEqual(ns['__file__'], report.__file__)
        self.assertIs(ns['verify'].__globals__, ns)
        self.assertIs(ns['records'], report.previous.predecessor.records)

    def test_immutable_stdout_snapshot_and_exact_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); service = out / 'service.log'
            service.write_bytes(b'EXACT742_LIVE pid=10 launch=9\n')
            data = dict(status='QUALIFIED', system={'raw': {'Toggle': '50%'}},
                        output_pins={str(service): report.life.digest(service)})
            report.snapshot_stdout(data, out)
            self.assertNotIn(str(service), data['output_pins'])
            saved = out / 'qualification.json'
            saved.write_text(json.dumps(data))
            tail = (json.dumps(dict(status=data['status'], seal=report.life.digest(saved),
                                   system=data['system'])) + '\n').encode()
            service.write_bytes(service.read_bytes() + tail)
            replay = dict(status='QUALIFIED', system=data['system'], output_pins={
                str(service): report.life.digest(service),
                str(out / 'service-before-qualification.log'): report.life.digest(out / 'service-before-qualification.log')})
            report.snapshot_stdout(replay, out)
            self.assertEqual(data, replay)
            service.write_bytes(service.read_bytes() + b'arbitrary extra\n')
            replay['output_pins'][str(service)] = report.life.digest(service)
            with self.assertRaisesRegex(ValueError, 'Not exact post-qualification'):
                report.snapshot_stdout(replay, out)


if __name__ == '__main__':
    unittest.main()
