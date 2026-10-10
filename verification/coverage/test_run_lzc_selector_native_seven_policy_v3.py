import unittest
import run_lzc_selector_native_seven_policy_v3 as subject


class RunnerTests(unittest.TestCase):
    def test_private_runtime_and_gates(self):
        self.assertIs(subject.prepare_entry.__globals__['generic'],subject.generic)
        self.assertIs(subject.invoke_run.__globals__['generic'],subject.generic)
        self.assertIs(subject.reviewed_entry.__globals__['generic'],subject.generic)
        self.assertTrue(callable(subject.generic.read_config))

    def test_dependencies_cover_predecessor_and_successor(self):
        names={p.name for p in subject.generic.successor_dependencies()}
        self.assertIn('lzc_selector_native_seven_policy_runtime_v2.py',names)
        self.assertIn('run_lzc_selector_native_seven_policy_v3.py',names)
        self.assertEqual(subject.generic.frozen.TIMEOUT,subject.generic.serialization_prior.frozen.TIMEOUT)


if __name__ == '__main__': unittest.main()
