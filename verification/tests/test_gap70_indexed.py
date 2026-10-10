"""Gap70 positive/negative audit and isolated hook tests; no simulator."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'coverage'))
import audit_gap70_indexed as audit
import run_gap70_indexed_checked_extension as adapter


def fixture():
    sym = {n:0x80001000+16*i for i,n in enumerate(audit.WORDS)}
    sym.update(gap70_s_entry=0x80002000,gap70_m_resume=0x80002010,
        gap70_checks_begin=0x80003000,gap70_checks_end=0x80003010,
        gap70_pages=0x80010000,gap70_guard_lo=0x8000ffc0,gap70_guard_hi=0x80014000,
        seed=0x80015000,fault=0x80015400,result=0x80015800,records=0x80016000,
        post=0x80016100,marker=0x80016200)
    info = dict(symbols=sym,sites={n:dict(pc=hex(sym[n]),word=hex(w)) for n,w in audit.WORDS.items()})
    lines = []

    def commit(mode,pc,word=0x13,tail=''):
        lines.append('core 0: %d 0x%016x (0x%08x)%s'%(mode,pc,word,tail))

    def store(mode,address,value):
        commit(mode,0x80005000,0x233023,' mem 0x%016x 0x%016x'%(address,value))

    def record(i):
        p = sym['gap70_pages']
        values = [9 if i else 13,sym['gap70_ecall' if i else 'gap70_indexed_load'],
            0 if i else audit.VA+audit.OFFSETS[0],0x800,(8<<60)|((p+4096)>>12),
            8,16,0,117,5,i,((p>>12<<10)|0xc7) if i else 0]
        for j,v in enumerate(values): store(3,sym['records']+(i*12+j)*8,v)

    seed,result = audit.expected_vectors()
    commit(1,sym['gap70_s_entry'])
    lines.append('core 0: 0x%016x (0x0f03e407) vloxei32.v'%sym['gap70_indexed_load'])
    commit(1,sym['gap70_indexed_load'],audit.WORDS['gap70_indexed_load'],
           ' e32 m1 l8 c8_vstart 0x0000000000000000')
    lines.append('core 0: exception trap_load_page_fault, epc 0x%016x'%sym['gap70_indexed_load'])
    record(0)
    for r in range(6):
        for w,v in enumerate(seed[r]): store(3,sym['fault']+64+r*128+w*4,v)
    commit(3,sym['gap70_repair_store'],audit.WORDS['gap70_repair_store'],
        ' mem 0x%016x 0x%016x'%(sym['gap70_pages']+12288,(sym['gap70_pages']>>12<<10)|0xc7))
    commit(3,0x80005004,0xe13,' x28 0x0000000040000000')
    commit(3,sym['gap70_repair_sfence'],audit.WORDS['gap70_repair_sfence'])
    commit(3,sym['gap70_retry_mret'],audit.WORDS['gap70_retry_mret'])
    lines.append('core 0: 0x%016x (0x0f03e407) vloxei32.v'%sym['gap70_indexed_load'])
    vector = sum(v<<(32*w) for w,v in enumerate(result[1]))
    tail = ' e32 m1 l8 v8 0x%0256x'%vector
    tail += ''.join(' mem 0x%016x'%(audit.VA+a) for a in audit.OFFSETS)
    commit(1,sym['gap70_indexed_load'],audit.WORDS['gap70_indexed_load'],tail)
    for i,v in enumerate((8,16,0,117,5)): store(1,sym['post']+i*8,v)
    commit(1,sym['gap70_younger_store'],audit.WORDS['gap70_younger_store'],
        ' mem 0x%016x 0x0000000000000001'%sym['marker'])
    for r in range(6):
        for w,v in enumerate(result[r]): store(1,sym['result']+64+r*128+w*4,v)
    lines.append('core 0: exception trap_supervisor_ecall, epc 0x%016x'%sym['gap70_ecall'])
    record(1)
    commit(3,sym['gap70_m_resume'])
    commit(3,sym['gap70_checks_begin'])
    for a,(_,v) in audit.final_memory(sym).items():
        commit(3,0x80005008,0x33283,' x5 0x%016x mem 0x%016x'%(v,a))
    commit(3,sym['gap70_checks_end'])
    return info,lines


class AuditTest(unittest.TestCase):
    def setUp(self): self.info,self.lines = fixture()
    def run_audit(self): return audit.trace_check('\n'.join(self.lines),self.info)
    def rejected(self):
        with self.assertRaises(ValueError): self.run_audit()
    def replace_line(self,needle,before,after):
        i = next(i for i,l in enumerate(self.lines) if needle in l)
        self.lines[i] = self.lines[i].replace(before,after)
    def test_positive(self):
        r = self.run_audit()
        self.assertEqual((r['load_page_faults'],r['indexed_commits'],r['final_compared_words']),(1,1,2752))
    def test_wrong_cause(self):
        self.lines = [l.replace('trap_load_page_fault','trap_load_access_fault') for l in self.lines]
        self.rejected()
    def test_wrong_fault_epc(self):
        self.replace_line('trap_load_page_fault','epc 0x','epc 0x1'); self.rejected()
    def test_missing_retry_attempt(self):
        i = max(i for i,l in enumerate(self.lines) if 'vloxei32.v' in l)
        self.lines.pop(i); self.rejected()
    def test_modified_mepc(self):
        self.lines.insert(5,'core 0: 3 0x80005000 (0x34129073)'); self.rejected()
    def test_partial_memory_side_effect(self):
        self.replace_line('l8 c8_vstart','c8_vstart 0x0000000000000000',
                          'c8_vstart 0x0000000000000000 mem 0x40000300'); self.rejected()
    def test_missing_partial_log(self):
        self.lines = [l for l in self.lines if 'l8 c8_vstart' not in l]; self.rejected()
    def test_missing_repair(self):
        self.lines = [l for l in self.lines if '(0x006e3023)' not in l]; self.rejected()
    def test_wrong_repair(self):
        self.replace_line('(0x006e3023)','0x00000000200040c7','0x00000000200040c6'); self.rejected()
    def test_overflush(self):
        self.replace_line('(0x120e0073)','0x120e0073','0x12000073'); self.rejected()
    def test_wrong_sfence_va(self):
        self.replace_line('x28','40000000','40001000'); self.rejected()
    def test_wrong_retry_privilege(self):
        self.replace_line('(0x30200073)','core 0: 3','core 0: 1'); self.rejected()
    def test_wrong_vector_tail(self):
        self.replace_line('l8 v8 ','6c71001f','6c71001e'); self.rejected()
    def test_wrong_index_address(self):
        self.replace_line('l8 v8 ','40000300','40000304'); self.rejected()
    def test_duplicate_indexed(self):
        i = next(i for i,l in enumerate(self.lines) if ' e32 m1 l8 ' in l)
        self.lines.insert(i,self.lines[i]); self.rejected()
    def test_wrong_saved_vstart(self):
        a = self.info['symbols']['records']+7*8
        self.replace_line('mem 0x%016x '%a,'0x0000000000000000','0x0000000000000001'); self.rejected()
    def test_wrong_saved_marker(self):
        a = self.info['symbols']['records']+10*8
        self.replace_line('mem 0x%016x '%a,'0x0000000000000000','0x0000000000000001'); self.rejected()
    def test_pre_repair_vector_changed(self):
        a = self.info['symbols']['fault']+64
        self.replace_line('mem 0x%016x '%a,'6c700000','6c700001'); self.rejected()
    def test_missing_snapshot_word(self):
        a = self.info['symbols']['fault']+64
        self.lines = [l for l in self.lines if 'mem 0x%016x '%a not in l]; self.rejected()
    def test_foreign_data_store(self):
        self.lines.insert(1,'core 0: 1 0x80005000 (0x233023) mem 0x80010000 0x1'); self.rejected()
    def test_early_younger_store(self):
        i = next(i for i,l in enumerate(self.lines) if '(0x0062b023)' in l)
        self.lines.insert(1,self.lines.pop(i)); self.rejected()
    def test_missing_guard_comparison(self):
        self.lines.pop(-2); self.rejected()
    def test_wrong_final_data(self):
        self.replace_line('x5 0x9170000191700000','91700000','91700001'); self.rejected()
    def test_pmp_access(self):
        self.lines.insert(0,'core 0: 3 0x80000000 (0x3a002573) x10 0x0'); self.rejected()
    def test_retirement_limit(self):
        self.lines += ['core 0: 3 0x80000000 (0x00000013)']*35001; self.rejected()
    def test_extra_hart(self):
        self.lines.append('core 1: 3 0x80000000 (0x00000013)'); self.rejected()
    def test_check_log(self):
        audit.check_log('gap35 checks=85 failures=0\nPASSED: /src.c!\n','/src.c')
        with self.assertRaises(ValueError): audit.check_log('gap35 checks=84 failures=0\n','/src.c')
    def test_configuration(self):
        audit.validate_pmp_dts('riscv,pmpregions = <0>;')
        with self.assertRaises(ValueError): audit.validate_pmp_dts('riscv,pmpregions = <16>;')


class HookTest(unittest.TestCase):
    def setUp(self):
        self.result = dict(status='PASS'); self.files = {'source':'a'*64,'tool':'b'*64}
        self.saved = dict(status='PASS',read_only_validation=True,result=copy.deepcopy(self.result),
                          checked_files=dict(self.files))
    def test_replay(self): adapter.require_exact_replay(self.result,self.files,self.saved)
    def test_missing_pin(self):
        self.files.pop('tool')
        with self.assertRaises(ValueError): adapter.require_exact_replay(self.result,self.files,self.saved)
    def test_hash_drift(self):
        self.files['tool']='c'*64
        with self.assertRaises(ValueError): adapter.require_exact_replay(self.result,self.files,self.saved)
    def test_result_drift(self):
        self.result['extra']=True
        with self.assertRaises(ValueError): adapter.require_exact_replay(self.result,self.files,self.saved)
    def test_chain_preserves_checked_script(self):
        script = adapter.checked.SCRIPT
        delegate = lambda item,proof:'delegated'
        with patch.object(adapter.evidence,'precheck',delegate),patch.object(adapter,'_installed',False):
            adapter.install_hooks(); hook = adapter.evidence.precheck; adapter.install_hooks()
            self.assertIs(adapter.evidence.precheck,hook)
            self.assertEqual(adapter.checked.SCRIPT,script)
            self.assertEqual(hook({'name':'other'},None),'delegated')
            with patch.object(adapter,'sealed_precheck',return_value='sealed') as sealed:
                item = {'name':adapter.NAME}; self.assertEqual(hook(item,None),'sealed')
                sealed.assert_called_once_with(item,None,delegate)


if __name__=='__main__': unittest.main()
