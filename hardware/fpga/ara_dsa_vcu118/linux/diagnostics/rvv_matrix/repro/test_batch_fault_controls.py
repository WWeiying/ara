import unittest
from pathlib import Path
from batch_fault_controls import select


class BatchControlsTests(unittest.TestCase):
    def test_exact_identity_and_explicit_exclusion(self):
        a = dict(name='rvv_fault_replay_e8_mf8', sew=8, lmul='mf8', sha256='a')
        b = dict(name='rvv_fault_replay_e64_m8', sew=64, lmul='m8', sha256='b')
        roots = [(Path('root'), dict(cases=[a, b]))]
        report = dict(inputs=dict(cases=[a, b]), results=[dict(name=c['name'], status='failed') for c in (a,b)])
        self.assertEqual(select(roots, report, [a['name']]), [(Path('root'), b)])
        for excluded in (['unknown'], [a['name'], b['name']]):
            with self.assertRaises(ValueError):select(roots, report, excluded)
        with self.assertRaises(ValueError):select(roots + roots, report, [])
        report['results'][1]['status'] = 'passed'
        with self.assertRaises(ValueError):select(roots, report, [])

    def test_layout_is_explicit_and_identity_checked(self):
        case = dict(name='rvv_fault_replay_segment_nf2_e16_m1', sew=16, lmul='m1', sha256='a')
        root = Path('root')
        manifest = dict(fields=2, indexed=False, cases=[case])
        report = dict(inputs=dict(cases=[case]), results=[dict(name=case['name'], status='failed')])
        self.assertEqual(select([(root, manifest)], report, [], 'segment'), [(root, case)])
        with self.assertRaises(ValueError):select([(root, manifest)], report, [])
        with self.assertRaises(ValueError):select([(root, manifest)], report, [], 'strided')
        case['name'] = 'rvv_fault_replay_segment_nf2_strided_e16_m1'
        report['results'][0]['name'] = case['name']
        manifest['strided'] = True
        self.assertEqual(select([(root, manifest)], report, [], 'strided'), [(root, case)])
        with self.assertRaises(ValueError):select([(root, manifest)], report, [], 'segment')


if __name__ == '__main__':
    unittest.main()
