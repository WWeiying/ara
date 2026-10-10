import unittest
from test_fsm741_exact_capture import InventoryTest
import fsm741_exact_capture_v2 as v2


class RootTest(unittest.TestCase):
    def test_only_system_root_is_reported_all_groups_still_audited(self):
        hook = v2.HOOK.read_text()
        self.assertIn('set p740_scopes [list ara_tb.dut.i_ara_soc.i_system]', hook)
        self.assertNotIn('lappend p740_scopes', hook)
        self.assertIn('foreach group $fx_groups', hook)
        self.assertIn('fx_audit final 0', hook)
        self.assertIn('p740_summary final', hook)


if __name__ == '__main__':
    unittest.main()
