#!/usr/bin/env python3
"""Host-only successor checks, including replay of immutable completed smoke."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('attention_serialization_test', HERE/'run_v2.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
SMOKE = v.r.b.OUT/'stage3_attention_vcs_smoke_20261110_01'
SOC = v.r.b.OUT/'stage3_soc_20261110_02'


class SuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = v.strict_json((SMOKE/'result.json').read_text())
        selection = v.strict_json((SMOKE/'selection.json').read_text())
        software = v.strict_json((Path(selection['build'])/'build.json').read_text())
        cls.evidence = v.r.numerical_and_work(SMOKE, software)

    def test_actual_difference_is_only_six_lane_keysets(self):
        self.assertEqual(self.report['numerical'], self.evidence['numerical'])
        self.assertEqual(self.report['akv_work'], self.evidence['akv_work'])
        resident = copy.deepcopy(self.evidence['resident_work'])
        self.assertNotEqual(self.report['resident_work'], resident)
        self.assertEqual(len(resident['performance']), 6)
        for record in resident['performance']:
            self.assertEqual(set(record['lanes']), {0, 1, 2, 3})
            record['lanes'] = {str(k): val for k, val in record['lanes'].items()}
        self.assertEqual(self.report['resident_work'], resident)
        self.assertEqual(v.compare_evidence(self.report, self.evidence),
                         {k: self.report[k] for k in self.evidence})

    def test_actual_evidence_mutations_rejected(self):
        for mode in ('extra', 'missing', 'wrong_count', 'wrong_flag', 'wrong_type',
                     'wrong_lane', 'extra_lane', 'missing_lane', 'extra_command',
                     'missing_command', 'wrong_numerical', 'wrong_payload'):
            with self.subTest(mode=mode):
                report = copy.deepcopy(self.report)
                work = report['resident_work']
                record = work['performance'][0]
                if mode == 'extra': record['terminal']['extra'] = 0
                elif mode == 'missing': del record['terminal']['source_words']
                elif mode == 'wrong_count': record['lanes']['0']['issued'] += 1
                elif mode == 'wrong_flag': record['lanes']['0']['flags'] ^= 1
                elif mode == 'wrong_type': record['lanes']['0']['lane'] = False
                elif mode == 'wrong_lane': record['lanes']['0']['lane'] = 1
                elif mode == 'extra_lane': record['lanes']['4'] = record['lanes']['0']
                elif mode == 'missing_lane': del record['lanes']['3']
                elif mode == 'extra_command': work['performance'].append(record)
                elif mode == 'missing_command': work['performance'].pop()
                elif mode == 'wrong_numerical': report['numerical']['fcsr'] ^= 1
                elif mode == 'wrong_payload': report['akv_work']['summary']['q_external_bytes'] = 0
                with self.assertRaises(ValueError):
                    v.compare_evidence(report, self.evidence)

    def test_bad_json_and_key_collisions_rejected(self):
        for text in ('{', '{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}',
                     '{"x":-Infinity}', '{"x":1e999}', '{"x":0} trailing'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                v.strict_json(text)
        for value in ({0: 1, '0': 2}, {'x': float('nan')}, {'x': float('inf')}):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                v.canonical(value)

    def test_full_smoke_admission_retains_immutable_identity(self):
        before = {str(p): v.r.b.sha(p) for p in (SMOKE/'result.json', SMOKE/'source-pins.json')}
        pins = v.admitted_smoke(SMOKE, SOC)
        self.assertTrue(all(pins[p] == digest == v.r.b.sha(p) for p, digest in before.items()))
        self.assertEqual(before[str(SMOKE/'result.json')],
                         '1b5b42543463fae9bc04a1c1b730fc8e0a5e72600a41bcfa4c88cf4fb310f88c')
        self.assertTrue(set(self.report['artifacts']).issubset(pins))
        self.assertEqual(Path(v.r.__file__).resolve(), HERE/'run.py')
        self.assertEqual(v.r.OWN, ('run.py', 'test_run.py', 'check_work.py',
                                   'test_check_work.py', *v.SUCCESSOR))

    def test_wrong_reader_and_same_image_requirement_retained(self):
        with patch.object(v.r.b, 'sha', side_effect=['wrong', 'expected']):
            with self.assertRaisesRegex(ValueError, 'Different sealed smoke reader'):
                v.admitted_smoke(SMOKE, SOC)
        # The wrong image must fail in the inherited admission, not be masked
        # by normalization. No simulation or changes to the accepted receipt.
        with self.assertRaisesRegex(ValueError, 'Accepted same-image smoke required'):
            v.admitted_smoke(SMOKE, SOC.parent/'stage3_soc_wrong_image')

    def test_successor_service_entry_and_original_worker_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'source-pins.json').write_text('{}')
            review = v.r.b.sha(out/'source-pins.json')
            with patch.object(v.r, 'verify_prepared', return_value=({'python': '/usr/bin/python3'},)):
                command = v.service_command(out, review)
                self.assertIn(str(out/'inputs/run_v2.py'), command)
                self.assertNotIn(str(out/'inputs/run.py'), command)
                self.assertIn('--property=KillMode=control-group', command)
                self.assertIs(v.sealed_run.__globals__, v.r.__dict__)
                self.assertEqual(Path(v.sealed_run.__globals__['__file__']).resolve(), HERE/'run.py')
                (out/'attempt.json').write_text('{}')
                with self.assertRaises(ValueError): v.service_command(out, review)
            with self.assertRaisesRegex(ValueError, 'Execute frozen successor entrypoint'):
                v.run(out, review)


if __name__ == '__main__':
    unittest.main()
