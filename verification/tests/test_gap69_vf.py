"""Independent unit oracle plus in-memory mutations of the genuine Spike trace."""
import argparse
import copy
import csv
import io
import json
from pathlib import Path
import re
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'coverage'))
import audit_gap69_vf as audit

PREFLIGHT = None


class Oracle(unittest.TestCase):
    def test_encoding(self):
        for vd,name in ((9,'gap69_illegal_site'),(8,'gap69_legal_site')):
            word = (0b100100 << 26) | (1 << 25) | (16 << 20) | (0 << 15) | (0b101 << 12) | (vd << 7) | 0x57
            self.assertEqual(audit.WORDS[name],word)
        self.assertEqual(audit.WORDS['gap69_illegal_site'] ^ audit.WORDS['gap69_legal_site'],1 << 7)
        for bit in range(32):
            with self.assertRaises(ValueError): audit.check_vf(audit.WORDS['gap69_illegal_site'] ^ (1<<bit),9)

    def test_exact_products(self):
        self.assertEqual([audit.expected_half(8,i,True) for i in range(8)],
                         [0x4000,0xc000,0x4200,0xc500,0x3c00,0x4800,0x5000,0xb800])

    def test_tail_source_neighbors(self):
        for r in audit.REGS:
            for i in range(64):
                if r != 8 or i >= 8:
                    self.assertEqual(audit.expected_half(r,i),audit.expected_half(r,i,True))
        self.assertEqual(len(audit.image(0,False)),1184)
        self.assertEqual(audit.CHECKS,1815)

    def test_log_failures(self):
        valid = 'gap35 checks=1815 failures=0\nPASSED: /tmp/vgap69_vf_odd_vd.c!\n'
        audit.check_log(valid,'/tmp/vgap69_vf_odd_vd.c')
        for bad in (valid.replace('1815','1814'),valid.replace('failures=0','failures=1'),
                    valid+valid,valid+'check=1 got=1 want=0\n',valid.replace('/tmp/','/other/')):
            with self.assertRaises(ValueError): audit.check_log(bad,'/tmp/vgap69_vf_odd_vd.c')


