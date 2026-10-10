import copy
import csv
from pathlib import Path
import unittest
from unittest.mock import patch

import collect_itlb_ppn_aba_v2 as v2

old=v2.old
RUN=old.pre.OUT/'itlb-ppn-aba-old-image792-parent-20261008-01'
PRE=old.pre.OUT/'itlb-ppn-aba-preflight792-agent-20261008-01'
PRE_SHA='8c7d34e4009f76b0e415a6900793d4e359a3fb7f118bbd96d66cd61112fbcb85'
CALLS=[]


def call_private_marker(prepared,seal,output):
    original.markers((RUN/'console.log').read_text())
    CALLS.append(True)


class ActualCSRContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=(RUN/'console.log').read_text()
        with (RUN/'commit_trace.csv').open() as f:cls.rows=list(csv.DictReader(f))
        with (RUN/'vector_trace.csv').open() as f:cls.vector=list(csv.DictReader(f))
        cls.pre=old.life.read_bound(PRE/'preflight.json',PRE_SHA)
        cls.ref=old.pre.reference(PRE/'spike.trace',cls.pre['symbols'])

    def gate(self,text=None,rows=None,vector=None):
        return v2.console_gate(self.text if text is None else text,
            self.rows if rows is None else rows,self.ref,self.vector if vector is None else vector)

    def test_actual_sixCSR_complete_contract(self):
        audit=self.gate()
        self.assertEqual(audit['summary']['requests'],6)
        self.assertEqual(len(audit['lifecycle']['records']),6)
        self.assertEqual([r['word'] for r in audit['lifecycle']['records']],v2.WORDS)
        self.assertTrue(audit['zero_vector_writes'])
        self.assertFalse(audit['UVM_final_summary_claimed'])

    def test_original_zero_contract_still_rejects(self):
        with self.assertRaisesRegex(ValueError,'Zero-vector contract'):
            old.original.markers(self.text)

    def test_actual_full_scalar_and48_traps_unchanged(self):
        scalar=old.pre.architecture.spike_trace.compare_commit_prefix(PRE/'spike.trace',RUN/'commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        old.original.exact_scalar(scalar,self.pre['counts'])
        self.assertEqual(scalar['ara_trap_events'],48)
        self.assertEqual(scalar['matched_instructions'],37340)
        self.assertIsNone(scalar['mismatch'])
        self.assertEqual(scalar['skipped_unobservable_register_values'],0)

    def test_zero_wrong_counts_error_stall_or_extra_summary(self):
        line=next(x for x in self.text.splitlines() if x.startswith('[ARA_CONTRACT]'))
        for bad in (line.replace('requests=6','requests=0'),line.replace('responses=6','responses=7'),
                    line.replace('exceptions=0','exceptions=1'),line.replace('mmu_request_cycles=0','mmu_request_cycles=1'),
                    line.replace('protocol_errors=0','protocol_errors=1'),line.replace('outstanding=0','outstanding=1'),
                    line.replace('req_stalled=0','req_stalled=1'),line.replace('resp_stalled=0','resp_stalled=1'),
                    line+' foreign=0',line+'\n'+line):
            with self.assertRaises(ValueError):self.gate(self.text.replace(line,bad))

    def test_missing_req_resp_or_live_TID_replay(self):
        for event in ('cvx_req','cvx_resp','arch_start'):
            rows=copy.deepcopy(self.rows);i=next(i for i,r in enumerate(rows) if r['event']==event)
            rows.pop(i)
            with self.assertRaises(ValueError):self.gate(rows=rows)
        rows=copy.deepcopy(self.rows);i=next(i for i,r in enumerate(rows) if r['event']=='cvx_req')
        rows.insert(i,dict(rows[i]))
        with self.assertRaises(ValueError):self.gate(rows=rows)

    def test_request_instruction_exception_or_memory_sideeffect(self):
        for key,value in [('insn','00000057'),('trap','1'),('mem_wmask','ff')]:
            rows=copy.deepcopy(self.rows);row=next(r for r in rows if r['event']=='cvx_req');row[key]=value
            with self.assertRaises(ValueError):self.gate(rows=rows)

    def test_wrong_CSR_retire_PC_value_or_response_time(self):
        for key,value in [('pc','8000ffff'),('rd_wdata','1'),('cycle','0')]:
            rows=copy.deepcopy(self.rows)
            row=next(r for r in rows if r['event']=='retire' and int(r['insn'],16)==v2.WORDS[0]);row[key]=value
            with self.assertRaises(ValueError):self.gate(rows=rows)

    def test_console_handshake_unknown_duplicate_foreign_or_exception(self):
        line=next(x for x in self.text.splitlines() if x.startswith('[ARA_CONTRACT_TRACE]'))
        for bad in (line.replace('fire=1','fire=0',1),line.replace('insn=00802773','insn=00000057'),
                    line.replace('exc=0','exc=1'),line.replace('errors=0000000','errors=0000001'),
                    line.replace('resp=1/1 fire=1 id=2','resp=1/1 fire=1 id=3'),'',line+'\n'+line):
            with self.assertRaises(ValueError):self.gate(self.text.replace(line,bad))

    def test_independent_monitor_must_match(self):
        line=next(x for x in self.text.splitlines() if '[CVXIF/EVENT]' in x)
        for bad in ('',line.replace('insn=00802773','insn=00f024f3'),line.replace('exc=0','exc=1')):
            with self.assertRaises(ValueError):self.gate(self.text.replace(line,bad))

    def test_vector_write_or_extra_config_never_hidden_by_sixCSR(self):
        for vector in ([dict(self.vector[0],event='write',be='ff')],self.vector*2,
                       [dict(self.vector[0],vlen_bits='512')],[dict(self.vector[0],wdata='1')]):
            with self.assertRaises(ValueError):self.gate(vector=vector)

    def test_real_console_error_or_missing_success(self):
        for text in (self.text+'\nUVM_ERROR genuine failure\n',self.text.replace('Core Test *** SUCCESS ***','')):
            with self.assertRaises(ValueError):self.gate(text)

    def test_successor_executes_frozen_collect_and_marker_body(self):
        prepared=RUN.with_name(RUN.name+'.prepared.json')
        output=old.pre.OUT/'itlb-ppn-aba-v2-host-call-never-created'
        CALLS.clear()
        # Exercise the actual private wiring, without a second full waveform/OR collect.
        with patch.object(old,'collect',call_private_marker):
            v2.collect(prepared,v2.PREPARED_SHA,output)
        self.assertEqual(CALLS,[True])
        self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
