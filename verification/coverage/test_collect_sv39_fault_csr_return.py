"""Actual complete DUT fixture and CSR/return corruptions, no new simulation."""
import copy
import unittest
import collect_sv39_fault_alternating771_csr_return as q

class HandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre=q.life.read_bound(q.old.PRE/'preflight.json',q.old.PRE_SHA);cls.s=pre['symbols']
        cls.ref=q.prefix.terminal_prefix(q.old.p.build.parse_spike_commits(q.old.PRE/'spike.trace'),cls.s)
        cls.rows=q.old.common.read_csv((q.prefix.RUN/'commit_trace.csv').read_bytes(),q.old.common.COMMIT_FIELDS)
    def reject(self,rows):
        with self.assertRaises(ValueError):q.handler_replay(rows,self.ref,self.s)
    def test_actual(self):
        proof=q.handler_replay(self.rows,self.ref,self.s)
        self.assertEqual(len(proof),12);self.assertEqual([p['cause'] for p in proof],[13,15,9]*4)
    def test_wrong_mepc_source(self):
        rows=copy.deepcopy(self.rows)
        pcs=[r for r in rows if r['event']=='retire' and not int(r['trap'])]
        site=next(i for i,r in enumerate(pcs) if int(r['insn'],16)==0x34129073
          and int(r['pc'],16)>self.s['fault_handler'] and int(r['pc'],16)<self.s['fault_load_pc'])
        preceding=pcs[site-1];preceding['rd_wdata']='%x'%(int(preceding['rd_wdata'],16)+4);self.reject(rows)
    def test_cause_write(self):
        rows=copy.deepcopy(self.rows)
        r=next(r for r in rows if r['event']=='retire' and int(r['insn'],16)==0x34129073)
        r['insn']='34229073';self.reject(rows)
    def test_tval_write(self):
        rows=copy.deepcopy(self.rows)
        r=next(r for r in rows if r['event']=='retire' and int(r['insn'],16)==0x34129073)
        r['insn']='34329073';self.reject(rows)
    def test_early_write(self):
        rows=copy.deepcopy(self.rows)
        r=next(r for r in rows if r['event']=='retire' and int(r['pc'],16)==self.s['fault_handler'])
        r['insn']='34129073';self.reject(rows)
    def test_wrong_return(self):
        rows=copy.deepcopy(self.rows);ret=[r for r in rows if r['event']=='retire' and not int(r['trap'])]
        i=next(i for i,r in enumerate(ret) if int(r['insn'],16)==0x30200073 and int(r['pc'],16)==0x80002074)
        ret[i+1]['pc']='%x'%(self.s['fault_store_pc']+4);self.reject(rows)

if __name__=='__main__':unittest.main()
