"""Gap64 positive/negative audits. Real-trace mutations are entirely in memory."""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'coverage'))
import audit_gap64_lr as audit
import run_gap64_lr_checked_extension as adapter

PREFLIGHT = None


class OracleTest(unittest.TestCase):
    def test_exact_24(self):
        self.assertEqual(audit.expected_values(0),[
            0x0123456789abcdef,0xffffffff89abcdef,0x01234567,
            0x800000007fffffff,0x7fffffff,0xffffffff80000000,
            0xfedcba9876543210,0x76543210,0xfffffffffedcba98,
            0x00000001ffffffff,0xffffffffffffffff,1])
        self.assertEqual(audit.expected_values(1),[
            0x89abcdef01234567,0x01234567,0xffffffff89abcdef,
            0x7fffffff80000000,0xffffffff80000000,0x7fffffff,
            0x76543210fedcba98,0xfffffffffedcba98,0x76543210,
            0xffffffff00000001,1,0xffffffffffffffff])

    def test_guard_constants(self):
        self.assertEqual(audit.guard(0,1,7),0x9494949494949493)
        self.assertEqual(audit.guard(1,1,0),0xeca86420db97531f)

    def test_exact_command(self):
        self.assertEqual(audit.expected_command('spike','elf'),['spike',
            '--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits','elf'])

    def test_dts(self): audit.validate_pmp_dts('riscv,pmpregions = <0>;')
    def test_nonzero_pmp(self):
        with self.assertRaises(ValueError): audit.validate_pmp_dts('riscv,pmpregions = <16>;')
    def test_two_harts(self):
        with self.assertRaises(ValueError): audit.validate_pmp_dts('riscv,pmpregions = <0>;'*2)
    def test_log(self): audit.check_log('gap35 checks=51 failures=0\nPASSED: /src.c!\n','/src.c')
    def test_wrong_count(self):
        with self.assertRaises(ValueError): audit.check_log('gap35 checks=50 failures=0\nPASSED: /src.c!','/src.c')
    def test_wrong_source(self):
        with self.assertRaises(ValueError): audit.check_log('gap35 checks=51 failures=0\nPASSED: src.c!','/src.c')
    def test_duplicate_pass(self):
        with self.assertRaises(ValueError):
            audit.check_log('gap35 checks=51 failures=0\nPASSED: /src.c!\nPASSED: /src.c!','/src.c')
    def test_failure(self):
        with self.assertRaises(ValueError):
            audit.check_log('gap35 checks=51 failures=0\ncheck=3 got=1 want=0\nPASSED: /src.c!','/src.c')


class SealTest(unittest.TestCase):
    def setUp(self):
        self.result={'status':'PASS'}; self.files={'source':'a'*64,'tool':'b'*64}
        self.saved=dict(status='PASS',read_only_validation=True,result=copy.deepcopy(self.result),
                        checked_files=dict(self.files))
    def check(self): adapter.require_exact_replay(self.result,self.files,self.saved)
    def test_positive(self): self.check()
    def test_missing(self):
        del self.files['tool']
        with self.assertRaises(ValueError): self.check()
    def test_extra(self):
        self.files['extra']='c'*64
        with self.assertRaises(ValueError): self.check()
    def test_drift(self):
        self.files['source']='c'*64
        with self.assertRaises(ValueError): self.check()
    def test_result(self):
        self.result['unexpected']=1
        with self.assertRaises(ValueError): self.check()
    def test_not_read_only(self):
        self.saved['read_only_validation']=False
        with self.assertRaises(ValueError): self.check()
    def test_chain(self):
        script=adapter.checked.SCRIPT
        delegate=lambda item,proof:'delegated'
        with patch.object(adapter.evidence,'precheck',delegate),patch.object(adapter,'_installed',False):
            adapter.install_hooks(); hook=adapter.evidence.precheck; adapter.install_hooks()
            self.assertIs(adapter.evidence.precheck,hook)
            self.assertEqual(adapter.checked.SCRIPT,script)
            self.assertEqual(hook({'name':'other'},None),'delegated')
            with patch.object(adapter,'sealed_precheck',return_value='sealed') as sealed:
                item={'name':adapter.NAME}
                self.assertEqual(hook(item,None),'sealed')
                sealed.assert_called_once_with(item,None,delegate)


class RealTraceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if PREFLIGHT is None:
            raise unittest.SkipTest('real-trace tests run after the new Spike precheck')
        cls.info=json.loads((PREFLIGHT/'execution-proof.json').read_text())['spike']['metadata']
        cls.trace=(PREFLIGHT/'case.spike.stderr.log').read_text()
        cls.lines=cls.trace.splitlines()
    def rejected(self,trace):
        with self.assertRaises(ValueError): audit.trace_check(trace,self.info)
    def mutate(self,pattern,replace):
        result,count=re.subn(pattern,replace,self.trace,count=1,flags=re.M)
        self.assertEqual(count,1); self.rejected(result)
    def test_positive(self):
        self.assertEqual(audit.trace_check(self.trace,self.info)['lr_w'],16)
    def test_retired_gate(self): self.rejected(self.trace+'\ncore 0: 3 0x80000000 (0x13)'*45001)
    def test_trap(self): self.rejected(self.trace+'\ncore 0: exception trap_load_access_fault, epc 0x80000000')
    def test_other_hart(self): self.rejected(self.trace+'\ncore 1: 3 0x80000000 (0x13)')
    def test_pmp_probe(self): self.rejected('core 0: 3 0x80000000 (0x3a002573) x10 0x0\n'+self.trace)
    def test_wrong_sign(self): self.mutate(r'(\(0x10032e2f\) x28 )0xffffffff89abcdef',r'\g<1>0x0000000089abcdef')
    def test_wrong_lr_address(self): self.mutate(r'(\(0x10033e2f\)[^\n]*mem 0x)([0-9a-f]+)',
        lambda m:m[1]+format(int(m[2],16)+8,'016x'))
    def test_wrong_lr_width(self): self.mutate(r'^(core\s+0: 3[^\n]*)\(0x10033e2f\)', r'\1(0x10032e2f)')
    def test_sc_forbidden(self): self.mutate(r'^(core\s+0: 3[^\n]*)\(0x10033e2f\)', r'\1(0x18033e2f)')
    def test_missing_lr(self): self.mutate(r'^core\s+0: 3[^\n]*\(0x10033e2f\)[^\n]*\n','')
    def test_duplicate_lr(self):
        lines=self.trace.splitlines()
        index=next(i for i,l in enumerate(lines) if re.match(r'^core\s+0: 3.*\(0x10033e2f\)',l))
        lines.insert(index,lines[index]); lines.pop()
        self.rejected('\n'.join(lines))
    def test_non_m_lr(self): self.mutate(r'^(core\s+0:) 3([^\n]*\(0x10033e2f\))',r'\1 1\2')
    def test_predecessor_store(self): self.mutate(r'(mem 0x[0-9a-f]+ )0x0123456789abcdef',r'\g<1>0x0123456789abcdee')
    def test_corrupt_buffer_read(self):
        address=self.info['symbols']['gap64_capture']+64
        self.mutate(r'^(core\s+0: 3[^\n]* x[0-9]+ )0x[0-9a-f]+( mem 0x%016x)$'%address,
                    r'\g<1>0x1\2')
    def test_missing_guard_read(self):
        address=self.info['symbols']['gap64_payload']
        self.mutate(r'^core\s+0: 3[^\n]* mem 0x%016x\n'%address,'')
    def test_missing_full_register_read(self):
        address=self.info['symbols']['gap64_capture']+64+543*8
        self.mutate(r'^core\s+0: 3[^\n]* mem 0x%016x\n'%address,'')
    def test_wrong_elf_site(self):
        info=copy.deepcopy(self.info); info['sites']['gap64_lr_d']['word']='0x18033e2f'
        with self.assertRaises(ValueError): audit.trace_check(self.trace,info)


if __name__=='__main__':
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--preflight',type=Path)
    options,rest=parser.parse_known_args()
    PREFLIGHT=options.preflight
    unittest.main(argv=[sys.argv[0],*rest])
