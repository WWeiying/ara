import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import qualify_sv39_alias770_terminal as q
from test_run_sv39_rvv_alias770 import TrapTests


def frames():
    codes={n:n for n in q.WIDTHS}
    state={n:'0'*width for n,width in q.WIDTHS.items()}
    state['rst_ni']='1';state['acc_mmu_en_q']='1'
    result=[];time=10;pointer=0
    def setvalue(s,n,v):s[n]=format(v,'0%db'%q.WIDTHS[n])
    for index in range(48):
        phase=index//16;pattern=q.run.reference.prior.PATTERNS[phase]
        for beat in range(4):
            before=dict(state)
            for n in q.WIDTHS:
                if n not in ('rst_ni','acc_mmu_en_q'):before[n]='0'*q.WIDTHS[n]
            setvalue(before,q.FIFO+'write_pointer_q',pointer)
            if beat==0:
                for n,v in {'aw_valid':1,'aw.addr':0x80003040,'aw.len':3,'aw.size':4,
                            'aw.burst':1,'ar_valid':1,'ar.addr':0x80003040,'ar.len':3,
                            'ar.size':4,'ar.burst':1,'r_ready':1}.items():setvalue(before,'axi_req_o.'+n,v)
                setvalue(before,'axi_resp_i.aw_ready',1);setvalue(before,'axi_resp_i.ar_ready',1)
            for n,v in {'w_valid':1,'w.data':pattern|(pattern<<64),'w.strb':65535,
                        'w.last':int(beat==3),'b_ready':1,'r_ready':1}.items():setvalue(before,'axi_req_o.'+n,v)
            for n,v in {'w_ready':1,'b_valid':int(beat==3),'r_valid':1,
                        'r.data':pattern|(pattern<<64),'r.last':int(beat==3)}.items():setvalue(before,'axi_resp_i.'+n,v)
            if beat==3:
                setvalue(before,q.FIFO+'push_i',1)
                setvalue(before,q.FIFO+'data_i.vaddr',q.run.reference.prior.address(phase))
                setvalue(before,'i_vlsu.i_addrgen.axi_addrgen_req_o.vaddr',q.run.reference.prior.address(phase))
                setvalue(before,q.FIFO+'data_i.slot',index%4)
            after=dict(before);after['clk_i']='1'
            if beat==3:pointer=(pointer+1)%16
            setvalue(after,q.FIFO+'write_pointer_q',pointer)
            # NBA data deliberately differs: the checker must only consume BEFORE.
            setvalue(after,q.FIFO+'data_i.vaddr',0)
            result.append((time,before,after));time+=10
    return result,codes


