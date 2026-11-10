import importlib.util
from pathlib import Path
import unittest


def load(name):
    spec = importlib.util.spec_from_file_location('test_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run, check = load('run_projection'), load('check_projection')


def fixture(enabled, modes=(4, 8, 8, 4)):
    lines = []
    count = len(modes)*2 if enabled else 0
    for lane in range(4):
        total = 0
        for seq in range(1, count+1):
            beats = 4096 if modes[(seq-1)//2] == 8 else 0
            total += beats
            lines.append(f'STAGE2_SOC_LOAN lane={lane} seq={seq} accepted={beats} '
                         f'core_issued={beats} core_completed={beats} returned={beats}')
        lines.append(f'STAGE2_SOC_LOAN_DONE lane={lane} commands={count} accepted={total} returned={total}')
    return '\n'.join(lines)


class TestActualCoreAccounting(unittest.TestCase):
    def test_native_and_borrowed_paths(self):
        for enabled in (0, 1):
            for modes in ((4, 8, 8, 4), (4, 4), (8, 8)):
                result = run.check_loans(fixture(enabled, modes), 32, enabled, check.fields, modes)
                self.assertEqual(result['commands_per_lane'], len(modes)*2*enabled)

    def test_wrong_or_incomplete_work_rejected(self):
        original = fixture(1)
        for text in (original.replace('core_issued=4096', 'core_issued=0', 1),
                     original.replace('lane=0 seq=1', 'lane=0 seq=2', 1),
                     '\n'.join(original.splitlines()[1:]),
                     original.replace('returned=4096', 'returned=4095', 1),
                     original + '\nSTAGE2_SOC_LOAN_DONE lane=0 commands=8 accepted=0 returned=0'):
            with self.assertRaises(ValueError):
                run.check_loans(text, 32, 1, check.fields)


if __name__ == '__main__':
    unittest.main()
