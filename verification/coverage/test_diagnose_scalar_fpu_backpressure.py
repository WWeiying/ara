import unittest
from unittest.mock import patch
from types import SimpleNamespace
import diagnose_scalar_fpu_backpressure as d
import test_scalar_fpu_backpressure as fixture

TEXT='''    puts BP_PROBE_READY
    puts "BP_PROBE_ERROR $failure"
BP_PROBE_READY
Core Test *** SUCCESS ***
[ARA_CONTRACT] requests=0 responses=0 exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0
UVM_ERROR : 0
UVM_FATAL : 0
'''
class Tests(unittest.TestCase):
    def test_active_flush_still_rejected(self):
        fixture.FRAMES=fixture.frames('flush')
        with patch.object(d.p,'wave',SimpleNamespace(vcd=fixture.stub)),self.assertRaises(ValueError):
            d.wave_audit('fixture')
    def test_idle_flush_not_a_stall(self):
        fixture.FRAMES=fixture.frames('none')
        fixture.FRAMES[1][1]['flush_i']='1'
        with patch.object(d.p,'wave',SimpleNamespace(vcd=fixture.stub)):
            result=d.wave_audit('fixture')
        self.assertFalse(result['observed']);self.assertEqual(len(result['idle_ownerless_flush_times']),1)
    def test_real_echo_schema(self):self.assertEqual(d.stdout_audit(TEXT)['mmu_request_cycles'],0)
    def test_emitted_failure(self):
        for extra in ('BP_PROBE_ERROR actual failure','UVM_ERROR @ 10: actual error','UVM_FATAL bad',
                      'UVM_ERROR : 1','Error-[failure] real'):
            with self.subTest(extra=extra),self.assertRaises(ValueError):d.stdout_audit(TEXT+extra+'\n')
    def test_contracts(self):
        for text in (TEXT.replace('mmu_request_cycles=0 ','') ,TEXT.replace('req_stalled=0','req_stalled=1'),
                     TEXT.replace('mmu_request_cycles=0','mmu_request_cycles=1'),
                     TEXT.replace('outstanding=0','outstanding=0 outstanding=0'),
                     TEXT+TEXT.splitlines()[4]+'\n'):
            with self.assertRaises(ValueError):d.stdout_audit(text)
    def test_initialized_guard_reads(self):
        rows=[dict(mem_addr=hex(0x1000+8*i),mem_rmask='ff',mem_wmask='00',insn='00003083',rd='1',
                   rd_wdata=hex(v)) for i,v in enumerate((0x539af02c168be47d,0xce71049af28635bd))]
        self.assertEqual(len(d.guard_loads(rows,0x1000)),2)
        for field,value in (('rd_wdata','1'),('mem_rmask','0f'),('mem_wmask','ff'),('insn','00002083')):
            changed=[dict(r) for r in rows];changed[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):d.guard_loads(changed,0x1000)
        with self.assertRaises(ValueError):d.guard_loads(rows+rows[:1],0x1000)
    def test_unique_markers(self):
        for text in (TEXT+'BP_PROBE_READY\n',TEXT+'Core Test *** SUCCESS ***\n',
                     TEXT.replace('Core Test *** SUCCESS ***','Core Test *** FAIL ***')):
            with self.assertRaises(ValueError):d.stdout_audit(text)
if __name__=='__main__':unittest.main()
