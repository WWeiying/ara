import unittest

import run_soc_sram_mc as r


def fixture():
    rows = ['MC_CASE_PASS ' + ' '.join(key + '=' + str(value) for key, value in r.expected_case(i).items())
            for i in range(len(r.CONFIGS))]
    return '\n'.join(rows + ['MC_COMPONENT_PASS cases=10']) + '\n'


class SocSramMcTests(unittest.TestCase):
    def test_extracts_exact_current_source_and_actual_default_and_ff(self):
        text = r.DUT.read_text(); wrapper, body, expression = r.extracted_slice(text)
        self.assertEqual(body, text.split('  // TARGET_SRAM_MC_BEGIN\n')[1].split('  // TARGET_SRAM_MC_END\n')[0])
        self.assertIn(body, wrapper)
        self.assertEqual(expression.replace(' ', ''), '(2**20)/(AxiDataWidth/8)')
        self.assertIn("`FF(l2_rvalid, l2_req, 1'b0);", wrapper)
        self.assertIn('TS1N28HPCPSVTB8192X128M4SWBASO i_dram', body)
        self.assertIn("dram_bank_ren <= '0;", body)
        self.assertIn('dram_bank_ren <= dram_bank_en;', body)
        self.assertIn('MC_SELECTOR_RESET_FAIL', wrapper)
        self.assertIn('MC_UNUSED_COLUMN_BITS_FAIL', wrapper)
        self.assertNotIn('tc_sram #(', wrapper)

    def test_extraction_rejects_missing_duplicate_or_changed_contract(self):
        text = r.DUT.read_text()
        for damaged in (text.replace('  // TARGET_SRAM_MC_BEGIN\n', '', 1),
                        text + '\n  // TARGET_SRAM_MC_END\n',
                        text.replace("`FF(l2_rvalid, l2_req, 1'b0);", "`FF(l2_rvalid, l2_we, 1'b0);")):
            with self.assertRaises(ValueError): r.extracted_slice(damaged)

    def test_independent_schedule_conservation_and_fixed_capacity(self):
        for i, (width, words, default) in enumerate(r.CONFIGS):
            row = r.expected_case(i); banks, byte_count = words // 8192, width // 8
            self.assertEqual(row['steps'], 8*banks + 4*byte_count + 140)
            self.assertEqual(row['steps'], row['reads'] + row['writes'] + row['idle'])
            self.assertEqual(row['holds'], row['writes'] + row['idle'])
            self.assertEqual(row['reads'], 4*banks + 2*byte_count + 37)
            self.assertEqual(row['phases'], byte_count)
            self.assertEqual(row['checked_read_bytes'], row['reads'] * byte_count)
            self.assertGreater(row['masked'], 0); self.assertGreater(row['zero_mask'], 0)
            if banks > 1: self.assertGreater(row['switches'], 0)
            if default: self.assertEqual(words * byte_count, 1048576)
        for lanes in (1, 2, 4, 8, 16):
            self.assertEqual((2**20) // ((32*lanes)//8), (2**18)//lanes)

    def test_checker_requires_exact_counts_and_all_ten_geometries(self):
        measured = r.check(fixture())
        self.assertEqual(len(measured['cases']), 10)
        self.assertEqual(measured['checked_read_bytes'], sum(r.expected_case(i)['checked_read_bytes'] for i in range(10)))
        for old, new in (('checked_read_bytes=43', 'checked_read_bytes=42'), ('phases=1 ', 'phases=0 '),
                         ('resets=2', 'resets=1'), ('banks=8 ', 'banks=4 '), ('cases=10', 'cases=9')):
            self.assertIn(old, fixture())
            with self.subTest(old=old), self.assertRaises(ValueError): r.check(fixture().replace(old, new, 1))

    def test_missing_duplicate_fatal_return_zero_and_unknown_records_rejected(self):
        text = fixture(); first = text.splitlines()[0]
        for broken in (text.replace(first + '\n', '', 1), text + first + '\n',
                       text + 'Fatal: SRAM checker failed\n', text + 'MC_MACRO_CONTROL_FAIL\n',
                       text + 'MC_OTHER_PASS cases=10\n'):
            with self.assertRaises(ValueError): r.check(broken)

    def test_duplicate_numeric_fields_rejected(self):
        with self.assertRaises(ValueError): r.fields('MC_COMPONENT_PASS cases=10 cases=10', 'MC_COMPONENT_PASS')


if __name__ == '__main__':
    unittest.main()
