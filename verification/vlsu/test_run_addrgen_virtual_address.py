import unittest
from pathlib import Path

from run_addrgen_virtual_address import MODULES, PACKAGES, parse_cases, source_map


class RunnerTests(unittest.TestCase):
    def test_current_source_mapping(self):
        paths = []
        for name in PACKAGES + MODULES:
            prefix = 'ara/hardware/src' if name == 'addrgen.sv' else 'cva6/core'
            paths.append(f"Parsing design file '/old/hardware/fpga/board/rtl/{prefix}/{name}'")
        mapped = source_map('\n'.join(paths), Path('/current'))
        self.assertEqual(len(mapped), len(PACKAGES + MODULES))
        self.assertTrue(all('/fpga/' not in str(p) for p in mapped))
        self.assertEqual(mapped[-1], Path('/current/hardware/src/addrgen.sv'))

    def test_missing_source_is_error(self):
        with self.assertRaises(ValueError):
            source_map('')

    def test_incomplete_simulation_is_error(self):
        with self.assertRaises(ValueError):
            parse_cases('CASE_PASS kind=0 width=48\n')

    def test_complete_results(self):
        log = '\n'.join(f'CASE_PASS kind={i} width=48 cycles=61' for i in range(10))
        self.assertEqual(len(parse_cases(log + '\nADDRGEN_VIRTUAL_ADDRESS_PASS')), 10)


if __name__ == '__main__':
    unittest.main()
