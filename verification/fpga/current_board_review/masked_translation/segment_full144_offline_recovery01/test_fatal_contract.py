"""Focused Host tests on the actual SoC spec; no reference/DUT execution."""
import copy
import csv
import json
from pathlib import Path
import unittest
import checker as c
import fatal_contract as f

OLD = c.HERE.parent / 'segment_full144_vcs_m8_plan01' / 'prepared02'

class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((OLD/'plan.json').read_text())['spec']
        cls.facts = f.inspect(cls.spec)

    def test_real_absent_optional_symbol(self):
        self.assertNotIn('replay_mismatch', self.facts['symbols'])
        self.assertIn(self.spec['symbols']['replay_trap'], f.validate(self.spec, self.facts))

    def test_missing_required_symbol(self):
        s = copy.deepcopy(self.spec); del s['symbols']['replay_trap']
        with self.assertRaisesRegex(ValueError, 'Spec symbols'): f.validate(s, self.facts)

    def test_fabricated_missing_symbol(self):
        s = copy.deepcopy(self.spec); s['symbols']['replay_mismatch'] = s['symbols']['mx_checkpoint']
        with self.assertRaisesRegex(ValueError, 'Spec symbols'): f.validate(s, self.facts)

    def test_wrong_fatal_mapping(self):
        s = copy.deepcopy(self.spec); s['symbols']['replay_trap'] = s['symbols']['replay_exit']
        with self.assertRaisesRegex(ValueError, 'Spec symbols'): f.validate(s, self.facts)

    def test_wrong_instruction(self):
        s = copy.deepcopy(self.spec); s['code'][str(s['symbols']['replay_trap'])] ^= 1
        with self.assertRaisesRegex(ValueError, 'Spec code'): f.validate(s, self.facts)

    def test_wrong_elf_hash(self):
        s = copy.deepcopy(self.spec); s['elf_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'ELF hash'): f.inspect(s)

    def test_actual_first_row_no_keyerror(self):
        with (OLD/'replay'/c.NAME/'commit_trace.csv').open() as fp:
            row = next(csv.DictReader(fp))
        c.Checker(self.spec).row(row)

    def test_actual_fatal_entry_and_interiors_reject(self):
        fatal = f.validate(self.spec, self.facts)
        for pc in (self.spec['symbols']['trap_entry'], self.spec['symbols']['trap_entry']+4,
                   self.spec['symbols']['replay_trap'], self.spec['symbols']['replay_trap']+4):
            with self.subTest(pc=hex(pc)):
                self.assertIn(pc, fatal)
                row = {key: '0' for key in c.FIELDS}
                row.update(event='retire', pc=hex(pc), insn=hex(self.facts['code'][pc]))
                with self.assertRaisesRegex(ValueError, 'Unexpected fatal runtime'):
                    c.Checker(self.spec).row(row)

    def test_real_handler_and_exit_not_fatal(self):
        fatal = f.validate(self.spec, self.facts)
        for name in ('mx_handler', 'mx_trap', 'replay_exit', 'mx_compare', 'mx_allowed'):
            self.assertNotIn(self.spec['symbols'][name], fatal)

    def test_capability_protocol_and_unexpected_fatal(self):
        good = 'SEGMENT144_CAPABILITY_COMPLETE\nCore Test *** FAILED *** (tohost = 77)\n$finish\n'
        c.protocol(good, 77)
        for bad in (good+'UnexpectedFatal\n', good+'BOARD_REPLAY_MISMATCH\n',
                    good.replace('tohost = 77', 'tohost = 1')):
            with self.assertRaises(ValueError): c.protocol(bad, 77)

if __name__ == '__main__': unittest.main(verbosity=2)
