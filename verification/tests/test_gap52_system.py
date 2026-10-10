"""Positive/negative gap52 audit tests. No simulator or sealed-file mutation."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import audit_gap52_system as audit
import run_gap52_system_checked_extension as adapter


def fixture():
    names = list(audit.WORDS) + ['gap52_remap_entry','gap52_payload_begin','gap52_payload_end',
                               'gap52_pages','gap52_guard_lo','gap52_guard_hi','records']
    sym = {n:0x80001000+16*i for i,n in enumerate(names)}
    sym.update(gap52_pages=0x80010000, gap52_guard_lo=0x8000ffc0,
               gap52_guard_hi=0x80015000, records=0x80018000)
    info = dict(symbols=sym, sites={n:dict(pc=hex(sym[n]),word=hex(w)) for n,w in audit.WORDS.items()})
    lines = []

    def commit(mode, pc, word=0x13, tail=''):
        lines.append('core 0: %d 0x%016x (0x%08x)%s' % (mode,pc,word,tail))

    commit(3,0x80000004,0xc20022f3,' x5 0x0000000000000000')
    commit(3,0x80000008,0xc21022f3,' x5 0x8000000000000000')
    commit(3,sym['gap52_payload_begin'])
    ecalls = []
    fences = []
    for phase,(base,step) in enumerate(((0x100000000,0x200000),(0x800000000,0x40000000))):
        for i in range(32):
            address = base+i*step+sym['gap52_pages']+3*4096-audit.PA+(32+phase*32+i)*8
            stamp = 0x5200000000000000+(phase+1)*65536+i
            for suffix,value in (('pc',base+i*step+sym['gap52_hop_pc']-audit.PA),
                                 ('load',audit.GUARD^(32+phase*32+i)),('store',stamp),('readback',stamp)):
                name = 'gap52_hop_'+suffix
                tail = ' x5 0x%016x'%value if suffix=='pc' else (
                    ' mem 0x%016x 0x%016x'%(address,value) if suffix=='store' else
                    ' x30 0x%016x mem 0x%016x'%(value,address))
                commit(1,base+i*step+sym[name]-audit.PA,audit.WORDS[name],tail)
        ecalls.append(base+31*step+sym['gap52_hop_ecall']-audit.PA)
        asid = 0x21+phase
        fences += [(base+16*step,0),(base+17*step,asid),(0,asid)]
        fences += [(base+i*step,asid) for i in range(32)]+[(0,0x23)]
    for i in range(3):
        for suffix,value in (('load',audit.GUARD^256 if i<2 else audit.REMAP[0]),
                             ('store',audit.REMAP[i]),('readback',audit.REMAP[i])):
            name = 'gap52_remap_'+suffix
            tail = ' mem 0x%016x 0x%016x'%(audit.DVA+2048,value) if suffix=='store' else \
                   ' x6 0x%016x mem 0x%016x'%(value,audit.DVA+2048)
            commit(1,sym[name],audit.WORDS[name],tail)
        ecalls.append(sym['gap52_remap_ecall'])
    fences += [(audit.DVA,0x21),(0,0x21)]
    for va,asid in fences:
        commit(3,0x80000010,0x293,' x5 0x%016x'%va)
        commit(3,0x80000014,0x313,' x6 0x%016x'%asid)
        commit(3,0x80000018,0x12628073)
    for i,pc in enumerate(ecalls):
        lines.append('core 0: exception trap_supervisor_ecall, epc 0x%016x'%pc)
        values = [0,32 if i<2 else 1,9,pc,0,0x800,8<<60|sym['gap52_pages']>>12|
                  (0x22 if i==1 else 0x21)<<44,0,1<<63,0,5,117,1]
        for j,v in enumerate(values):
            commit(3,0x80000020,0x233023,' mem 0x%016x 0x%016x'%(sym['records']+(i*13+j)*8,v))
    commit(3,sym['gap52_payload_end'])
    for p,page in enumerate(audit.expected_pages(sym['gap52_pages'])):
        for w,v in enumerate(page):
            commit(3,0x80000030,0x33283,' x5 0x%016x mem 0x%016x'%(v,sym['gap52_pages']+p*4096+w*8))
    for n,value in (('gap52_guard_lo',audit.GUARD),('gap52_guard_hi',audit.GUARD^audit.MASK64)):
        for w in range(8):
            commit(3,0x80000030,0x33283,' x5 0x%016x mem 0x%016x'%(value^w,sym[n]+w*8))
    return info,lines


class AuditTest(unittest.TestCase):
    def setUp(self): self.info,self.lines = fixture()
    def run_audit(self): return audit.trace_check('\n'.join(self.lines),self.info)
    def rejected(self):
        with self.assertRaises(ValueError): self.run_audit()

    def test_positive(self):
        r = self.run_audit()
        self.assertEqual((r['superpage_hops'],r['s_ecalls'],r['final_compared_words'],r['selective_sfences']),
                         (64,5,2576,74))

    def test_retirement_limit(self):
        self.lines += ['core 0: 3 0x80000000 (0x00000013)']*45001
        self.rejected()

    def test_missing_alias(self):
        self.lines.pop(next(i for i,l in enumerate(self.lines) if 'core 0: 1' in l))
        self.rejected()

    def test_wrong_privilege(self):
        i = next(i for i,l in enumerate(self.lines) if 'core 0: 1' in l)
        self.lines[i] = self.lines[i].replace('core 0: 1','core 0: 3')
        self.rejected()

    def test_duplicate_alias(self):
        i = next(i for i,l in enumerate(self.lines) if 'core 0: 1' in l)
        self.lines.insert(i,self.lines[i]); self.rejected()

    def test_wrong_loaded_guard(self):
        i = next(i for i,l in enumerate(self.lines) if 'x30 0x6b' in l)
        self.lines[i] = self.lines[i].replace('x30 0x6b','x30 0x5b'); self.rejected()

    def test_wrong_asid(self):
        i = next(i for i,l in enumerate(self.lines) if '(0x00000313) x6 0x0000000000000021' in l)
        self.lines[i] = self.lines[i].replace('0021','0022'); self.rejected()

    def test_missing_ecall(self):
        self.lines.pop(next(i for i,l in enumerate(self.lines) if 'exception' in l)); self.rejected()

    def test_extra_page_fault(self):
        self.lines.append('core 0: exception trap_load_page_fault, epc 0x80000000'); self.rejected()

    def test_wrong_saved_trap_word(self):
        address = self.info['symbols']['records']+16
        i = next(i for i,l in enumerate(self.lines) if 'mem 0x%016x '%address in l)
        self.lines[i] = self.lines[i][:-1]+'8'; self.rejected()

    def test_missing_full_page_read(self): self.lines.pop(); self.rejected()

    def test_corrupt_guard_read(self):
        self.lines[-1] = self.lines[-1].replace('x5 0x94','x5 0x84'); self.rejected()

    def test_pmp_csr_forbidden(self):
        self.lines.insert(0,'core 0: 3 0x80000000 (0x3a002573) x10 0x0'); self.rejected()

    def test_vector_payload_forbidden(self):
        self.lines.insert(4,'core 0: 3 0x80000000 (0x00007057)'); self.rejected()

    def test_compressed_fp_forbidden(self):
        self.lines.insert(4,'core 0: 3 0x80000000 (0x00002000)'); self.rejected()

    def test_foreign_s_store(self):
        self.lines.insert(4,'core 0: 1 0x80000ff0 (0x00133023) mem 0x80010000 0x1')
        self.rejected()

    def test_overflush_not_substituted(self):
        self.lines = [l.replace('(0x12628073)','(0x12000073)') for l in self.lines]
        self.rejected()

    def test_dts_and_command(self):
        audit.validate_pmp_dts('riscv,pmpregions = <0>;')
        self.assertIn('--pmpregions=0',audit.expected_command('spike','elf'))
        with self.assertRaises(ValueError): audit.validate_pmp_dts('riscv,pmpregions = <16>;')

    def test_oracle_edges(self):
        p = audit.expected_pages(0x80040000)
        self.assertEqual(p[0][4],0x20010401)
        self.assertEqual(p[1][511],0x20010801)
        self.assertEqual(p[2][0],0x20010cc7)
        self.assertEqual(p[3][31],audit.GUARD^31)
        self.assertEqual(p[3][32],0x5200000000010000)
        self.assertEqual(p[3][95],0x520000000002001f)
        self.assertEqual(p[3][96],audit.GUARD^96)
        self.assertEqual(p[3][256],audit.REMAP[2])
        self.assertEqual(p[4][256],audit.REMAP[1])

    def test_log_binding(self):
        audit.check_log('gap35 checks=110 failures=0\nPASSED: /src.c!\n','/src.c')
        with self.assertRaises(ValueError):
            audit.check_log('gap35 checks=109 failures=0\nPASSED: /src.c!\n','/src.c')


class SealTest(unittest.TestCase):
    def setUp(self):
        self.result = dict(status='PASS')
        self.files = {'source':'a'*64,'tool':'b'*64}
        self.saved = dict(status='PASS',read_only_validation=True,result=copy.deepcopy(self.result),
                          checked_files=dict(self.files))
    def check(self): adapter.require_exact_replay(self.result,self.files,self.saved)
    def test_positive(self): self.check()
    def test_missing(self):
        self.files.pop('tool')
        with self.assertRaises(ValueError): self.check()
    def test_extra(self):
        self.files['extra'] = 'c'*64
        with self.assertRaises(ValueError): self.check()
    def test_drift(self):
        self.files['source'] = 'c'*64
        with self.assertRaises(ValueError): self.check()
    def test_result(self):
        self.result['extra'] = True
        with self.assertRaises(ValueError): self.check()
    def test_chain(self):
        script = adapter.checked.SCRIPT
        delegate = lambda item,proof:'delegated'
        with patch.object(adapter.evidence,'precheck',delegate),patch.object(adapter,'_installed',False):
            adapter.install_hooks(); hook = adapter.evidence.precheck; adapter.install_hooks()
            self.assertIs(adapter.evidence.precheck,hook)
            self.assertEqual(adapter.checked.SCRIPT,script)
            self.assertEqual(hook({'name':'other'},None),'delegated')
            with patch.object(adapter,'sealed_precheck',return_value='sealed') as sealed:
                item = {'name':adapter.NAME}
                self.assertEqual(hook(item,None),'sealed')
                sealed.assert_called_once_with(item,None,delegate)


if __name__ == '__main__': unittest.main()
