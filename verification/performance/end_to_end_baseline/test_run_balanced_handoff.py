import unittest

import run_balanced_handoff as b


def fixture():
    lines = [b.program.SCOPE]
    for i in range(4):
        row = dict(seq=i + 1, m=4, n=3, vlen=1024, lanes=4, success=1, fault=0,
                   validation_fault=0, read_fault=0, useful_pairs=3072, dot_active_cycles=32,
                   weight_bytes=432, activation_bytes=1168, payload_bytes=1616,
                   activation_access=0, read_ranges=8, r_beats=92, accumulator_updates=12,
                   fp_uop_issue=72, commit_groups=16, busy_cycles=200, ar=12)
        row.update({'phase_' + phase + '_cycles': 200 if i == 0 else 0
                    for i, phase in enumerate(b.PHASES)})
        lines.append('[QBS_PERF] ' + ' '.join(k + '=' + str(v) for k, v in row.items()))
    for i, command in enumerate((4, 2, 3, 4, 2, 2, 2, 3, 4, 3)):
        row = {key: 0 for key in b.akv_parser.PERF_FIELDS}
        row.update(seq=i + 1, command=command, success=1, v2_full=int(command == 4), busy_cycles=50,
                   context_ready=int(command != 3), load=int(command == 2),
                   v2_row_load=int(command == 2), release=int(command == 3))
        lines.append('[AKV_PERF] ' + ' '.join(k + '=' + str(v) for k, v in row.items()))
    # Completed QBS/AKV work follows the actual adjacent ownership transfers.
    lines = [lines[0], *lines[1:3], *lines[5:], *lines[3:5]]
    return '\n'.join([*lines, b.program.PASS, 'Core Test *** SUCCESS *** (tohost = 0)',
                      'UVM_ERROR : 0', 'UVM_FATAL : 0'])


class BalancedHandoffRuntime(unittest.TestCase):
    def test_original_worker_is_unchanged_and_namespace_isolated(self):
        fn, record = b.specialize()
        self.assertIsNot(fn, b.parent.run)
        self.assertIs(fn.__globals__['check_program'], b.check_program)
        self.assertIsNot(b.parent.check_program, b.check_program)
        self.assertTrue(record['source_reversible'])
        self.assertFalse(record['numerical_or_protocol_checks_removed'])

    def test_actual_m4_work_and_akv_sequence_required(self):
        text = fixture()
        self.assertEqual(b.check_program(text, 'handoff')['actual_m4_commands'], 4)
        for old, new in (('m=4 n=3', 'm=1 n=3'), ('dot_active_cycles=32', 'dot_active_cycles=64'),
                         ('activation_bytes=1168', 'activation_bytes=292'), ('r_beats=92', 'r_beats=91'),
                         ('fp_uop_issue=72', 'fp_uop_issue=18'), ('commit_groups=16', 'commit_groups=4'),
                         ('phase_setup_cycles=200', 'phase_setup_cycles=199'),
                         ('seq=1 id=0 command=4', 'seq=1 id=0 command=5')):
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(ValueError):
                b.check_program(text.replace(old, new, 1), 'handoff')

    def test_skip_missing_terminal_wrong_core_or_old_m1_are_not_pass(self):
        text = fixture()
        for bad in (text.replace(b.program.PASS, ''), text.replace(b.program.PASS, b.program.parent.PASS),
                    text.replace('PASS traps=0', 'SKIP traps=0'), text + '\n' + b.program.PASS,
                    text.replace('tohost = 0', 'tohost = 1'), text + '\nQBS M4 mismatch[row=3 col=0]',
                    text.replace('[AKV_PERF] seq=1 id=0 command=4', '[IGNORED] seq=1 id=0 command=4')):
            self.assertNotEqual(text, bad)
            with self.assertRaises(ValueError):
                b.check_program(bad, 'handoff')
        with self.assertRaises(ValueError):
            b.check_program(text, 'memory')

    def test_actual_digit_bearing_akv_schema_and_joint_sequence(self):
        text = fixture()
        self.assertIn('v2_full=1', text)
        b.check_program(text, 'handoff')
        lines = text.splitlines()
        other = [line for line in lines if not line.startswith(('[QBS_PERF] ', '[AKV_PERF] '))]
        qbs = [line for line in lines if line.startswith('[QBS_PERF] ')]
        akv = [line for line in lines if line.startswith('[AKV_PERF] ')]
        grouped = '\n'.join([other[0], *qbs, *akv, *other[1:]])
        with self.assertRaisesRegex(ValueError, 'ownership handoff order'):
            b.check_program(grouped, 'handoff')
        for bad in (text.replace('v2_full=1', '', 1),
                    text.replace('v2_full=1', 'v2_full=1 v2_full=1', 1),
                    text.replace('v2_full=1', 'v2_full=x', 1)):
            with self.assertRaises(ValueError):
                b.check_program(bad, 'handoff')


if __name__ == '__main__':
    unittest.main()
