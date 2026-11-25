"""Host whitelist tests, not power measurement evidence."""
import unittest
import akv_fifo_env_v1 as m


class ScopeTests(unittest.TestCase):
    def test_actual_netlist_whitelist(self):
        cells=m.payload_cells((m.PARENT/'source/ara_soc_dc.v').read_text())
        self.assertEqual(len(cells),1280)
        self.assertTrue(all('.i_operand_queue_alu_b.i_input_buffer.mem_q_reg_' in c for c in cells))
        self.assertFalse(any('pointer' in c or 'status_cnt' in c for c in cells))

    def test_missing_hierarchy_rejected(self):
        with self.assertRaises(ValueError):m.payload_cells('module top; endmodule')


if __name__=='__main__':unittest.main()
