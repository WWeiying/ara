"""Independent finite oracle and strict software proof negative tests."""
import tempfile
from pathlib import Path
import subprocess
import unittest

import build_sv39_masked_unit_fault_preflight as p


def fixture():
    s = {name:0x80010000+i*0x1000 for i,name in enumerate(p.SYMBOLS)}
    s['smuf_pages']=0x80050000
    s['smuf_guard_lo']=s['smuf_pages']-64
    s['smuf_guard_hi']=s['smuf_pages']+16384
    for i,name in enumerate(('seed','fault','result','records','post','trap_count','marker',
                             'repair_pte','completed','g75_result','num_failed')):
        s[name]=0x80100000+i*0x1000
    return s


def synthetic(s):
    lines = []
    def row(name, tail='', mode=3):
        lines.append('core 0: %d 0x%016x (0x%08x)%s' % (mode,s[name],p.WORDS[name],tail))
    row('smuf_masked_load',' e8 m1 l17 c8_vstart 0x0000',1)
    lines.append('exception trap_load_page_fault, epc 0x%016x' % s['smuf_masked_load'])
    row('smuf_repair_store',' mem 0x%016x 0x%016x' %
        (s['smuf_pages']+12288,(s['smuf_pages']>>12<<10)|0xc7))
    lines.append('core 0: 3 0x0000000080002000 (0x40000e37) x28 0x0000000040000000')
    row('smuf_repair_sfence')
    row('smuf_retry_mret')
    for name,r,vr,base in (('smuf_masked_load',1,8,0x40000300),('smuf_recovery_load',2,9,0x40000340)):
        want=sum(p.word(r,w,True)<<(32*w) for w in range(32))
        tail=' e8 m1 l17 v%d 0x%x' % (vr,want)
        tail+=''.join(' mem 0x%016x' % (base+i) for i in range(17) if r==2 or i%2==0)
        row(name,tail,1)
    row('smuf_younger_store',' mem 0x%016x 0x1' % s['marker'],1)
    lines.append('exception trap_supervisor_ecall, epc 0x%016x' % s['smuf_ecall'])
    memory=p.expected_memory(s)
    for phase in range(2):
        for i,b in enumerate((0x800).to_bytes(8,'little')):
            memory[s['records']+phase*96+24+i]=b
    for a,v in memory.items():
        lines.append('core 0: 3 0x0000000080002000 (0x00528023) mem 0x%016x 0x%x' % (a,v))
    lines.append('core 0: 3 0x0000000080002000 (0x0052b023) mem 0x%016x 0x1' % s['tohost'])
    return '\n'.join(lines)+'\n'


class OracleTests(unittest.TestCase):
    def test_host_complete(self):
        with tempfile.TemporaryDirectory() as d:
            binary = Path(d)/'oracle'
            subprocess.run(['/usr/bin/cc', '-DSMUF_ORACLE_HOST', str(p.APP), '-o', str(binary)], check=True)
            text = subprocess.check_output([str(binary)], text=True)
            self.assertEqual(p.check_host(text)['rows'], 1728)
            with self.assertRaises(ValueError):
                p.check_host(text.replace('55555555', '55555554', 1))
            with self.assertRaises(ValueError):
                p.check_host(text+'R 0 0 00000000 00000000\n')

    def test_mask_tail_gold(self):
        initial = b''.join(p.word(1,w).to_bytes(4,'little') for w in range(32))
        result = b''.join(p.word(1,w,True).to_bytes(4,'little') for w in range(32))
        for i in range(128):
            want = initial[i]
            if i < 17 and i % 2 == 0:
                offset = 768+i
                want = ((0x91700000 ^ (offset//4)) >> (8*(offset % 4))) & 255
            self.assertEqual(result[i],want)
        for r in (0,3,4,5):
            self.assertEqual([p.word(r,w,True) for w in range(32)], [p.word(r,w) for w in range(32)])

    def test_bad_coordinate(self):
        for r,w in ((-1,0),(6,0),(0,32)):
            with self.assertRaises(ValueError):
                p.word(r,w)

    def test_fixture_scope(self):
        text = p.APP.read_text()
        self.assertIn('smuf_masked_load: vle8.v v8, (t2), v0.t',text)
        self.assertIn('smuf_recovery_load: vle8.v v9, (t2)',text)
        self.assertNotIn('vloxei',text)
        self.assertNotIn('\\\\n',text)
        self.assertIn('op(7) op(8) op(9) op(15) op(0) op(17)',text)

    def test_explicit_seal_rejected(self):
        with self.assertRaises(ValueError):
            p.bind_baseline(p.OUT/'gap110-offline-admitted-734-parent-20261006-01','0'*64)

    def test_final_memory_covers_tables_snapshots(self):
        s=fixture()
        memory=p.expected_memory(s)
        self.assertTrue(all(s['smuf_pages']+i in memory for i in range(16384)))
        self.assertTrue(all(s['result']+i in memory for i in range(896)))
        self.assertEqual(memory[s['result']+64+4*128],0x55)
        s['smuf_guard_hi']+=8
        with self.assertRaises(ValueError):
            p.expected_memory(s)

    def test_trace_positive(self):
        s=fixture()
        self.assertEqual(p.validate_trace(synthetic(s),s)['checks'],85)

    def test_trace_wrong_destination(self):
        s=fixture(); text=synthetic(s)
        with self.assertRaisesRegex(ValueError,'destination'):
            p.validate_trace(text.replace('v8 0x','v8 0xf',1),s)

    def test_trace_wrong_opcode(self):
        s=fixture(); text=synthetic(s)
        with self.assertRaisesRegex(ValueError,'opcode'):
            p.validate_trace(text.replace('0x00038407','0x02038407',1),s)

    def test_trace_wrong_trap(self):
        s=fixture()
        with self.assertRaisesRegex(ValueError,'trap ledger'):
            p.validate_trace(synthetic(s).replace('trap_load_page_fault','trap_load_access_fault'),s)

    def test_trace_missing_byte(self):
        s=fixture(); text=synthetic(s)
        target='mem 0x%016x' % (s['result']+895)
        text='\n'.join(l for l in text.splitlines() if target not in l)
        with self.assertRaisesRegex(ValueError,'oracle mismatch'):
            p.validate_trace(text,s)

    def test_trace_wrong_mask_address(self):
        s=fixture(); text=synthetic(s)
        with self.assertRaisesRegex(ValueError,'masked memory'):
            p.validate_trace(text.replace('mem 0x0000000040000302','mem 0x0000000040000301'),s)

    def test_trace_original_epc_changed(self):
        s=fixture(); text=synthetic(s)
        i=text.index('exception trap_load_page_fault')
        text=text[:i]+'core 0: 3 0x0000000080002000 (0x34129073)\n'+text[i:]
        with self.assertRaisesRegex(ValueError,'EPC overwritten'):
            p.validate_trace(text,s)

    def test_unknown_compressed_store_rejected(self):
        s=fixture(); text=synthetic(s)
        with self.assertRaisesRegex(ValueError,'Unknown compressed'):
            p.validate_trace(text+'core 0: 3 0x0000000080002000 (0x0001) mem 0x0000000080003000 0x0\n',s)


if __name__ == '__main__':
    unittest.main()
