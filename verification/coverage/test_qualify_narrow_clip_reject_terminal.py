"""Strict17 owner/zero-activity/whole-memory tests; no running DUT consumption."""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch

import qualify_narrow_clip_reject_terminal as m


def symbols():
    result={name:0x80010000+i*0x1000 for i,name in enumerate(m.p.SYMBOLS)}
    result['trap_fail']=0x80000100
    return result


def commit(event,cycle,seq=-1,tid=0,insn=0,pc=0,**changes):
    row={k:'0' for k in m.common.COMMIT_FIELDS}
    row.update(event=event,cycle=str(cycle),order=str(seq),trans_id=str(tid),insn='%08x'%insn,
               pc='%016x'%pc,port='-1',rd_wdata='0000000000000000',mem_addr='0000000000000000',
               mem_rmask='00',mem_wmask='00',mem_wdata='0000000000000000')
    row.update({k:str(v) for k,v in changes.items()});return row


def vector(event,cycle,seq=100,**changes):
    row={k:'0' for k in m.common.VECTOR_FIELDS}
    row.update(event=event,cycle=str(cycle),arch_seq=str(seq),vid='0',insn='%08x'%m.p.RECOVERY,
               use_vd='1',vd='16',eew='0',vl='4',vstart='0',nr_lanes='4',vlen_bits='1024',be='ff',wdata='0000000000000000')
    row.update({k:str(v) for k,v in changes.items()});return row


def fixture():
    rows=[]
    for i,word in enumerate(m.WORDS):
        c=10*i
        rows.extend([commit('arch_start',c,i,0,word),commit('cvx_req',c+1,tid=0,insn=word),
                     commit('cvx_resp',c+2,tid=0,trap=1)])
    rows.extend([commit('arch_start',180,100,0,m.p.RECOVERY),commit('cvx_req',181,tid=0,insn=m.p.RECOVERY),
                 commit('uop_alloc',182,100,0,m.p.RECOVERY,port=0),
                 commit('uop_done',184,100,0,m.p.RECOVERY,port=0),commit('cvx_resp',185,tid=0),
                 commit('retire',186,0,-1,m.p.RECOVERY,symbols()['gnr_recovery'])])
    vectors=[vector('config',0,-1),vector('alloc',182),vector('write',183),vector('done',184)]
    return rows,vectors


class LifecycleTests(unittest.TestCase):
    def test_exact17_owners_repeated_word_different_cells(self):
        rows,vectors=fixture();r=m.lifecycle(rows,vectors,symbols())
        self.assertEqual(r['exceptions'],17);self.assertEqual(len(r['per_cell']),17)
        self.assertEqual(r['rejected_arch_seqs'],list(range(17)))
        self.assertEqual(r['per_cell'][9]['opcode'],r['per_cell'][12]['opcode'])
        self.assertNotEqual(r['per_cell'][9]['fault_pc'],r['per_cell'][12]['fault_pc'])
    def test_rejected_backend_allocation(self):
        rows,v=fixture();rows[2:2]=[commit('uop_alloc',1,0,0,m.WORDS[0],port=0),commit('uop_done',1,0,0,m.WORDS[0],port=0)]
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())
    def test_zeroBE_native_fault_not_ignored(self):
        rows,v=fixture();v.insert(1,vector('write',1,0,insn='%08x'%m.WORDS[0],be='00'))
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())
    def test_fault_config_not_ignored(self):
        rows,v=fixture();v[0]['arch_seq']='0'
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())
    def test_missing_exception(self):
        rows,v=fixture();rows[2]['trap']='0'
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())
    def test_duplicate_request(self):
        rows,v=fixture();rows.insert(2,deepcopy(rows[1]))
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())
    def test_wrong_opcode_order(self):
        rows,v=fixture();rows[0]['insn']=rows[1]['insn']='%08x'%m.WORDS[1]
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())
    def test_wrong_backend_transaction(self):
        rows,v=fixture();rows[-4]['trans_id']='1'
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())
    def test_early_done(self):
        rows,v=fixture();rows[-4]['event'],rows[-3]['event']='uop_done','uop_alloc'
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())
    def test_native_metadata_drift(self):
        rows,v=fixture();v[2]['vstart']='1'
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())
    def test_native_outside_lifetime(self):
        rows,v=fixture();v[2]['cycle']='185';v[3]['cycle']='186'
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())
    def test_vector_duplicate_done(self):
        rows,v=fixture();v.append(deepcopy(v[-1]))
        with self.assertRaises(ValueError):m.lifecycle(rows,v,symbols())


