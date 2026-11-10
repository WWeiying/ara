import importlib.util
from pathlib import Path
import unittest


def module(name):
    spec = importlib.util.spec_from_file_location('test_' + name, Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


build, run = module('build_smokes'), module('run_smokes')


class TestSmokeContracts(unittest.TestCase):
    def test_exact_numerical_terminal(self):
        for case, contract in build.CASES.items():
            text = contract['pass_line'] + '\nCore Test *** SUCCESS *** (tohost = 0)\n'
            self.assertTrue(build.check_log(case, text)['successful_eoc'])
            for bad in ('SKIP', 'disabled', 'FAILED', 'Fatal: error', 'UVM_ERROR : 1'):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    build.check_log(case, text + bad + '\n')
            with self.assertRaises(ValueError):
                build.check_log(case, text + text)

    def test_exact_exception_sequence(self):
        case = 'qbs_control_smoke'
        instructions = build.CASES[case]['expected_exception_instructions']
        events = []
        for index, insn in enumerate(instructions):
            events += [(2*index, True, index, insn, False, 0, False),
                       (2*index+1, False, 0, 0, True, index, True)]
        self.assertEqual(run.check_exceptions(case, events, build.CASES)['count'], len(instructions))
        for changed in (events[:-1], events + [events[-1]],
                        [(t, req, ident, insn ^ 1, resp, resp_id, exc)
                         for t, req, ident, insn, resp, resp_id, exc in events]):
            with self.assertRaises(ValueError):
                run.check_exceptions(case, changed, build.CASES)

    def test_handoff_does_not_allow_traps(self):
        self.assertEqual(run.check_exceptions('qbs_akv_handoff_smoke', [], build.CASES)['count'], 0)
        with self.assertRaises(ValueError):
            run.check_exceptions('qbs_akv_handoff_smoke',
                [(0, True, 0, 0x00b5605b, False, 0, False),
                 (1, False, 0, 0, True, 0, True)], build.CASES)


if __name__ == '__main__':
    unittest.main()
