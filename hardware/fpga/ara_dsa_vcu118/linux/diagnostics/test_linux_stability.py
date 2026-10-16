import hashlib
import unittest
from linux_stability import plan, validate, has_kernel_fault
from linux_stability_matrix import matrix, PROFILES, zero_digest, process_case, REMAINING_PROCESS_CASES


class StabilityTests(unittest.TestCase):
    def test_remaining_cases_preserve_original_commands_and_boundaries(self):
        original = {s[0]: s for s in matrix('/tmp/test', 'process', 200)}
        self.assertEqual(len(REMAINING_PROCESS_CASES), 7)
        for name in REMAINING_PROCESS_CASES:
            steps = list(process_case('/tmp/test', name, 200))
            self.assertEqual(steps[1], original[name])
            self.assertEqual(steps[0][0], 'case_setup')
            self.assertNotIn('exec_loader', [s[0] for s in steps])
            self.assertEqual(len(steps), 2 if name == 'cleanup' else 3)
        with self.assertRaises(ValueError):
            list(process_case('/tmp/test', 'exec_loader'))
    def test_matrix_inventory(self):
        for profile in PROFILES:
            steps = list(matrix('/tmp/test', profile, 100))
            self.assertEqual(len(steps), len({s[0] for s in steps}))
            self.assertEqual(steps[-1][0], 'cleanup')
            self.assertTrue(all(0 < s[2] <= 360 for s in steps))
        with self.assertRaises(ValueError):
            list(matrix('/tmp/test', 'process', 501))

    def test_generic_oracle(self):
        for size in (0, 1, 65535, 65536, 65537):
            self.assertEqual(zero_digest(size), hashlib.sha256(bytes(size)).hexdigest())
        h = zero_digest(1)
        validate(('sha256', h, '/tmp/test/z'), h+'  /tmp/test/z\r\n', '/tmp/test')
        validate(('text', 'FLOAT_OK'), 'FLOAT_OK\r\n', '/tmp/test')
        validate(('text', 'FLOAT_OK'), 'FLOAT_OK\r\r\n', '/tmp/test')
        with self.assertRaises(ValueError):
            validate(('text', 'FLOAT_OK'), "echo 'FLOAT_OK'", '/tmp/test')
        with self.assertRaises(ValueError):
            validate(('sha256', h, '/tmp/test/z'), h+'  /tmp/wrong', '/tmp/test')

    def test_kernel_failure_even_with_successful_command(self):
        for output in ('[ 1.234] BUG: Bad rss-counter state',
                       '[ 1383.584055] cat[598]: unhandled signal 11 code 0x1',
                       '[ 9.100] Kernel panic - not syncing'):
            with self.assertRaises(ValueError):
                validate(None, output, '/tmp/t')
        validate(None, '[ 1.234] random: crng init done', '/tmp/t')

    def test_bad_page_table_cannot_pass_with_zero_exit_status(self):
        for level in ('pgd', 'p4d', 'pud', 'pmd', 'pte'):
            output = f'[ 1570.595215] mm/pgtable-generic.c:56: bad {level} 000000002005ac5b.\r\r\nRESULT:0\r\n'
            self.assertTrue(has_kernel_fault(output))
            with self.assertRaises(ValueError):
                validate(None, output, '/tmp/t')
        self.assertFalse(has_kernel_fault("echo 'bad pmd'\r\nRESULT:0\r\n"))

    def test_plan(self):
        steps = list(plan('/tmp/ara_stability_test', 3))
        self.assertEqual(len(steps), 28)
        self.assertEqual(len({s[0] for s in steps}), len(steps))
        self.assertEqual(steps[-1][0], 'cleanup')
        self.assertTrue(all(0 < s[2] <= 120 for s in steps))

    def test_zero(self):
        digest = hashlib.sha256(bytes(8*1024*1024)).hexdigest()
        validate('zero', digest+'  /tmp/t/z\r\n', '/tmp/t')
        with self.assertRaises(ValueError):
            validate('zero', 'sha256sum /tmp/t/z\n', '/tmp/t')

    def test_random(self):
        a = 'a'*64
        validate('random', a+'  /tmp/t/a\r\n'+a+'  /tmp/t/b\r\n', '/tmp/t')
        for output in ('', a+'  /tmp/t/a\n', a+'  /tmp/t/a\n'+'b'*64+'  /tmp/t/b\n'):
            with self.assertRaises(ValueError):
                validate('random', output, '/tmp/t')


if __name__ == '__main__':
    unittest.main()