class RuntimeFixtures(unittest.TestCase):
    @staticmethod
    def csv(rows):
        f = io.StringIO()
        writer = csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
        return f.getvalue()

    def setUp(self):
        self.info = dict(symbols={n:0x80010000+i*0x1000 for i,n in enumerate(audit.BUFFERS)})
        self.info['symbols'].update(gap69_illegal_site=0x80001000,gap69_legal_site=0x80001020)
        self.vector = []
        def row(event,seq,reg,word,**kw):
            r = dict(cycle=len(self.vector),event=event,arch_seq=seq,vid=seq,lane=0,source=0,
                insn='%08x'%word,use_vd=1,vd=reg,eew=1,vl=64,vstart=0,addr=0,be='00',
                wdata='0000000000000000',nr_lanes=4,vlen_bits=1024)
            r.update(kw); self.vector.append(r)
        row('config',0,0,0)
        for seq,reg in enumerate(audit.REGS):
            word = 0x0202d007 | reg<<7
            row('alloc',seq,reg,word)
            for chunk in range(4):
                for lane in range(4):
                    data = bytearray(8)
                    for slot in range(4):
                        i = chunk*16+((slot&1)*2+(slot>>1))*4+lane
                        data[2*slot:2*slot+2] = audit.expected_half(reg,i).to_bytes(2,'little')
                    row('write',seq,reg,word,lane=lane,addr=reg*4+chunk,be='ff',wdata=data[::-1].hex())
            row('done',seq,reg,word)
        word = audit.WORDS['gap69_legal_site']
        row('alloc',9,8,word,vl=8)
        for lane in range(4):
            data = bytearray(8)
            for slot,i in ((0,lane),(2,lane+4)):
                data[2*slot:2*slot+2] = audit.expected_half(8,i,True).to_bytes(2,'little')
            row('write',9,8,word,vl=8,lane=lane,addr=32,be='33',wdata=data[::-1].hex())
        row('done',9,8,word,vl=8)
        self.commit = []
        def commit(event,**kw):
            r = dict(cycle=len(self.commit),event=event,order=0,port=0,trans_id=3,pc='0000000000000000',
                     insn='00000000',rd=0,rd_wdata='0',mem_addr='0',mem_rmask='00',mem_wmask='00',mem_wdata='0',trap=0)
            r.update(kw); self.commit.append(r)
        commit('cvx_req',insn='%08x'%audit.WORDS['gap69_illegal_site'])
        commit('cvx_resp',trap=1)
        commit('retire',pc='%016x'%self.info['symbols']['gap69_legal_site'],insn='%08x'%word)
        memory = audit.expected_memory(self.info)
        for name in ('gap69_traps','gap69_state'):
            for i in range(0,audit.BUFFERS[name],8):
                addr = self.info['symbols'][name]+i
                value = int.from_bytes(bytes(memory[addr+j] for j in range(8)),'little')
                commit('retire',mem_addr='%016x'%addr,mem_wmask='ff',mem_wdata='%016x'%value)

    def check(self):
        return audit.vcs_vector(self.csv(self.vector),self.csv(self.commit),self.info)

    def test_positive(self):
        self.assertEqual(self.check()['trap_and_csr_bytes'],216)

    def test_every_enabled_byte_negative(self):
        for row in self.vector:
            if row['event'] != 'write': continue
            for byte in range(8):
                if not (int(row['be'],16)>>byte)&1: continue
                before = row['wdata']
                row['wdata'] = '%016x'%(int(before,16)^(1<<(byte*8)))
                with self.assertRaises(ValueError): self.check()
                row['wdata'] = before

    def test_backend_rejection_negatives(self):
        for field,value in (('insn','930054d7'),('vl',7),('eew',0),('vd',9),('vstart',1)):
            original = self.vector[-6][field]
            self.vector[-6][field] = value
            with self.assertRaises(ValueError): self.check()
            self.vector[-6][field] = original
        self.vector.pop()
        with self.assertRaises(ValueError): self.check()

    def test_trap_and_csr_negative(self):
        for row in self.commit[3:]:
            old = row['mem_wdata']; row['mem_wdata'] = '%016x'%(int(old,16)^1)
            with self.assertRaises(ValueError): self.check()
            row['mem_wdata'] = old

    def test_wrong_recovery_pc(self):
        self.commit[2]['pc'] = '80001000'
        with self.assertRaises(ValueError): self.check()

    def test_stdout_completion_negatives(self):
        source = '/tmp/vgap69_vf_odd_vd.c'
        log = ('gap35 checks=1815 failures=0\nPASSED: '+source+'!\n'
            'Core Test *** SUCCESS *** (tohost = 0)\nUVM_ERROR : 0\nUVM_FATAL : 0\n'
            '[ARA_CONTRACT] requests=30 responses=30 exceptions=1 mmu_request_cycles=0 protocol_errors=0 outstanding=0\n'
            '$finish at simulation time 123\n')
        audit.vcs_stdout(log,source)
        for old,new in (('tohost = 0','tohost = 1'),('exceptions=1','exceptions=0'),
                        ('responses=30','responses=29'),('protocol_errors=0','protocol_errors=1'),
                        ('UVM_ERROR : 0','UVM_ERROR : 1'),('$finish at','not finished at')):
            with self.assertRaises(ValueError): audit.vcs_stdout(log.replace(old,new),source)

    def test_hook_composition(self):
        import run_gap69_vf_checked_extension as wrapper
        import run_checked_extension as checked
        import coverage_evidence as evidence
        original_script = checked.SCRIPT
        original_precheck, original_row = evidence.precheck,evidence.Evidence.baseline_row
        original_hooks = wrapper._hooks
        sentinel = object()
        evidence.precheck = lambda item,proof: sentinel
        wrapper._hooks = None
        try:
            hook = wrapper.install_hooks()
            self.assertIs(hook,wrapper.install_hooks())
            self.assertEqual(checked.SCRIPT,original_script)
            self.assertIs(evidence.precheck(dict(name='rvv:other'),evidence.Evidence()),sentinel)
        finally:
            evidence.precheck = original_precheck
            evidence.Evidence.baseline_row = original_row
            wrapper._hooks = original_hooks


