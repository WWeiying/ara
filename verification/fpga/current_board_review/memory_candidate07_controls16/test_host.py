import json
from pathlib import Path
import tempfile
import unittest
import regression as r


class Gates(unittest.TestCase):
    def test_scope(self):
        cases, controls, _ = r.original_scope()
        self.assertEqual(len(cases), 16)
        self.assertEqual({c['timeout_s'] for c in cases}, {180})
        self.assertEqual(r.STAGES, (('controls16', 1),))
        self.assertTrue(all('repair06_regression48_prepared01' in c['baseline_csv'] for c in controls))

    def test_wrong_image(self):
        with self.assertRaisesRegex(ValueError, 'Exact M7'):
            r.image_context(Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image'))

    def test_actual_m7(self):
        ledger, _, _ = r.image_context(r.M7)
        self.assertEqual(ledger['configuration_sha256'], r.CONFIGURATION_SHA)

    def test_comparison(self):
        with tempfile.TemporaryDirectory(dir=r.HERE) as directory:
            p = Path(directory)
            (p/'old').write_text('cycle,event,order,pc\n1,retire,0,8000\n2,retire,1,8004\n')
            (p/'new').write_text((p/'old').read_text())
            self.assertEqual(r.compare_cycles(p/'old', p/'new', p/'same')['cycle_changed_rows'], 0)
            (p/'new').write_text('cycle,event,order,pc\n2,retire,0,8000\n3,retire,1,8004\n')
            self.assertEqual(r.compare_cycles(p/'old', p/'new', p/'cycles')['cycle_changed_rows'], 2)
            (p/'new').write_text('cycle,event,order,pc\n1,retire,0,8000\n2,retire,1,9999\n')
            with self.assertRaises(ValueError): r.compare_cycles(p/'old', p/'new', p/'bad')
            (p/'new').write_text('cycle,event,order,pc\n1,retire,0,8000\n')
            with self.assertRaises(ValueError): r.compare_cycles(p/'old', p/'new', p/'missing')

    def test_console(self):
        case = r.original_scope()[0][0]
        text = '\n'.join(case['pass_markers'] + case.get('oracle_lines', []) + [r.SUCCESS, '$finish'])
        r.check_console(case, text)
        for bad in (text.replace('$finish', ''), text+'\nBOARD_REPLAY_MISMATCH', text+'\nSKIP'):
            with self.assertRaises(ValueError): r.check_console(case, bad)

    def test_resource(self):
        with self.assertRaises(ValueError):
            r.resource_math([dict(argv=['simv'])]*24, 64*1024**3, r.HERE, 1, 0)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Gates))
    with (r.HERE/'host02.json').open('x') as f:
        json.dump(dict(passed=result.wasSuccessful(), tests=result.testsRun,
                       script_sha256=r.sha(r.HERE/'regression.py'), dut_runs=0), f, indent=2)
    raise SystemExit(not result.wasSuccessful())
