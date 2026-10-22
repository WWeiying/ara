import importlib.util
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
spec = importlib.util.spec_from_file_location('fence_checked',
    ROOT / 'verification/coverage/run_fence_checked_extension.py')
fence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fence)


class FenceAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.sites = [{'fence_pc': hex(p), 'resume_pc': hex(p + 4),
                       'auipc_pc': hex(p + 8)} for p in (0x80001000, 0x80002000)]
        self.trace = '3 0x80000000 (0x00002197)\n'
        for site in self.sites:
            for key, word in (('fence_pc', 0xb), ('resume_pc', 0x0fefb823), ('auipc_pc', 0xf17)):
                self.trace += f'3 {site[key]} (0x{word:08x})\n'

    def test_exact_resume(self):
        self.assertEqual(fence.trace_sites(self.trace, self.sites)['rounds'], 2)

    def test_store_encoding(self):
        self.assertEqual(fence.builder().store_insn(30, 31, 240), 0x0fefb823)

    def test_nop_rejected(self):
        with self.assertRaises(ValueError):
            fence.trace_sites(self.trace.replace('0x0000000b', '0x00000013'), self.sites)

    def test_duplicate_boot_rejected(self):
        with self.assertRaises(ValueError):
            fence.trace_sites(self.trace + '3 0x80000000 (0x00002197)\n', self.sites)

    def test_wrong_mode_rejected(self):
        with self.assertRaises(ValueError):
            fence.trace_sites(self.trace.replace('3 0x80001000', '1 0x80001000'), self.sites)

    def test_missing_resume_rejected(self):
        with self.assertRaises(ValueError):
            fence.trace_sites(self.trace.replace('3 0x80001004 (0x0fefb823)\n', ''), self.sites)

    def test_duplicated_probe_rejected(self):
        with self.assertRaises(ValueError):
            fence.trace_sites(self.trace + self.trace.split('\n', 1)[1], self.sites)

    def test_wrong_order_rejected(self):
        lines = self.trace.splitlines()
        wrong = '\n'.join([lines[0], *lines[4:], *lines[1:4]])
        with self.assertRaises(ValueError):
            fence.trace_sites(wrong, self.sites)

    def test_malformed_trace_rejected(self):
        with self.assertRaises(ValueError):
            fence.trace_sites(self.trace + 'unparsed event\n', self.sites)

    def test_uart_mutations(self):
        text = f'{fence.NAME} rounds=2 checks=458 failures=0\nPASSED: {fence.NAME}\n'
        self.assertEqual(fence.builder().validate_log(text)['checks'], 458)
        for bad in (text * 2, text.replace('458', '457'), text + 'FAIL: bad\n'):
            with self.assertRaises(ValueError):
                fence.builder().validate_log(bad)

    def test_native_line_mapping(self):
        source = '\n'.join([
            'if (fence_t_i) fence_t_state_d = FLUSH_DCACHE;',
            'if (flush_dcache_ack_i) fence_t_state_d = DRAIN_REQS;',
            'fence_t_state_d = PAD;',
            "if (pad_cnt == '0) fence_t_state_d = RST_UARCH;",
            "rst_uarch_no    = 1'b0;", "rst_uarch_cnt_d = 4'b0;",
        ])
        root = ET.Element('linedef')
        signatures = ['fence_t_state_d = FLUSH_DCACHE;', 'fence_t_state_d = DRAIN_REQS;',
                      'fence_t_state_d = PAD;', 'fence_t_state_d = RST_UARCH;',
                      "rst_uarch_no = 1'b0;", "rst_uarch_cnt_d = 4'b0;"]
        for line, index in enumerate((5, 3, 4, 1, 2, 0), 1):
            block = ET.SubElement(root, 'linebb', index=str(index), file_id='1',
                                  line_num=str(line), line_ignore='0', bbsig=signatures[line-1])
            ET.SubElement(block, 'linestmt', file_id='1', line_num=str(line),
                          line_ignore='0', line_type='1')
        row = {'width': 6, 'bits': '0x3f'}
        result = fence.line_activity(root, row, '1', source)
        self.assertEqual(result['IDLE_to_FLUSH_DCACHE']['hit_indices'], [5])
        for bit in range(6):
            with self.assertRaises(ValueError):
                fence.line_activity(root, dict(row, bits=hex(63 ^ (1 << bit))), '1', source)
        with self.assertRaises(ValueError):
            fence.line_activity(root, row, '2', source)
        # One source line can have separate conditional, assignment and empty
        # false-branch points. Hitting the condition cannot prove assignment.
        condition = ET.SubElement(root, 'linebb', index='6', file_id='1', line_num='1',
                                  line_ignore='0', bbsig='if (fence_t_i)')
        ET.SubElement(condition, 'linestmt', file_id='1', line_num='1',
                      line_ignore='0', line_type='0')
        empty = ET.SubElement(root, 'linebb', index='7', file_id='1', line_num='1',
                              line_ignore='0', bbsig='')
        ET.SubElement(empty, 'linestmt', file_id='1', line_num='1',
                      line_ignore='5', line_type='1')
        with self.assertRaises(ValueError):
            fence.line_activity(root, {'width': 8, 'bits': '0xfb'}, '1', source)
        self.assertEqual(fence.line_activity(root, {'width': 8, 'bits': '0xff'}, '1', source)
                         ['IDLE_to_FLUSH_DCACHE']['hit_indices'], [5])


if __name__ == '__main__':
    unittest.main()
