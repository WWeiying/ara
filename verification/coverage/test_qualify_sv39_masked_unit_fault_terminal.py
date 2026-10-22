"""Strict terminal plan/oracle negative tests; no EDA or DUT artifacts required."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import qualify_sv39_masked_unit_fault_terminal as q
from test_build_sv39_masked_unit_fault_preflight import fixture


def oracle_rows(symbols):
    memory=q.p.expected_memory(symbols)
    for phase in range(2):
        memory.update({symbols['records']+phase*96+24+i:b for i,b in enumerate((0x800).to_bytes(8,'little'))})
    rows=[]
    for address,value in memory.items():
        rows.append(dict(event='retire',trap='0',insn='00028003',rd='1',rd_wdata=hex(value),
            mem_addr=hex(address),mem_rmask=hex(1<<(address&7)),mem_wmask='0',mem_wdata='0',order=str(len(rows))))
    rows.append(dict(event='retire',trap='0',insn='0052b023',rd='0',rd_wdata='0',
        mem_addr=hex(symbols['tohost']),mem_rmask='0',mem_wmask='ff',mem_wdata='1',order=str(len(rows))))
    return rows


def c_row(pc,word,order=0,**kw):
    obj=dict(event='retire',pc=hex(pc),insn=hex(word),trap='0',order=str(order),
             rd='0',rd_wdata='0',mem_addr='0',mem_rmask='0',mem_wmask='0',mem_wdata='0')
    obj.update(kw);return obj


class QualifierTests(unittest.TestCase):
    def test_log_zero_summary(self):
        q.log_gate('Core Test *** SUCCESS ***\nUVM_ERROR : 0\nUVM_FATAL : 0\n')

    def test_log_errors(self):
        for suffix in ('UVM_ERROR foo','UVM_FATAL : 1','UVM_ERROR : 2','Error: failure','[ARA_CONTRACT_ERROR] fail'):
            with self.assertRaises(ValueError):q.log_gate('Core Test *** SUCCESS ***\n'+suffix)

    def test_log_duplicate_success(self):
        with self.assertRaises(ValueError):q.log_gate('Core Test *** SUCCESS ***'*2)

    def test_gold_complete(self):
        s=fixture();self.assertEqual(q.observed_gold(oracle_rows(s),s)['independent_gold_bytes'],19460)

    def test_gold_wrong_mask_tail_guard(self):
        s=fixture()
        for address in (s['result']+64+4*128,s['result']+64+128+127,s['smuf_guard_hi']+12):
            rows=oracle_rows(s)
            row=next(r for r in rows if int(r['mem_addr'],16)==address)
            row['rd_wdata']=hex(int(row['rd_wdata'],16)^1)
            with self.assertRaisesRegex(ValueError,'mismatch'):q.observed_gold(rows,s)

    def test_gold_status(self):
        s=fixture();rows=oracle_rows(s)
        row=next(r for r in rows if int(r['mem_addr'],16)==s['records']+25)
        row['rd_wdata']='0x18'
        with self.assertRaisesRegex(ValueError,'privilege'):q.observed_gold(rows,s)

    def test_gold_partial_readback(self):
        s=fixture();rows=oracle_rows(s)
        rows=[r for r in rows if int(r['mem_addr'],16)!=s['smuf_pages']+53]
        with self.assertRaises(ValueError):q.observed_gold(rows,s)

    def test_failure_tohost(self):
        s=fixture();rows=oracle_rows(s);rows[-1]['mem_wdata']='3'
        with self.assertRaises(ValueError):q.observed_gold(rows,s)

    def test_reference_partial_is_explicit(self):
        s=fixture()
        def c(pc,word,mem=(),gpr=None):return SimpleNamespace(pc=pc,instruction=word,memory_accesses=mem,
            gpr_writes=gpr or {},fpr_writes={},vector_writes={})
        commits=[c(0x80000000,0x13),c(s['smuf_masked_load'],q.p.WORDS['smuf_masked_load']),
                 c(0x80002000,0x23,((s['tohost'],1),))]
        self.assertEqual(q.reference_prefix(commits,s)[1],1)
        commits[1].gpr_writes={1:4}
        with self.assertRaises(ValueError):q.reference_prefix(commits,s)

    def test_compressed_store_exact(self):
        s=fixture();pc=0x80000000;word=0xe406
        reference=[SimpleNamespace(pc=pc,instruction=0x13,gpr_writes={2:0x801ffff0,1:0x1234},memory_accesses=()),
                   SimpleNamespace(pc=pc+4,instruction=word,gpr_writes={},memory_accesses=((0x801ffff8,0x1234),))]
        rows=[c_row(pc,0x13),c_row(pc+4,word,1,mem_addr='801ffff8',mem_wmask='ff',mem_wdata='1234'),
              c_row(s['smuf_ecall'],0x73,2,trap='1')]
        self.assertEqual(q.compressed_audit(rows,reference,-1,s)['compressed_stores'],1)
        rows[1]['mem_wmask']='f'
        with self.assertRaisesRegex(ValueError,'store'):q.compressed_audit(rows,reference,-1,s)

    def test_unknown_compressed(self):
        s=fixture();ref=[SimpleNamespace(pc=0x80000000,instruction=1,gpr_writes={},memory_accesses=())]
        rows=[c_row(0x80000000,1,mem_wmask='ff'),c_row(s['smuf_ecall'],0x73,1,trap='1')]
        with self.assertRaisesRegex(ValueError,'Unknown compressed'):q.compressed_audit(rows,ref,-1,s)

    def test_active_collect_rejected(self):
        plan=dict(status=q.STATUS,run=str(q.life.OUT/'never-run'),prepared='/missing',prepared_seal='0'*64,pins={})
        with patch.object(q.life,'read_bound',side_effect=[plan,{}]),patch.object(q.life,'check'),\
             patch.object(Path,'read_bytes',side_effect=AssertionError('missing file must not be read')):
            with self.assertRaises(ValueError):q.collect(Path('/plan'),'0'*64,q.life.OUT/'never-output')


if __name__=='__main__':unittest.main()
