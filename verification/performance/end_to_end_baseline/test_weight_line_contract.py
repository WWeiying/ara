import unittest

from collect_weight_line_assembler import contract_rejection


class ContractFatalTests(unittest.TestCase):
    def fixture(self):
        return ('Fatal: "/src/qbs_weight_line_assembler.sv", 128: dut at time 65\n'
                'QBS weight line input must be a nonempty compacted prefix\n'
                '$finish called from file "/src/qbs_weight_line_assembler.sv"\n')

    def test_zero_or_one_exit_requires_specific_dut_fatal(self):
        for code in (0, 1):
            contract_rejection(code, self.fixture(), 'must be a nonempty compacted prefix')

    def test_clean_log_unknown_fatal_duplicate_wrong_reason_and_tool_failure_rejected(self):
        text = self.fixture()
        for wrong in ('', text.replace('qbs_weight_line_assembler.sv', 'some_other.sv'), text + text,
                      text.replace('nonempty', 'wrong'), text + '\nError: broken',
                      text + '\nWEIGHT_LINE_COMPONENT_PASS', text + '\nfixture was not rejected'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                contract_rejection(0, wrong, 'must be a nonempty compacted prefix')
        for code in (-9, 2, 139):
            with self.assertRaises(ValueError):
                contract_rejection(code, text, 'must be a nonempty compacted prefix')


if __name__ == '__main__':
    unittest.main()
