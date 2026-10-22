import json
import unittest
import review_cva6_fixed_fields768 as m


class FixedFields(unittest.TestCase):
    def test_normal_exception_and_address_retained(self):
        for name in ('instruction_o.ex.tval', 'instruction_o.ex.cause', 'instruction_o.pc', 'issue_q[0].sbe'):
            self.assertIsNone(m.selection(dict(name=name, scope='x.decoder_i')))

    def test_accelerator_result_only_upper_half(self):
        self.assertEqual(m.selection(dict(name='instruction_o.result', scope='x.i_accel_decoder'))[1], (63, 32))
        for name in ('instruction_o.op', 'instruction_o.fu', 'instruction_o.rs1'):
            self.assertIsNone(m.selection(dict(name=name, scope='x.i_accel_decoder')))

    def test_fifo_unknown_is_hold(self):
        self.assertTrue(m.selection(dict(name='fifo_ram_rdata', scope='x.i_instr_queue.i_fifo_address'))[0].startswith('HOLD'))
        self.assertIsNone(m.selection(dict(name='mem_q', scope='x.i_instr_queue.i_fifo_address')))

    def test_actual_shape_constant_projections(self):
        rank = json.loads(m.RANK.read_bytes())
        count = 0
        for field in rank['owned_fields']:
            choice = m.selection(field)
            if not choice or choice[0].startswith('HOLD'):
                continue
            partial = choice[1]
            left, right = partial or (int(field.get('left', '0')), int(field.get('right', '0')))
            offset = field['serialized_offset']
            coordinates = {offset + 2 * (bit - int(field.get('right', '0'))) + d
                           for bit in range(right, left + 1) for d in (0, 1)}
            self.assertTrue(coordinates <= set(field['missing_coordinates']))
            count += len(coordinates)
        self.assertEqual(count, 4396)


if __name__ == '__main__':
    unittest.main()
