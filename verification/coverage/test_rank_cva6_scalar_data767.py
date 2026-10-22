import unittest
import rank_cva6_scalar_data767 as r


class ShapeTests(unittest.TestCase):
    def test_arrays_do_not_consume_binary_offsets(self):
        nodes, arrays = r.typed_nodes('<tgldef><tglshape><arrays name="mem"/><vectornode name="x" left="1" right="0"/></tglshape></tgldef>',
                                     dict(width=4, bits='a'))
        self.assertEqual(nodes[0]['missing_coordinates'], [1, 3])
        self.assertEqual(arrays, [dict(name='mem')])

    def test_width_rejected(self):
        with self.assertRaises(ValueError):
            r.typed_nodes('<tgldef><tglshape><node name="x"/></tglshape></tgldef>', dict(width=3, bits='0'))

    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):
            r.typed_nodes('<tgldef><tglshape><node name="x"/></tglshape></tgldef>', dict(width=2, bits='f'))

    def test_disabled_bitmanip_and_load_write_not_targets(self):
        self.assertFalse(r.data_object('x.i_multiplier', 'clmul_q'))
        self.assertFalse(r.data_object('x.i_load_unit', 'req_port_o.data_wdata'))
        self.assertTrue(r.data_object('x.i_multiplier', 'mult_result_q'))

    def test_scoreboard_only_actual_result(self):
        self.assertTrue(r.data_object('x.i_scoreboard', 'mem_q[0].sbe.result'))
        self.assertFalse(r.data_object('x.i_scoreboard', 'mem_q[0].sbe.ex.tval'))
        self.assertFalse(r.data_object('x.i_scoreboard', 'decoded_instr_i[0].result'))

    def test_issue_and_load_data_not_counters_or_immediates(self):
        self.assertTrue(r.data_object('x.i_issue_read_operands', 'fu_data_q[0].operand_b'))
        self.assertFalse(r.data_object('x.i_issue_read_operands', 'fu_data_q[0].imm'))
        self.assertTrue(r.data_object('x.i_load_unit', 'shifted_data'))

    def test_store_queue_data_not_address(self):
        self.assertTrue(r.data_object('x.store_buffer_i', 'commit_queue_q[0].data'))
        self.assertFalse(r.data_object('x.store_buffer_i', 'commit_queue_q[0].address'))


if __name__ == '__main__':
    unittest.main()
