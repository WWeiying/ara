import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('env', Path(__file__).with_name('gate_rvv_env_v1.py'))
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


class Tests(unittest.TestCase):
    def witness(self):
        return dict(state='FIRST_X_DIAGNOSTIC_COMPLETE_NOT_POWER', wave=dict(
            merge_samples=[dict(tick=1, values={'alu.operand_a_i': '1010', 'alu.operand_b_i': 'xxxx',
                'alu.result_o': 'xxxx', 'alu.vm_i': '1', 'alu.mask_i': '11111111'})],
            reductions={'0x80001380': ['xxxx']}))

    def test_root_witness(self):
        self.assertEqual(e.firstx_witness(self.witness())['a'], '0xa')

    def test_no_guess(self):
        for field, bad in [('operand_a_i', 'xxxx'), ('operand_b_i', '1010'), ('result_o', '1010'),
                           ('vm_i', '0'), ('mask_i', '00000000')]:
            row = self.witness()
            row['wave']['merge_samples'][0]['values']['alu.' + field] = bad
            with self.assertRaises(ValueError):
                e.firstx_witness(row)

    def test_no_reduction_no_repair(self):
        row = self.witness()
        row['wave']['reductions'] = {}
        with self.assertRaises(ValueError):
            e.firstx_witness(row)

    def test_active_x_not_hidden(self):
        signals = {'soc.' + x: dict(unknown_records=0) for x in ('pc_commit', 'commit_ack_commit_id', 'state_q')}
        signals['ara_tb.dut.i_ara_soc.clk_i'] = dict(unknown_records=0)
        report = dict(signals=signals)
        e.clean_quality(report, dict(counts={}))
        with self.assertRaises(ValueError):
            e.clean_quality(report, dict(counts={'D/DM': 1}))
        for key in signals:
            bad = copy.deepcopy(report)
            bad['signals'][key]['unknown_records'] = 1
            with self.assertRaises(ValueError):
                e.clean_quality(bad, dict(counts={}))

    def test_reset_scope(self):
        text = e.initializer(['soc.vrf0', 'soc.vrf1'])
        self.assertEqual(text.count('.MEMORY[row][0]'), 2)
        self.assertNotIn('force ', text)
        self.assertNotIn('release ', text)
        self.assertIn("ara_tb.rst_n !== 1'b0", text)


if __name__ == '__main__':
    unittest.main()
