"""Mutations of the independent reference authority fail closed."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import audit_pending_fpu_red32_reference_20261016 as audit


class ReferenceAuthorityTests(unittest.TestCase):
    def fixture(self):
        command = ['/spike', '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0', '-l', '--log-commits', '/input.elf']
        receipt = dict(command=command, returncode=0, started=1, finished=2,
                       input_pins={'/spike': audit.SPIKE_SHA, '/input.elf': 'elf'})
        record = dict(status='PASS', exact_all_parsed_commit_fields=True,
                      historical_PASS_reused=False, RTL_simulation_started=False,
                      receipt=receipt, input_pins=receipt['input_pins'])
        return record, receipt, command

    def test_complete_independent_receipt(self):
        record, receipt, command = self.fixture()
        audit.validate_receipt(record, receipt, command, 'elf')

    def test_clean_exit_or_boolean_returncode_is_insufficient(self):
        for code in (False, None, 1):
            record, receipt, command = self.fixture()
            receipt['returncode'] = code
            with self.assertRaises(ValueError):
                audit.validate_receipt(record, receipt, command, 'elf')

    def test_old_pass_or_unpinned_gold_rejected(self):
        for key, value in (('exact_all_parsed_commit_fields', False), ('historical_PASS_reused', True),
                           ('RTL_simulation_started', True)):
            record, receipt, command = self.fixture()
            record[key] = value
            with self.assertRaises(ValueError):
                audit.validate_receipt(record, receipt, command, 'elf')

    def test_spike_elf_or_options_mutation_rejected(self):
        for field in ('spike', 'elf', 'options'):
            record, receipt, command = self.fixture()
            if field == 'options':
                command[1] = '--isa=rv64gcv'
            else:
                receipt['input_pins']['/spike' if field == 'spike' else '/input.elf'] = 'changed'
            with self.assertRaises(ValueError):
                audit.validate_receipt(record, receipt, command, 'elf')


if __name__ == '__main__':
    unittest.main()