class SignatureTests(unittest.TestCase):
    def fixture(self):
        s=symbols();rows=[]
        def store(pc,address,value):
            rows.append(commit('retire',len(rows),len(rows),-1,0x0002b023,pc,
                mem_addr='%016x'%address,mem_wmask='ff',mem_wdata='%016x'%value))
        for n,c in enumerate(m.p.CASES):
            values=[2,s['gnr_bad_%02d'%n],int(c['word'],16),4,m.p.vtype(c),1,5,n+1,0x2222,1,117,0x801ffff0]
            for i,value in enumerate(values):store(s['gnr_handler']+(i*4),s['gnr_ledger']+(n*12+i)*8,value)
            store(s['gnr_handler']+48,s['gnr_traps'],n+1)
            values=[0x1111,0x2222,1,0x801ffff0,1,4,m.p.vtype(c),5,117]
            for i,value in enumerate(values):store(0x80001000,s['gnr_post']+(n*9+i)*8,value)
        values=[s['trap_fail']]*2+[0]*2+[0x801ffff0]*2+[0]*6
        for i,value in enumerate(values):store(0x80001000,s['gnr_restore']+i*8,value)
        store(0x80001000,s['g75_result'],2094);store(0x80001000,s['num_failed'],0)
        for phase in range(3):
            for reg in range(32):
                data=b'\xa5'*8+m.p.expected_register(reg,phase==2)+b'\xa5'*8
                for w in range(18):
                    value=int.from_bytes(data[w*8:w*8+8],'little')
                    addr=s['gnr_dump']+((phase*32+reg)*18+w)*8
                    rows.append(commit('retire',len(rows),len(rows),-1,0x0002b083,0x80001000,rd=1,
                        rd_wdata='%016x'%value,mem_addr='%016x'%addr,mem_rmask='ff'))
        store(0x80001000,s['tohost'],1)
        return rows,s
    def test_full_signatures_and_readback(self):
        rows,s=self.fixture();result=m.observed(rows,s)
        self.assertEqual(result['checks'],2094);self.assertEqual(result['illegal_traps'],17)
        self.assertEqual(result['explicit_dump_read_bytes'],13824)
        self.assertEqual(result['handler_store_words'],221)
    def test_noC_compressed_rejected(self):
        rows,s=self.fixture();rows[0]['insn']='0000e422'
        with self.assertRaises(ValueError):m.observed(rows,s)
    def test_vstart_tval_guard_corruption(self):
        for index,field in [(2,'mem_wdata'),(5,'mem_wdata'),(-2,'rd_wdata')]:
            rows,s=self.fixture();rows[index][field]='0000000000000000'
            with self.subTest(index=index),self.assertRaises(ValueError):m.observed(rows,s)
    def test_missing_full_snapshot_byte(self):
        rows,s=self.fixture();rows[-2]['mem_rmask']='00'
        with self.assertRaises(ValueError):m.observed(rows,s)
    def test_handler_protected_register(self):
        rows,s=self.fixture();rows[0]['rd']='8'
        with self.assertRaises(ValueError):m.observed(rows,s)
    def test_returncode_not_an_oracle(self):
        rows,s=self.fixture();rows[-1]['mem_wdata']='0000000000000003'
        with self.assertRaises(ValueError):m.observed(rows,s)


class StdoutTests(unittest.TestCase):
    def fixture(self):
        return '[ARA_CONTRACT] requests=18 responses=18 exceptions=17 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n', 'Core Test *** SUCCESS ***\nUVM_ERROR : 0\nUVM_FATAL : 0\n',dict(requests=18,responses=18)
    def test_complete_contract(self):
        c,l,r=self.fixture();self.assertEqual(m.stdout_gate(c,l,r)['exceptions'],17)
    def test_nonzero_missing_duplicate_stall_fields(self):
        for suffix in ['req_stalled=1 resp_stalled=0','req_stalled=0','req_stalled=0 resp_stalled=0 resp_stalled=0']:
            c,l,r=self.fixture();c=c.replace('req_stalled=0 resp_stalled=0',suffix)
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):m.stdout_gate(c,l,r)
    def test_real_UVM_error_fatal_nonzero_summary(self):
        for extra in ['UVM_ERROR message','UVM_FATAL @ 10: failure','UVM_ERROR : 1','Fatal: failure']:
            c,l,r=self.fixture()
            with self.subTest(extra=extra),self.assertRaises(ValueError):m.stdout_gate(c,l+extra+'\n',r)
    def test_duplicate_contract_success(self):
        c,l,r=self.fixture()
        with self.assertRaises(ValueError):m.stdout_gate(c+c,l,r)
        with self.assertRaises(ValueError):m.stdout_gate(c,l+l,r)


