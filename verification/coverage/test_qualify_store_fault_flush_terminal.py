import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import qualify_store_fault_flush_terminal as q


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.directory=q.runner.PRE
        self.pre=json.loads((self.directory/'preflight-manifest.json').read_bytes())
        self.symbols=self.pre['symbols']

    def observed_fixture(self):
        reference=q.p.shared.parse_spike_commits(self.directory/'spike.trace')
        rows=[]; active=False
        for c in reference:
            if c.pc==0x80000000: active=True
            if not active: continue
            rd,value=next(iter(c.gpr_writes.items()),(0,0))
            r=dict(event='retire',order=str(len(rows)),pc=hex(c.pc),insn=hex(c.instruction),trap='0',
                   rd=str(rd),rd_wdata=hex(value),mem_addr='0',mem_rmask='0',mem_wmask='0',mem_wdata='0')
            access=q.common.scalar_memory(c.instruction)
            if access is not None and c.memory_accesses:
                kind,size=access; address,data=c.memory_accesses[0]
                r['mem_addr']=hex(address)
                r['mem_'+('rmask' if kind=='read' else 'wmask')]=hex(((1<<size)-1)<<(address&7))
                if kind=='write': r['mem_wdata']=hex(data)
            rows.append(r)
            if (self.symbols['tohost'],1) in c.memory_accesses: break
        return rows

    def test_real_reference_memory_all134_and_guards(self):
        result=q.observed(self.observed_fixture(),self.symbols,self.directory)
        self.assertEqual(result['checks'],134)
        self.assertEqual(result['explicit_readback_bytes'],1024)

    def test_wrong_source_readback_rejected(self):
        rows=self.observed_fixture()
        matches=[r for r in rows if int(r['mem_addr'],16)==self.symbols['sff_a'] and int(r['mem_rmask'],16)]
        self.assertTrue(matches)
        matches[-1]['rd_wdata']='0'
        with self.assertRaisesRegex(ValueError,'Buffer/guard'): q.observed(rows,self.symbols,self.directory)

    def test_wrong_trap_ledger_rejected(self):
        rows=self.observed_fixture()
        for r in rows:
            if int(r['mem_addr'],16)==self.symbols['sff_trap']+8 and int(r['mem_rmask'],16):
                r['rd_wdata']='6'
        with self.assertRaisesRegex(ValueError,'trap/privilege'): q.observed(rows,self.symbols,self.directory)

    def test_missing_footprint_or_extra_terminal_rejected(self):
        rows=self.observed_fixture()
        altered=[r for r in rows if not(int(r['mem_rmask'],16) and int(r['mem_addr'],16)==self.symbols['sff_b'])]
        for i,r in enumerate(altered): r['order']=str(i)
        with self.assertRaisesRegex(ValueError,'Incomplete.*readback'): q.observed(altered,self.symbols,self.directory)
        rows=self.observed_fixture(); rows.append(dict(rows[-1],order=str(len(rows))))
        with self.assertRaisesRegex(ValueError,'tohost'): q.observed(rows,self.symbols,self.directory)

    def lifecycle_fixture(self):
        proof=json.loads((self.directory/'linked-proof.json').read_bytes())
        rows=[]; vectors=[]
        def row(event,seq,cycle,word,trap=0,port=0):
            rows.append(dict(event=event,order=str(seq),cycle=str(cycle),trans_id=str(seq if event!='cvx_resp' else 1),
                pc='0',insn=hex(word),trap=str(trap),port=str(port)))
        for s,word in enumerate((proof['fault_opcode'],proof['recovery_opcode'])):
            t=1+10*s
            row('arch_start',s,t,word); row('cvx_req',s,t+1,word); row('uop_alloc',s,t+2,word)
            row('uop_done',s,t+3,word)
            row('cvx_resp',-1,t+4,0,trap=int(s==0)); rows[-1]['trans_id']=str(s)
            for event,cycle in [('alloc',t+2),('done',t+3)]:
                vectors.append(dict(event=event,cycle=str(cycle),arch_seq=str(s),vid='0',insn=hex(word),
                    nr_lanes='4',vlen_bits='1024',use_vd='0',vd='8' if s==0 else '16',eew='3',vl='8',vstart='0'))
        rows.append(dict(event='retire',order='0',cycle='20',trans_id='-1',pc=hex(self.symbols['sff_recovery']),
                         insn=hex(proof['recovery_opcode']),trap='0',port='0'))
        return rows,vectors,proof

    def test_fault_backend_and_recovery_conservation(self):
        rows,vectors,proof=self.lifecycle_fixture()
        result=q.lifecycle(rows,vectors,self.symbols,proof['fault_opcode'],proof['recovery_opcode'])
        self.assertEqual(result['exceptions'],1); self.assertEqual(result['backend_uops'],2)

    def test_no_fault_response_or_incomplete_native_rejected(self):
        rows,vectors,proof=self.lifecycle_fixture()
        rows[4]['trap']='0'
        with self.assertRaisesRegex(ValueError,'fault request'): q.lifecycle(rows,vectors,self.symbols,proof['fault_opcode'],proof['recovery_opcode'])
        rows,vectors,proof=self.lifecycle_fixture()
        with self.assertRaisesRegex(ValueError,'event identity'): q.lifecycle(rows,vectors[:-1],self.symbols,proof['fault_opcode'],proof['recovery_opcode'])

    def test_terminal_unknown_returncode_and_timeout_rejected(self):
        for state in ({}, {'status':'SIMULATION_EXITED_NOT_ADMITTED','returncode':None},
                      {'status':'SIMULATION_EXITED_NOT_ADMITTED','returncode':0,'timeout':True}):
            with self.assertRaisesRegex(ValueError,'OS receipt'): q.terminal(state,{}, {},{'preflight':str(self.directory/'preflight-manifest.json')})

    def test_actual_prepare_uses_explicit_prepared_path_without_runner_globals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); run=root/'run'; output=root/'plan'
            prepared=dict(preflight=str(self.directory/'preflight-manifest.json'),preflight_seal=q.runner.PRE_SEAL,pins={})
            sourcebook=q.p.BUILD/'build-source-pins.json'
            original=q.life.read_bound
            def read(path,seal):
                if path==run.with_name('run.prepared.json'): return prepared
                return original(path,seal)
            oldpre,oldseal=q.runner.PRE,q.runner.PRE_SEAL
            del q.runner.PRE; del q.runner.PRE_SEAL
            try:
                with patch.object(q.life,'OUT',root),patch.object(q.life,'read_bound',side_effect=read), \
                     patch.object(q.life,'check'),patch.object(q,'verify_prepared') as prepare:
                    q.prepare(run,'a'*64,output)
                    prepare.assert_called_once_with(run,prepared)
                    plan=json.loads((output/'plan.json').read_text())
                    self.assertEqual(plan['preflight'],prepared['preflight'])
                    self.assertEqual(plan['preflight_seal'],oldseal)
            finally: q.runner.PRE=oldpre; q.runner.PRE_SEAL=oldseal

    def test_real_completed_directory_supported_without_fresh_runner(self):
        run=q.life.OUT/'store-fault-flush-old-image-732-parent-20261006-01'
        prepared=json.loads(run.with_name(run.name+'.prepared.json').read_bytes())
        self.assertTrue(run.is_dir())
        with patch.object(q.life,'check'),patch.object(q.runner,'prepare',side_effect=AssertionError('fresh runner called')):
            q.verify_prepared(run,prepared)

    def test_prepared_command_and_missing_image_obligation_rejected(self):
        run=q.life.OUT/'store-fault-flush-old-image-732-parent-20261006-01'
        original=json.loads(run.with_name(run.name+'.prepared.json').read_bytes())
        for mutation in ('command','pin'):
            prepared=copy.deepcopy(original)
            if mutation=='command': prepared['command'].append('+unexpected')
            else: prepared['pins'].pop(str(q.life.IMAGE))
            with patch.object(q.life,'check'):
                with self.assertRaises(ValueError): q.verify_prepared(run,prepared)

    def test_actual_collect_rejects_nonPASS_before_trace_without_runner_globals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); run=root/'run';run.mkdir();output=root/'post'
            prepared=dict(preflight=str(self.directory/'preflight-manifest.json'),preflight_seal=q.runner.PRE_SEAL,output=str(run))
            plan=dict(status=q.STATUS,run=str(run),prepared=str(root/'prepared.json'),prepared_seal='runseal',pins={},
                      preflight=prepared['preflight'],preflight_seal=prepared['preflight_seal'])
            (run/'simulation-status.json').write_text('{}')
            (run/'manifest.json').write_text('{}');(run/'started.json').write_text('{}')
            oldpre,oldseal=q.runner.PRE,q.runner.PRE_SEAL
            del q.runner.PRE;del q.runner.PRE_SEAL
            try:
                with patch.object(q.life,'OUT',root),patch.object(q.life,'check'), \
                     patch.object(q.life,'read_bound',side_effect=[plan,prepared]),patch.object(q.common,'read_csv') as trace:
                    with self.assertRaisesRegex(ValueError,'OS receipt'):q.collect(root/'plan.json','a'*64,output)
                    trace.assert_not_called();self.assertFalse(output.exists())
            finally:q.runner.PRE=oldpre;q.runner.PRE_SEAL=oldseal


if __name__=='__main__':unittest.main()