class MetadataTests(unittest.TestCase):
    def test_complete_preedge48(self):
        f,c=frames();result=q.metadata_frames(f,c,0x80003040)
        self.assertEqual(len(result['pushes']),48);self.assertTrue(result['preedge_sampling'])
        self.assertEqual([r['pointer'] for r in result['pushes'][:16]],list(range(16)))

    def reject(self,name,value,index=3):
        f,c=frames();f[index][1][name]=value
        with self.assertRaises(ValueError):q.metadata_frames(f,c,0x80003040)

    def test_wrong_virtual_alias(self):self.reject(q.FIFO+'data_i.vaddr','0'*128)
    def test_unknown_alias(self):self.reject(q.FIFO+'data_i.vaddr','x'*128)
    def test_pointer_postedge_bug(self):self.reject(q.FIFO+'write_pointer_q','0001')
    def test_missing_push(self):self.reject(q.FIFO+'push_i','0')
    def test_full_push(self):self.reject(q.FIFO+'full_o','1')
    def test_flush(self):self.reject(q.FIFO+'flush_i','1')
    def test_wrong_elem_start(self):self.reject(q.FIFO+'data_i.elem_start','0'*10+'1')
    def test_mprv_without_translation(self):self.reject('acc_mmu_en_q','0')
    def test_wrong_physical_data(self):self.reject('axi_req_o.w.data','0'*128)
    def test_bad_read_response(self):self.reject('axi_resp_i.r.resp','10')
    def test_unknown_write_valid(self):self.reject('axi_req_o.w_valid','x')
    def test_unexpected_reset(self):self.reject('rst_ni','0')
    def test_truncated(self):
        f,c=frames()
        with self.assertRaises(ValueError):q.metadata_frames(f[:-1],c,0x80003040)
    def test_extra_alias_pair(self):
        f,c=frames();extra=copy.deepcopy(f[:4])
        for i,(t,b,a) in enumerate(extra):extra[i]=(2000+t,b,a)
        with self.assertRaises(ValueError):q.metadata_frames(f+extra,c,0x80003040)
    def test_real_parser_declarations_and_timestamps(self):
        f,c=frames();lines=['$timescale 100fs $end','$scope module '+q.ROOT+' $end']
        codes={n:'v%d'%i for i,n in enumerate(q.WIDTHS)}
        for n,w in q.WIDTHS.items():lines.append('$var wire %d %s \\%s $end'%(w,codes[n],n))
        lines+=['$upscope $end','$enddefinitions $end']
        # Emit a falling edge before each rising edge to establish preedge values.
        for time,b,a in f:
            lines.append('#%d'%(time-1))
            lines += ['b%s %s'%(v,codes[n]) for n,v in b.items()]
            lines.append('#%d'%time)
            lines += ['b%s %s'%(v,codes[n]) for n,v in a.items()]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.vcd';p.write_text('\n'.join(lines)+'\n')
            self.assertEqual(q.metadata(p,0x80003040)['stores'],48)


class ArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=json.loads((q.run.PRE/'preflight.json').read_bytes())
        cls.reference=q.run.reference.prior.build.parse_spike_commits(q.run.PRE/'spike.trace')
        cls.expected=q.common.reference_counts(cls.reference,cls.pre['symbols'])

    def scalar(self):
        return dict(self.expected,status='TERMINAL_TOHOST_MATCH',rvfi_store_data_layout='unshifted',
            skipped_unobservable_register_values=0,stopped_at_unobservable=None,aligned_vector_faults=[],
            ara_trap_events=48,mismatch=None,terminal_ecall=None,
            ara_retired_instructions=self.expected['matched_instructions']+48,
            ara_committed_instructions=self.expected['matched_instructions'])

    def vector(self):
        records=[]
        for c in self.reference:
            if c.vector_writes:records.append(dict(pc=hex(c.pc),instruction=hex(c.instruction),
                compared_bytes=128*len(c.vector_writes),status='PASS',skipped_unknown_bytes=0,
                unknown_write_bytes=0,mismatch_count=0,first_mismatch=None))
        return dict(status='PASS',compared_instructions=len(records),compared_bytes=10624,
            skipped_unknown_bytes=0,non_bit_exact_instructions=0,nr_lanes=4,vlen_bits=1024,
            selected_index=None,stopped_at_spike_index=None,trapped_requests=[],first_mismatch=None,
            unobservable_instructions=0,incomplete_requests=[],unretired_requests=[],instructions=records)

    def test_sealed_reference_independent_allchecks(self):
        self.assertEqual(q.run.reference.validate(self.reference,self.pre['symbols']),self.pre['counts'])
        self.assertEqual(len(self.reference),58788)
        self.assertEqual(self.expected['matched_instructions'],55215)
        q.scalar_exact(self.scalar(),self.reference,self.pre['symbols'])
        q.vector_exact(self.vector(),self.reference)

    def test_scalar_corrupt_each_full_gate(self):
        for key in ('matched_instructions','matched_scalar_writes','matched_scalar_memory_accesses',
                    'ara_trap_events','ara_retired_instructions','skipped_unobservable_register_values'):
            with self.subTest(key=key):
                r=self.scalar();r[key]+=1
                with self.assertRaises(ValueError):q.scalar_exact(r,self.reference,self.pre['symbols'])

    def test_vector_corrupt_tail_unknown_missing_or_PC(self):
        for key,val in (('compared_bytes',127),('unknown_write_bytes',1),('pc','0x80000000')):
            with self.subTest(key=key):
                r=self.vector();r['instructions'][0][key]=val
                with self.assertRaises(ValueError):q.vector_exact(r,self.reference)
        r=self.vector();r['instructions'].pop()
        with self.assertRaises(ValueError):q.vector_exact(r,self.reference)

    def test_bound_run_actual_prepared_not_DUT(self):
        self.assertEqual(q.bound_run()['formal770_fixed_seal'],q.runner.BASE_SEAL)

    def test_scope_elf_and_baseline_drift(self):
        original=json.loads(q.RUN.with_name(q.RUN.name+'.prepared.json').read_bytes())
        for key in ('elf_sha256','formal770_fixed_seal','preflight_seal','case','output'):
            with self.subTest(key=key):
                r=copy.deepcopy(original);r[key]='drift'
                with patch.object(q.life,'read_bound',return_value=r),patch.object(q.life,'check'):
                    with self.assertRaises(ValueError):q.bound_run()

    def test_pin_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'evidence';p.write_text('first');pins={str(p):q.life.digest(p)}
            p.write_text('changed')
            with self.assertRaises(ValueError):q.life.check(pins)

    def test_actual_prepare_schema_and_merged_pins(self):
        with tempfile.TemporaryDirectory(prefix='alias-plan-hosttest-',dir=q.life.OUT) as d:
            out=Path(d);out.rmdir();record=q.prepare(out)
            self.assertEqual(record['baseline_seal'],q.runner.BASE_SEAL)
            self.assertFalse(record['coverage_admitted'])
            self.assertEqual(record['pins'][str(q.run.PRE/'input.elf')],q.run.ELF_SEAL)
            q.life.check(record['pins'])

    def retire_fixture(self):
        rows=[];started=False
        for c in self.reference:
            if c.pc==0x80000000:started=True
            if not started:continue
            if c.pc==self.pre['symbols']['alias_machine_return']:
                rows.append(dict(event='retire',order=str(len(rows)),trap='1',
                    pc=hex(self.pre['symbols']['alias_s_ecall']),insn='0x73',rd='0',
                    rd_wdata='0',mem_addr='0',mem_rmask='0',mem_wmask='0',mem_wdata='0'))
            rd=next(iter(c.gpr_writes),0);access=q.common.scalar_memory(c.instruction)
            address,value=(c.memory_accesses[0] if access and c.memory_accesses else (0,None))
            width=access[1] if access else 0;mask=((1<<width)-1)<<(address&7)
            row=dict(event='retire',order=str(len(rows)),trap='0',pc=hex(c.pc),insn=hex(c.instruction),
                rd=str(rd),rd_wdata=hex(c.gpr_writes.get(rd,0)),mem_addr=hex(address),
                mem_rmask=hex(mask if access and access[0]=='read' else 0),
                mem_wmask=hex(mask if access and access[0]=='write' else 0),
                mem_wdata=hex(value or 0))
            rows.append(row)
            if (self.pre['symbols']['tohost'],1) in c.memory_accesses:break
        return rows

    def test_reference_full_readback_signature(self):
        self.assertEqual(q.observed(self.retire_fixture(),self.pre['symbols'])['checks'],3113)

    def test_missing_single_source_readback(self):
        rows=self.retire_fixture();address=self.pre['symbols']['alias_source']
        for r in rows:
            if int(r['mem_addr'],16)==address and int(r['mem_rmask'],16):
                r.update(mem_addr='0',mem_rmask='0xff')
        with self.assertRaises(ValueError):q.observed(rows,self.pre['symbols'])

    def test_nonzero_raw_fail_signature(self):
        rows=self.retire_fixture();address=self.pre['symbols']['g75_result']+4
        for r in rows:
            if int(r['mem_addr'],16)==address and int(r['mem_wmask'],16):r['mem_wdata']='1'
        with self.assertRaises(ValueError):q.observed(rows,self.pre['symbols'])


