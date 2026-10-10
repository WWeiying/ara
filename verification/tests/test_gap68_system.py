"""Gap68 independent oracle tests; mutate copies, never preserved evidence."""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'coverage'))
import audit_gap68_system as audit
import run_gap68_system_checked_extension as adapter
PREFLIGHT=None

class ModelTest(unittest.TestCase):
    def test_sparse_pages(self):
        p=audit.expected_pages(0x80040000)
        self.assertEqual(sum(v!=0 for t in p[:3] for v in t),4)
        self.assertEqual((p[0][1],p[1][0],p[2][0],p[2][1]),(0x20010401,0x20010801,0x20010cc3,0x20011047))
        self.assertEqual((p[3][0],p[4][511]),(audit.TAGS[0],audit.TAGS[1]^511))
    def test_log(self):
        audit.check_log('gap35 checks=71 failures=0\nPASSED: /src.c!\n','/src.c')
        for log in ('gap35 checks=70 failures=0\nPASSED: /src.c!\n',
                    'gap35 checks=71 failures=0\nPASSED: /other.c!\n',
                    'gap35 checks=71 failures=0\ncheck=1\nPASSED: /src.c!\n'):
            with self.assertRaises(ValueError): audit.check_log(log,'/src.c')
    def test_dts(self):
        audit.validate_pmp_dts('riscv,pmpregions = <0>;')
        for text in ('riscv,pmpregions = <16>;','riscv,pmpregions = <0>; riscv,pmpregions = <0>;',''):
            with self.assertRaises(ValueError): audit.validate_pmp_dts(text)
        self.assertNotIn('svadu',' '.join(audit.expected_command('spike','elf')))
    def test_exact_replay(self):
        result={'status':'PASS'}; files={'source':'a'*64}
        saved=dict(status='PASS',result=result,checked_files=files,read_only_validation=True)
        adapter.require_exact_replay(result,files,saved)
        for altered in ({},{'source':'b'*64},{**files,'extra':'c'*64}):
            with self.assertRaises(ValueError): adapter.require_exact_replay(result,altered,saved)
    def test_hooks(self):
        script=adapter.checked.SCRIPT
        delegate=lambda item,proof:'delegated'
        with patch.object(adapter.evidence,'precheck',delegate),patch.object(adapter,'_installed',False):
            adapter.install_hooks(); hook=adapter.evidence.precheck; adapter.install_hooks()
            self.assertIs(hook,adapter.evidence.precheck); self.assertEqual(script,adapter.checked.SCRIPT)
            self.assertEqual(hook({'name':'other'},None),'delegated')
            with patch.object(adapter,'sealed_precheck',return_value='sealed') as sealed:
                item={'name':adapter.NAME}; self.assertEqual(hook(item,None),'sealed')
                sealed.assert_called_once_with(item,None,delegate)

class RealTraceTest(unittest.TestCase):
    def setUp(self):
        if PREFLIGHT is None: self.skipTest('requires newly produced gap68 preflight')
        self.proof=json.loads((PREFLIGHT/'execution-proof.json').read_text())
        self.info=copy.deepcopy(self.proof['spike']['metadata']); self.sym=self.info['symbols']
        self.trace=(PREFLIGHT/'case.spike.stderr.log').read_text()
    def reject(self):
        with self.assertRaises(ValueError): audit.trace_check(self.trace,self.info)
    def replace_commit(self,pc,change):
        pattern=r'(?m)^core\s+0:\s+3\s+0x%016x\s+\(0x[0-9a-f]+\)[^\n]*$'%pc
        self.trace,n=re.subn(pattern,change,self.trace); self.assertGreater(n,0)
    def test_positive(self): self.assertEqual(audit.trace_check(self.trace,self.info),self.proof['trace'])
    def test_missing_trap(self):
        self.trace=re.sub(r'(?m)^.*exception trap_store_page_fault.*\n','',self.trace,count=1); self.reject()
    def test_extra_trap(self): self.trace+='core 0: exception trap_load_page_fault, epc 0x80000000\n'; self.reject()
    def test_wrong_cause(self): self.trace=self.trace.replace('trap_store_page_fault','trap_store_access_fault',1); self.reject()
    def test_wrong_privilege(self): self.trace=self.trace.replace('core   0: 3 ','core   0: 1 ',1); self.reject()
    def test_wrong_load(self):
        self.replace_commit(self.sym['gap68_load_a'],lambda m:m[0].replace('6811681168116811','6811681168116810')); self.reject()
    def test_handler_memory_before_clear(self):
        self.replace_commit(self.sym['gap68_handler_entry'],lambda m:m[0]+' mem 0x80001000'); self.reject()
    def test_wrong_handler_status(self):
        self.replace_commit(self.sym['gap68_handler_entry'],lambda m:re.sub(r'(x5\s+0x)[0-9a-f]+',r'\g<1>0000000000000000',m[0])); self.reject()
    def test_interposed_csr(self):
        self.replace_commit(self.sym['gap68_load_a']+4,lambda m:m[0].replace('(0x00c7c833)','(0x18002873)')); self.reject()
    def test_store_retired(self):
        self.trace+='core 0: 3 0x%016x (0x0105b023) mem 0x40000000 0x1\n'%self.sym['gap68_store_a']; self.reject()
    def test_wrong_trap_record(self):
        addr=self.sym['records']+16
        self.trace,n=re.subn(r'(mem 0x%016x 0x)0000000040000000'%addr,r'\g<1>0000000040000008',self.trace)
        self.assertEqual(n,1); self.reject()
    def test_wrong_data_read(self):
        pattern=r'(x[0-9]+\s+0x)6811681168116811( mem 0x%016x)'%(self.sym['gap68_pages']+12288)
        self.trace,n=re.subn(pattern,r'\g<1>6811681168116810\2',self.trace)
        self.assertGreater(n,0); self.reject()
    def test_missing_guard_reads(self):
        self.trace,n=re.subn(r'(?m)^.* mem 0x%016x\s*$\n'%self.sym['gap68_guard_hi'],'',self.trace)
        self.assertGreater(n,0); self.reject()
    def test_pmp(self): self.trace+='core 0: 3 0x80000000 (0x3a002573) x10 0x0\n'; self.reject()
    def test_budget(self): self.trace+='core 0: 3 0x80000000 (0x00000013)\n'*35001; self.reject()
    def test_metadata(self):
        obj=json.loads((PREFLIGHT/'spike.metadata.log').read_text())[0]
        blob=Path(self.proof['spike']['elf']).read_bytes()
        self.assertEqual(audit.metadata(obj,blob),self.info)
        altered=copy.deepcopy(obj)
        for row in altered['Symbols']:
            if row['Symbol']['Name']['Name']=='gap68_store_a': row['Symbol']['Value']+=4
        with self.assertRaises(ValueError): audit.metadata(altered,blob)

if __name__=='__main__':
    parser=argparse.ArgumentParser(add_help=False); parser.add_argument('--preflight',type=Path)
    args,rest=parser.parse_known_args(); PREFLIGHT=args.preflight
    unittest.main(argv=[sys.argv[0],*rest])