class VectorTests(unittest.TestCase):
    def fixture(self):
        reference=[SimpleNamespace(pc=0x80001000+i*4,instruction=0x02028007+i*128,vector_writes={i:1}) for i in range(32)]
        reference.append(SimpleNamespace(pc=0x80003000,instruction=m.p.RECOVERY,vector_writes={16:1}))
        result=dict(status='PASS',compared_instructions=33,skipped_unknown_bytes=0,non_bit_exact_instructions=0,
            nr_lanes=4,vlen_bits=1024,selected_index=None,stopped_at_spike_index=None,trapped_requests=list(range(17)),
            first_mismatch=None,unobservable_instructions=0,incomplete_requests=[],unretired_requests=[],
            vector_destination_requests=33,prefix_vector_destination_requests=33,compared_bytes=4100,
            verified_zero_write_traps=[],verified_identity_write_traps=[],verified_probed_load_faults=[],verified_trapped_destination_requests=[])
        result['instructions']=[dict(pc='0x%016x'%c.pc,instruction='0x%08x'%c.instruction,
            compared_bytes=128 if i<32 else 4,status='PASS',skipped_unknown_bytes=0,unknown_write_bytes=0,
            mismatch_count=0,first_mismatch=None) for i,c in enumerate(reference)]
        return result,reference
    def test_exact33_known_writers(self):
        r,c=self.fixture();m.vector_gate(r,list(range(17)),c)
    def test_partial_unknown_writer_or_exception_accommodation(self):
        for key,value in [('status','PREFIX'),('vector_destination_requests',34),('skipped_unknown_bytes',1),
                          ('verified_identity_write_traps',[dict(arch_seq=0,compared_bytes=128)])]:
            r,c=self.fixture();r[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.vector_gate(r,list(range(17)),c)
    def test_missing_full_vrf_bytes(self):
        r,c=self.fixture();r['instructions'][0]['compared_bytes']=127
        with self.assertRaises(ValueError):m.vector_gate(r,list(range(17)),c)
    def test_recovery_and_total_bytes_strict(self):
        for size in (0,8,128):
            r,c=self.fixture();r['instructions'][-1]['compared_bytes']=size;r['compared_bytes']=4096+size
            with self.assertRaises(ValueError):m.vector_gate(r,list(range(17)),c)
        r,c=self.fixture();r['prefix_vector_destination_requests']=True
        with self.assertRaises(ValueError):m.vector_gate(r,list(range(17)),c)
    def test_scalar_partial_bool_count_rejected(self):
        with self.assertRaises(ValueError):m.common.scalar_exact(dict(status='PREFIX'),dict(matched_instructions=1))


class VerifyPlanTests(unittest.TestCase):
    def fixture(self):
        run=m.life.OUT/'synthetic-clip17-450-run'
        prepared=str(run.with_name(run.name+'.prepared.json'))
        dependency=Path(m.__file__).resolve()
        record=dict(pins={'/synthetic/input':'a'*64})
        pre=dict(targets=['exact-target'],reference_counts={'matched_instructions':73304})
        pins=m.life.merge_pins(record['pins'],{prepared:'b'*64,
            str(m.PRE/'preflight-manifest.json'):m.PRE_SEAL})
        pins=m.life.merge_pins(pins,{str(dependency):m.life.digest(dependency)})
        plan=dict(status=m.STATUS,preflight=str(m.PRE),preflight_seal=m.PRE_SEAL,
            coverage_admitted=False,qualification_only=True,run=str(run),prepared=prepared,
            prepared_seal='b'*64,pins=pins,**pre)
        return plan,record,pre,dependency

    def invoke(self,plan,record,pre,dependency):
        # Execute the real verify_plan and real two-argument merge_pins;
        # isolate only unrelated expensive image/preflight validation.
        with patch.object(m.life,'read_bound',side_effect=[plan,record]), \
             patch.object(m.life,'check'),patch.object(m.p,'verify',return_value=pre), \
             patch.object(m,'prepared_gate'),patch.object(m,'dependencies',return_value=[dependency]):
            return m.verify_plan(m.life.OUT/'synthetic-plan.json','c'*64)

    def test_verify_plan_real_merge_call_path(self):
        plan,record,pre,dependency=self.fixture()
        self.assertEqual(self.invoke(plan,record,pre,dependency),(plan,record,pre))

    def test_verify_plan_missing_dependency_rejected(self):
        plan,record,pre,dependency=self.fixture();del plan['pins'][str(dependency)]
        with self.assertRaises(ValueError):self.invoke(plan,record,pre,dependency)

    def test_verify_plan_conflicting_dependency_rejected(self):
        plan,record,pre,dependency=self.fixture();record['pins'][str(dependency)]='d'*64
        with self.assertRaises(ValueError):self.invoke(plan,record,pre,dependency)


class ReceiptAndELFTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=m.life.read_bound(m.PRE/'preflight-manifest.json',m.PRE_SEAL)
        cls.reference=m.p.frozen.shared.parse_spike_commits(m.PRE/'spike.trace')

    def receipt(self):
        record=dict(command=m.runner.command(m.life.OUT/'synthetic-clip17-run'))
        state=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,case=m.runner.NAME,
            timeout=False,coverage_admitted=False,admission_performed=False,terminal_oracle_verified=False,
            pid=123,wall_seconds=20.0)
        started=dict(command=record['command'],input_elf=str(m.runner.ELF),elf_sha256=m.runner.ELF_SHA,
            image=str(m.life.IMAGE),image_sha256=m.runner.IMAGE_SHA,pid=123,process_group=123,
            budget_s=450,foreground_lifetime=True,coverage_admitted=False)
        return state,deepcopy(record),started,record

    def reference_rows(self):
        rows=[];started=False
        for c in self.reference:
            if c.pc==0x80000000:started=True
            if not started:continue
            rd,value=next(iter(c.gpr_writes.items()),(0,0))
            row=commit('retire',len(rows),len(rows),-1,c.instruction,c.pc,rd=rd,rd_wdata=hex(value))
            access=m.common.scalar_memory(c.instruction)
            if access and c.memory_accesses:
                kind,size=access;addr,data=c.memory_accesses[0]
                row['mem_addr']=hex(addr)
                row['mem_'+('rmask' if kind=='read' else 'wmask')]=hex(((1<<size)-1)<<(addr&7))
                if kind=='write':row['mem_wdata']=hex(data)
            rows.append(row)
            if (self.pre['symbols']['tohost'],1) in c.memory_accesses:break
        return rows

    def test_sealed_software_full_ELF_gold_regression(self):
        rows=self.reference_rows();m.audit_retirements(rows)
        value=m.observed(rows,self.pre['symbols'])
        self.assertEqual((value['checks'],value['snapshots'],value['illegal_traps'],
            value['explicit_dump_read_bytes'],value['handler_store_words']),(2094,3,17,13824,221))

    def test_foreign_opcode_and_PC_rejected(self):
        for field,value in [('insn','ffffffff'),('pc','0000000000000000'),('insn','0000e422')]:
            rows=self.reference_rows();rows[0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):m.audit_retirements(rows)

    def test_successful_OS_receipt(self):m.terminal(*self.receipt())

    def test_exact450_runner_and_test_binding(self):
        self.assertEqual(m.runner.BUDGET,450)
        self.assertEqual(m.life.digest(m.RUNNER_PATH),m.RUNNER_SHA)
        self.assertEqual(m.life.digest(m.RUNNER_TEST),m.RUNNER_TEST_SHA)
        self.assertIn(m.RUNNER_PATH,m.dependencies())
        self.assertIn(m.RUNNER_TEST,m.dependencies())

    def test_old300_startup_cannot_qualify(self):
        args=self.receipt();args[2]['budget_s']=300
        with self.assertRaises(ValueError):m.terminal(*args)

    def test_failed_timeout_unknown_OS_rejected(self):
        for key,value in [('returncode',None),('returncode',True),('returncode',1),('timeout',True),
                          ('case','other'),('pid',True),('wall_seconds',float('nan')),('wall_seconds',True)]:
            args=self.receipt();args[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.terminal(*args)

    def test_wrong_started_identity_rejected(self):
        for key,value in [('pid',124),('process_group',124),('budget_s',180),('budget_s',True),
                          ('elf_sha256','a'*64),('image_sha256','b'*64),('foreground_lifetime',False)]:
            args=self.receipt();args[2][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.terminal(*args)

    def test_wrong_actual_manifest_rejected(self):
        args=self.receipt();args[1]['extra']=True
        with self.assertRaises(ValueError):m.terminal(*args)


if __name__=='__main__':unittest.main()
