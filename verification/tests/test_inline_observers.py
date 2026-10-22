import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location('inline_observers',
    Path(__file__).resolve().parents[1] / 'coverage/inspect_inline_observers.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class InlineObserverTest(unittest.TestCase):
    def test_nested_guard_and_inverse(self):
        text = '`ifdef FOR_VERIFY\na\n`ifdef OTHER\nb\n`else\nc\n`endif\n`else\nd\n`endif\n'
        self.assertEqual(MODULE.guarded_lines(text), {2, 4, 6})
        self.assertEqual(MODULE.guarded_lines('`ifndef FOR_VERIFY\na\n`else\nb\n`endif'), {4})

    def test_reject_ambiguous_guard(self):
        for text in ('`endif', '`ifdef FOR_VERIFY', '`ifdef X\n`elsif Y\n`endif'):
            with self.assertRaises(ValueError):
                MODULE.guarded_lines(text)

    def test_mixed_block_is_not_candidate(self):
        definition = ET.fromstring('''<linedef>
          <linebb index="0" file_id="7" line_num="10"><linestmt file_id="7" line_num="11"/></linebb>
          <linebb index="1" file_id="7" line_num="10"><linestmt file_id="7" line_num="12"/></linebb>
          <linebb index="2" file_id="8" line_num="10"/>
        </linedef>''')
        result = MODULE.classify(definition, {'width': 4, 'bits': '0xb'}, '7', {10, 11})
        self.assertEqual(result['raw_line_bits'], {'guarded_candidate_points': 1,
            'guarded_candidate_hit': 1, 'remaining_mapped_points': 2,
            'remaining_mapped_hit': 1, 'unmapped_points': 1, 'unmapped_hit': 1})
        self.assertEqual(len(result['candidate_blocks']), 1)

    def test_reject_duplicate_index(self):
        definition = ET.fromstring('<linedef><linebb index="0"/><linebb index="0"/></linedef>')
        with self.assertRaises(ValueError):
            MODULE.classify(definition, {'width': 1, 'bits': '0x0'}, '7', set())


if __name__ == '__main__':
    unittest.main()
