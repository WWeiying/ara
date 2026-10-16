import unittest
from linux_stability_matrix import matrix, isolated_case


class IsolatedTests(unittest.TestCase):
    def test_pipe_timeout_preserves_workload(self):
        for repetitions, budget in ((100, 300), (200, 600), (500, 1500)):
            item = next(s for s in matrix('/tmp/test', 'process', repetitions) if s[0] == 'pipes')
            self.assertEqual(item[2], budget)
            self.assertEqual(item[1], f'n=0; while [ $n -lt {repetitions} ]; do test "$(printf abc | cat | wc -c)" -eq 3; n=$((n+1)); done')

    def test_all_original_targets_unchanged(self):
        count = 0
        for profile in ('process', 'compute', 'storage', 'timers'):
            for original in matrix('/tmp/test', profile, 200):
                case = list(isolated_case('/tmp/test', profile, original[0], 200))
                self.assertEqual([s for s in case if s[0] == original[0]], [original])
                count += 1
        self.assertEqual(count, 72)

    def test_dependencies(self):
        self.assertEqual([s[0] for s in isolated_case('/tmp/test', 'storage', 'offset_4093')],
                         ['fixture_mkdir', 'fixture_random', 'offset_4093', 'fixture_cleanup'])
        self.assertEqual([s[0] for s in isolated_case('/tmp/test', 'compute', 'compression')],
                         ['fixture_mkdir', 'fixture_pattern', 'compression', 'fixture_cleanup'])


if __name__ == '__main__':
    unittest.main()
