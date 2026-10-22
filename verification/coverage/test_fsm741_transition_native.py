import unittest
from test_fsm741_transition_batch import BatchTest
import fsm741_transition_native as native


class ProjectionTest(unittest.TestCase):
    def test_protected_and_clear_queries_remain_strict(self):
        text = native.HOOK.read_text()
        self.assertIn('if {$want eq "0" && $actual ne "0"}', text)
        self.assertIn('if {$expected && $target} {set want NATIVE_EL_AUTHORITY}', text)
        self.assertIn('Nonboolean native query', text)


if __name__ == '__main__':
    unittest.main()