class LifecycleTests(unittest.TestCase):
    def fixture(self):
        rows=[]
        for event,cycle,seq in [('arch_start',0,0),('cvx_req',1,-1),('uop_alloc',1,0),
                              ('cvx_resp',2,-1),('retire',3,0),('uop_done',4,0)]:
            rows.append(dict(event=event,cycle=str(cycle),order=str(seq),trans_id='2',
                             insn='00000057',port='3',trap='0'))
        native=[]
        for event,cycle in [('alloc',1),('write',3),('done',4)]:
            native.append(dict(event=event,cycle=str(cycle),arch_seq='0',vid='3',insn='00000057',
                nr_lanes='4',vlen_bits='1024',use_vd='1',vd='8',eew='0',vl='8',vstart='0',source='0',lane='0'))
        return rows,native

    def call(self,rows,native):
        with patch.object(q.run,'trap_contract',return_value={'supervisor_ecalls':48}):
            return q.lifecycle(rows,native,{})

    def test_retire_before_backend_done(self):
        r,v=self.fixture();self.assertEqual(self.call(r,v)['backend_uops'],1)

    def test_wrong_backend_owner(self):
        r,v=self.fixture();r[-1]['order']='1'
        with self.assertRaises(ValueError):self.call(r,v)

    def test_wrong_current_sid(self):
        r,v=self.fixture();v[1]['vid']='2'
        with self.assertRaises(ValueError):self.call(r,v)

    def test_duplicate_allocation(self):
        r,v=self.fixture();v.insert(1,copy.deepcopy(v[0]))
        with self.assertRaises(ValueError):self.call(r,v)

    def test_missing_completion(self):
        r,v=self.fixture();v.pop()
        with self.assertRaises(ValueError):self.call(r,v)

    def test_extra_exception(self):
        r,v=self.fixture();r[3]['trap']='1'
        with self.assertRaises(ValueError):self.call(r,v)


class TerminalTests(unittest.TestCase):
    def test_profile_echo_is_not_executed_evidence(self):
        objects=['clk_i','rst_ni','acc_mmu_en_q','axi_req_o','axi_resp_i',
            *[q.FIFO+n for n in ('push_i','full_o','flush_i','write_pointer_q','data_i')],
            'i_vlsu.i_addrgen.axi_addrgen_req_o']
        valid='\n'.join(['ALIAS_METADATA_OBJECT '+q.ROOT+'.'+n for n in objects]+['ALIAS_METADATA_PROFILE_READY_11'])
        q.profile_exact('puts "ALIAS_METADATA_CAPTURE_ERROR $message"\n'+valid)
        with self.assertRaises(ValueError):q.profile_exact('puts "ALIAS_METADATA_PROFILE_READY_11"')
        with self.assertRaises(ValueError):q.profile_exact(valid+'\nALIAS_METADATA_CAPTURE_ERROR actual')

    def test_binary_toggle_shape_change_rejected(self):
        row={'width':2,'checksum':'7','bits':'0x1'}
        with self.assertRaises(ValueError):q.toggle.t.union({'scope':row},{'scope':dict(row,checksum='8')})

    def test_fail_timeout_and_wrong_ELF(self):
        prepared=json.loads(q.RUN.with_name(q.RUN.name+'.prepared.json').read_bytes())
        actual=dict(prepared,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
        state=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,case=q.run.NAME,
            coverage_admitted=False,admission_performed=False,terminal_oracle_verified=False,pid=123)
        started=dict(command=prepared['command'],budget_s=600,pid=123,process_group=123,
            elf_sha256=q.run.ELF_SEAL,image_sha256=q.run.frozen.IMAGE_SEAL,input_elf=str(q.run.PRE/'input.elf'),
            image=str(q.life.IMAGE),foreground_lifetime=True,coverage_admitted=False)
        q.terminal(state,actual,started,prepared)
        for key,val in [('returncode',-9),('timeout',True),('status','TIMEOUT')]:
            bad=dict(state,**{key:val})
            with self.assertRaises(ValueError):q.terminal(bad,actual,started,prepared)
        with self.assertRaises(ValueError):q.terminal(state,actual,dict(started,elf_sha256='0'*64),prepared)


if __name__=='__main__':unittest.main()