@unittest.skipUnless(PREFLIGHT,'requires --preflight real artifacts')
class RealTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = (PREFLIGHT/'case.spike.stderr.log').read_text()
        cls.info = json.loads((PREFLIGHT/'execution-proof.json').read_text())['spike']['metadata']

    def rejected(self, trace, info=None):
        with self.assertRaises(ValueError): audit.trace_check(trace,info or self.info)

    def replace(self, pattern, replacement, last=False):
        found = list(re.finditer(pattern,self.trace,re.M))
        self.assertTrue(found,'mutation not applied: '+pattern)
        match = found[-1] if last else found[0]
        return self.trace[:match.start()]+replacement(match)+self.trace[match.end():]

    def test_real_pass(self):
        self.assertEqual(audit.trace_check(self.trace,self.info)['illegal_word'],'0x930054d7')

    def test_wrong_illegal_word(self):
        self.rejected(self.trace.replace('(0x930054d7)','(0x93005457)'))

    def test_missing_trap(self):
        self.rejected(self.replace(r'^core\s+0:\s+exception trap_illegal_instruction[^\n]*\n',lambda m:''))

    def test_trap_epc(self):
        self.rejected(self.replace(r'(exception trap_illegal_instruction, epc )0x[0-9a-f]+',
                                  lambda m:m[1]+'0x0000000080000000'))

    def test_extra_trap(self):
        self.rejected(self.trace+'\ncore 0: exception trap_load_access_fault, epc 0x0000000080000000\n')

    def test_illegal_retired(self):
        pc = self.info['symbols']['gap69_illegal_site']
        self.rejected(self.trace+'\ncore 0: 3 0x%016x (0x930054d7)\n'%pc)

    def test_missing_recovery(self):
        self.rejected(self.trace.replace('(0x93005457)','(0x00000013)'))

    def test_bad_box(self):
        self.rejected(self.replace(r'(\bf0\s+)0x[0-9a-f]+',lambda m:m[1]+'0x0000000000004000',last=True))

    def test_wrong_eew_setup(self):
        self.rejected(self.replace(r'^(core\s+0: 3[^\n]*\(0x)([0-9a-f]+)(\)[^\n]* v7\s+0x[0-9a-f]+)',
                                  lambda m:m[1]+format(int(m[2],16) & ~(7<<12),'08x')+m[3]))

    def corrupt_store(self,address):
        self.rejected(self.replace(r'(\bmem 0x%016x )0x([0-9a-f]+)'%address,
                                  lambda m:m[1]+hex(int(m[2],16)^1),last=True))

    def test_trap_fields(self):
        base = self.info['symbols']['gap69_traps']
        for i in range(9):
            with self.subTest(field=i): self.corrupt_store(base+8*i)

    def test_live_csrs(self):
        base = self.info['symbols']['gap69_state']
        for i in range(18):
            with self.subTest(field=i): self.corrupt_store(base+8*i)

    def test_guards_and_tail(self):
        for n in ('gap69_rejected','gap69_recovered'):
            base = self.info['symbols'][n]
            for offset in (0,1182,16+64*2+8*2,16+2*64*2):
                with self.subTest(buffer=n,offset=offset): self.corrupt_store(base+offset)

    def test_wrong_metadata(self):
        info = copy.deepcopy(self.info)
        info['sites']['gap69_illegal_site']['word'] = '0x93005457'
        self.rejected(self.trace,info)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--preflight',type=Path)
    args,remaining = parser.parse_known_args()
    PREFLIGHT = args.preflight
    # Class decorators are evaluated before command-line parsing.
    RealTrace.__unittest_skip__ = PREFLIGHT is None
    unittest.main(argv=[sys.argv[0],*remaining])
