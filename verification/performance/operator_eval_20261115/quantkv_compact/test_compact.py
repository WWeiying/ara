"""Host tests only; mock cycle values are never performance evidence."""
import csv
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from contract import HERE,OUT,ORDER,ancestor,captured
from driver import derive,roi_source
from check import numerical,roi
from prepare import audit_compare


def fixture(count=763904):
    lines=['PREFILL_CAP q4=1 rows=8 d=128 first_query=16 tokens=20 trials=4',
           f'QKC_INITIAL bytes={count} checked={count} first_fail=-1 state_errors=0']
    for t,m in enumerate(ORDER):
        lines += [f'PREFILL_BEGIN trial={t} shared={m}',
            f'QKC_BYTES trial={t} bytes={count} checked={count} first_fail=-1 state_errors=0',
            f'PREFILL_RESULT trial={t} shared={m} cycles=10 commands=4 values={20 if m else 74} '
            'fcsr=1 vcsr=5 vstart=0 checked=1024 first_fail=-1 guards=384 errors=0 hex='+'3f800000'*64]
    return '\n'.join(lines+['PREFILL_SUITE_PASS']),struct.pack('<40960f',*([1.0]*40960))


class CompactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=Path(tempfile.mkdtemp(prefix='operator_quantkv_compact_prepare_20261115_host_',dir=OUT))

    def test_complete_real_fixture(self):
        for kind,size in (('q4_0',763904),('q8_0',894976)):
            data=captured(kind)
            self.assertEqual(sum(map(len,data.values())),size)
            for role,blob in data.items(): self.assertEqual(blob,(ancestor(kind)/'inputs'/(role+'.bin')).read_bytes())

    def test_scoped_roi_and_initializer_unchanged(self):
        for kind in ('q4_0','q8_0'):
            old=(ancestor(kind)/'inputs/quant_main.c').read_text(); new=derive(old)
            self.assertEqual(roi_source(old),roi_source(new))
            first=old.index('    /* The first drain'); last=old.index('    uint64_t start = cycles();',first)
            self.assertIn(old[first:last],new)
            self.assertNotIn('extensions_quant_hash',new)
            self.assertEqual(new.count('quantkv_compare_bytes('),2)
            self.assertIn('2e-5f+2e-5f*fabsf(gold)',new)
            self.assertIn('errors += bits(y)!=bits(baseline[row][d])',new)
            with self.assertRaises(ValueError): derive(old.replace('EXT_QUANT_STATE trial=','EXT_CHANGED_STATE trial='))

    def test_every_byte_and_late_mutations(self):
        binary=self.out/'compare'
        r=subprocess.run(['gcc','-std=c11','-O2','-I'+str(HERE),str(HERE/'test_compare.c'),'-o',str(binary)],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
        self.assertEqual(r.returncode,0,r.stdout.decode())
        self.assertEqual(subprocess.run([binary],timeout=60).returncode,0)

    def test_integer_mask_instruction_audit(self):
        text=' vsetvli x0,x10,e8,m8,ta,ma\n vle8.v v8,(x10)\n vmseq.vv v0,v8,v16\n vfirst.m x10,v0\n'
        audit_compare(text)
        for instruction in ('mul x10,x11,x12','fence rw,rw','vfmul.vv v8,v8,v16','fadd.s f0,f1,f2','csrrwi x0,vstart,0'):
            with self.subTest(instruction=instruction),self.assertRaises(ValueError): audit_compare(text+' '+instruction+'\n')

    def test_compact_rejection(self):
        text,gold=fixture(); self.assertEqual(len(numerical(text,gold,'q4_0',763904)),4)
        for before,after in (('checked=763904','checked=763903'),('first_fail=-1','first_fail=0'),
            ('state_errors=0','state_errors=1'),('checked=1024','checked=64'),('guards=384','guards=128'),
            ('fcsr=1','fcsr=32'),('vcsr=5','vcsr=0'),('vstart=0','vstart=1'),('values=20','values=74'),
            ('errors=0','errors=1'),('3f800000','7fc00000'),('PREFILL_SUITE_PASS','')):
            with self.subTest(before=before),self.assertRaises(ValueError):
                numerical(text.replace(before,after,1),gold,'q4_0',763904)
        with self.assertRaises(ValueError): numerical(text,bytes(163840),'q4_0',763904)

    def test_roi_and_architecture_snapshots(self):
        r=dict(elf_ranges=dict(quantkv_compare_bytes=[200,240],qbs_native_execute_command=[300,304],printf_=[400,404]),
            roi_marker_pcs=[100,112],roi_read_pcs=[104,108])
        words={200:0x13,300:0x13,104:0xc00022f3,108:0xc0002373}
        text,gold=fixture(); rows=numerical(text,gold,'q4_0',763904); commits=[]
        def emit(pc,insn,value=0):
            commits.append(dict(cycle=len(commits)+1,event='retire',pc=f'{pc:x}',insn=f'{insn:x}',rd_wdata=f'{value:x}',trap='0'))
        def compare(fc,vc):
            emit(200,0x13)
            for i,(csr,value) in enumerate(((3,fc),(15,vc),(8,0))*2):
                emit(204+i*4,(csr<<20)|0x22f3,value)
        compare(0,0)
        for t in range(4):
            emit(100,0xc0002073); emit(104,words[104],100*t+10)
            for _ in range(4): emit(300,0x13)
            emit(108,words[108],100*t+20); emit(112,0xc0002073); compare(1,5)
        path=self.out/'mock-commit.csv'
        def write():
            with path.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(commits[0])); w.writeheader(); w.writerows(commits)
        write(); self.assertEqual(roi(path,r,rows,dict(words=words))['complete_byte_comparisons'],5)
        commits[4]['rd_wdata']='1'; write()
        with self.assertRaises(ValueError): roi(path,r,rows,dict(words=words))


if __name__=='__main__': unittest.main()
