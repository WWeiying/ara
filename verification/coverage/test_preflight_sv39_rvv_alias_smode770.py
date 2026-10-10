import copy
import os
import unittest
from test_preflight_sv39_rvv_alias770 import StaticTests,ActualTests
import preflight_sv39_rvv_alias_smode770 as s


class ExceptionTests(unittest.TestCase):
    def test_precise_supervisor_return(self):
        text='core 0: exception trap_supervisor_ecall, epc 0x80000010\n'*48
        s.exception_gate(text,{'alias_s_ecall':0x80000010})

    def test_extra_wrong_cause_and_pc(self):
        good='core 0: exception trap_supervisor_ecall, epc 0x80000010\n'*48
        for text in (good+good.splitlines()[0],good.replace('supervisor','machine',1),
                     good.replace('80000010','80000014',1)):
            with self.assertRaises(ValueError):s.exception_gate(text,{'alias_s_ecall':0x80000010})


@unittest.skipUnless(os.environ.get('ALIAS_PREFLIGHT'),'Set actual S-mode fixture')
class ActualSMode(ActualTests):
    def test_actual_smode_and_full_oracle(self):
        s.exception_gate((self.directory/'spike.trace').read_text(),self.symbols)
        self.assertEqual(s.validate(self.commits,self.symbols)['expected_supervisor_ecalls'],48)

    def test_wrong_vl(self):
        c=copy.deepcopy(self.commits)
        target=next(x for x in c if x.pc==self.symbols['alias_store_site'])
        object.__setattr__(target,'vector_vl',16)
        with self.assertRaises(ValueError):s.validate(c,self.symbols)

    def test_wrong_return_cause(self):
        c=copy.deepcopy(self.commits)
        target=next(x for x in c if x.pc==self.symbols['alias_machine_return'])
        target.gpr_writes[next(iter(target.gpr_writes))]=11
        with self.assertRaises(ValueError):s.validate(c,self.symbols)


if __name__=='__main__':unittest.main()
