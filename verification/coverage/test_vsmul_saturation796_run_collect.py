import copy
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_vsmul_saturation796 as r
import collect_vsmul_saturation796 as c


def scalar_rows(reference):
    rows=[]
    for order,commit in enumerate(reference):
        row={key:'0' for key in c.common.COMMIT_FIELDS}
        row.update(event='retire',order=str(order),cycle=str(order),pc='%016x'%commit.pc,
            insn='%08x'%commit.instruction,rd_wdata='0000000000000000',mem_wdata='0000000000000000')
        if commit.gpr_writes:
            rd,value=next(iter(commit.gpr_writes.items()));row.update(rd=str(rd),rd_wdata='%016x'%value)
        access=c.common.scalar_memory(commit.instruction)
        if access:
            kind,width=access;assert len(commit.memory_accesses)==1
            address,value=commit.memory_accesses[0];row['mem_addr']='%016x'%address
            row['mem_rmask' if kind=='read' else 'mem_wmask']='%x'%(((1<<width)-1)<<(address&7))
            if kind=='write':row['mem_wdata']='%016x'%value
        rows.append(row)
    return rows


def physical_writes(seq,insn,reg,data,eew,source,cycle):
    rows=[]
    for word in range(len(data)//32):
        for lane in range(4):
            payload=bytes(data[word*32+c.vc._deshuffle_byte(lane*8+byte,4,eew)] for byte in range(8))
            rows.append(c.vc.VectorWrite(row=len(rows),cycle=cycle,arch_seq=seq,vid=seq%8,
                lane=lane,source=source,instruction=insn,eew=eew,addr=reg*4+word,be=255,
                data=int.from_bytes(payload,'little'),known_be=255))
    return rows


def native_fixture(reference,symbols):
    roles={symbols[n]:n for n in ('sm_load_a','sm_load_b','sm_seed','sm_target','sm_store_a','sm_store_b','sm_store_d')}
    config={key:'0' for key in c.common.VECTOR_FIELDS}
    config.update(event='config',nr_lanes='4',vlen_bits='1024')
    counts={n:0 for n in roles.values()};activities={};mapping={};raw=[config];starts={};seq=0
    for index,commit in enumerate(reference):
        if not c.vc.is_vector_instruction(commit.instruction):continue
        seq+=1;mapping[seq]=index;starts[index]=seq;role=roles.get(commit.pc)
        activity=c.vc.ArchActivity(commit.instruction,allocations=1,completions=1)
        use,vd,eew,vl=0,0,0,0
        if role:
            phase=counts[role];counts[role]+=1;expected=r.p.case(phase)
            if role.startswith('sm_store'):vl=128
            else:
                vd,source,data=(8,4,expected['sources'][0]) if role=='sm_load_a' else (16,4,expected['sources'][1]) if role=='sm_load_b' else (24,0,bytes([0x5a])*128) if role=='sm_seed' else (24,1,expected['destination'][:32])
                eew=phase//3 if role=='sm_target' else 0;vl=expected['vl'] if role=='sm_target' else 128;use=1
                activity.use_vd=True;activity.vd=vd;activity.eew=eew;activity.vl=vl;activity.vstart=0
                activity.writes=physical_writes(seq,commit.instruction,vd,data,eew,source,index*10+2)
                if role=='sm_target' and phase==3:
                    identity=physical_writes(seq,commit.instruction,8,expected['sources'][0],eew,3,index*10+1)
                    activity.writes=identity+activity.writes
        activities[seq]=activity
        for event,cycle in (('alloc',index*10),('done',index*10+3)):
            row={key:'0' for key in c.common.VECTOR_FIELDS}
            row.update(event=event,cycle=str(cycle),arch_seq=str(seq),vid=str(seq%8),insn='%08x'%commit.instruction,
                use_vd=str(use),vd=str(vd),eew=str(eew),vl=str(vl),vstart='0',nr_lanes='4',vlen_bits='1024')
            raw.append(row)
        for write in activity.writes:
            row={key:'0' for key in c.common.VECTOR_FIELDS}
            row.update(event='write',cycle=str(write.cycle),arch_seq=str(seq),vid=str(seq%8),insn='%08x'%commit.instruction,
                source=str(write.source),lane=str(write.lane),addr=str(write.addr),eew=str(write.eew),be='ff',
                wdata='%016x'%write.data,nr_lanes='4',vlen_bits='1024')
            raw.append(row)
    return activities,mapping,raw,starts


class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=r.preflight();cls.symbols=cls.pre['symbols'];cls.reference=c.reference_prefix(cls.pre)
        cls.rows=scalar_rows(cls.reference)
        cls.activities,cls.mapping,cls.raw,cls.starts=native_fixture(cls.reference,cls.symbols)
        cls.base,cls.before,cls.tgl,cls.ledger=r.baseline()

    def test_actual_prepare_no_VCS_and_direct_ROOT_pins(self):
        out=r.life.OUT/'vsmul-saturation796-host-test-never-created'
        with patch.object(r,'invoke_run',side_effect=AssertionError('No EDA')):
            manifest=r.prepare(out)
        self.assertFalse(out.exists());self.assertEqual(manifest['timeout_s'],300)
        self.assertEqual(manifest['systemd_policy']['RuntimeMaxSec'],360)
        self.assertEqual(manifest['old_image_files_checked'],66)
        for name,h in r.direct_source_pins().items():self.assertEqual(manifest['pins'][name],h)

    def test_exact_command_and_missing_authorization(self):
        out=r.life.OUT/'vsmul-saturation796-host-test-never-created';command=r.command(out)
        self.assertEqual(command[0],str(r.life.IMAGE));self.assertIn('+PRELOAD='+str(r.ELF),command)
        self.assertIn('+ntb_random_seed=1',command);self.assertIn('line+cond+fsm+tgl+branch',command)
        process=subprocess.run(['/usr/bin/python3','-B',str(Path(r.__file__)),'run','--output',str(out),'--seal','a'*64],capture_output=True,text=True)
        self.assertNotEqual(process.returncode,0);self.assertIn('Explicit parent authorization',process.stderr)
        self.assertFalse(out.exists())

    def test_wrong_preflight_contract(self):
        pre=copy.deepcopy(self.pre);pre['counts']['vector_writers']=12
        with patch.object(r.life,'read_bound',return_value=pre):
            with self.assertRaises(ValueError):r.preflight()

    def test_direct_source_drift_rejected(self):
        with patch.object(r.life,'check',side_effect=ValueError('source drift')):
            with self.assertRaises(ValueError):r.direct_source_pins()

    def test_actual_reference_complete_signature(self):
        result=c.footprint(self.rows,self.symbols,self.reference)
        self.assertEqual(result['checks'],1272);self.assertEqual(len(result['per_operation_vcsr']),12)

    def test_actual_scalar_engine_no_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'commit.csv'
            with path.open('w') as stream:
                writer=csv.DictWriter(stream,fieldnames=c.common.COMMIT_FIELDS);writer.writeheader();writer.writerows(self.rows)
            result=c.common.spike_trace.compare_commit_prefix(Path(self.pre['reference']),path,0x80000000,
                terminal_tohost_address=self.symbols['tohost'],rvfi_store_data_layout='unshifted')
            c.common.scalar_exact(result,c.common.reference_counts(self.reference,self.symbols))

    def test_wrong_guard_CSR_and_source_value(self):
        addresses=(self.symbols['sm_snapshot'],self.symbols['sm_csr']+32,self.symbols['sm_source'])
        for address in addresses:
            rows=copy.deepcopy(self.rows)
            index=next(i for i,row in enumerate(rows) if row['mem_rmask']!='0' and int(row['mem_addr'],16)==address)
            rows[index]['rd_wdata']='0000000000000000'
            with self.assertRaises(ValueError):c.footprint(rows,self.symbols,self.reference)

    def test_missing_order_or_wrong_opcode(self):
        for mode in ('missing','opcode'):
            rows=copy.deepcopy(self.rows)
            if mode=='missing':rows.pop()
            else:rows[0]['insn']='00000013'
            with self.assertRaises(ValueError):c.footprint(rows,self.symbols,self.reference)

    def test_native_all_roles_and_transport_closed(self):
        proof,filtered=c.native_state(self.reference,self.activities,self.mapping,self.symbols,self.raw)
        self.assertEqual(proof['primary_compared_bytes'],4992)
        self.assertEqual(proof['identity_compared_bytes'],128)
        self.assertEqual(len(proof['writers']),48)
        self.assertTrue(all(w.source!=3 for a in filtered.values() for w in a.writes))
        self.assertEqual(sum(w.source==3 for a in self.activities.values() for w in a.writes),16)

    def reject_native(self,activities=None,raw=None,mapping=None):
        with self.assertRaises(ValueError):c.native_state(self.reference,activities or self.activities,
            mapping or self.mapping,self.symbols,raw or self.raw)

    def test_wrong_primary_unknown_duplicate_missing(self):
        for mode in ('data','unknown','duplicate','missing','EEW'):
            import dataclasses
            acts=copy.deepcopy(self.activities);seq=next(s for s,a in acts.items() if any(w.source==1 for w in a.writes))
            a=acts[seq];w=a.writes[0]
            if mode=='data':a.writes[0]=dataclasses.replace(w,data=w.data^1)
            elif mode=='unknown':a.writes[0]=dataclasses.replace(w,known_be=254)
            elif mode=='duplicate':a.writes.append(w)
            elif mode=='missing':a.writes.pop()
            else:a.eew=3
            self.reject_native(activities=acts)

    def test_identity_transport_cannot_hide_wrong_data_or_unknown(self):
        import dataclasses
        for change in ({'data':0},{'known_be':0},{'source':2}):
            acts=copy.deepcopy(self.activities);seq=next(s for s,a in acts.items() if any(w.source==3 for w in a.writes))
            a=acts[seq];i=next(i for i,w in enumerate(a.writes) if w.source==3)
            a.writes[i]=dataclasses.replace(a.writes[i],**change);self.reject_native(activities=acts)

    def test_store_context_wrong_missing_duplicate_or_identity(self):
        for change in ('vl','vstart','eew','vd','vid','insn','missing','duplicate'):
            raw=copy.deepcopy(self.raw)
            index=next(i for i,row in enumerate(raw) if row['event']=='alloc' and int(row['insn'],16)&127==39)
            if change=='missing':raw.pop(index)
            elif change=='duplicate':raw.append(copy.deepcopy(raw[index]))
            else:raw[index][change]='1' if change!='insn' else '00000013'
            self.reject_native(raw=raw)

    def test_native_actual_entry_generic_engine_no_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);rows=[]
            for index,row in enumerate(self.rows):
                if index in self.starts:
                    seq=self.starts[index];start=dict(row,event='arch_start',order=str(seq),trans_id=str(seq%8))
                    rows.append(start)
                rows.append(row)
                if index in self.starts:rows.append(dict(row,event='cvx_resp',order=str(self.starts[index]),trans_id=str(self.starts[index]%8)))
            for name,data,fields in (('commit_trace.csv',rows,c.common.COMMIT_FIELDS),('vector_trace.csv',self.raw,c.common.VECTOR_FIELDS)):
                with (run/name).open('w') as stream:
                    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(data)
            result=c.native(run,self.reference,self.symbols,self.pre)
            self.assertEqual(result['architectural_vector_diff']['compared_bytes'],4992)
            self.assertEqual(result['primary_and_transport']['identity_compared_bytes'],128)

    def test_actual_full6162_OR_and_negative_universe_shape_loss(self):
        single=copy.deepcopy(self.before);single['tests']=['/synthetic/one.vdb']
        combined=r.bitmap.combine(self.before,single);self.assertEqual(c.exact_raw_union(self.before,single,combined)['metric_instances'],6162)
        for mode in ('missing','extra','shape','lost','duplicate'):
            bad=copy.deepcopy(single);final=copy.deepcopy(combined);scope=next(iter(bad['metrics']['line']))
            if mode=='missing':bad['metrics']['line'].pop(scope)
            elif mode=='extra':bad['metrics']['line']['/foreign']=bad['metrics']['line'][scope]
            elif mode=='shape':bad['metrics']['line'][scope]['checksum']='wrong'
            elif mode=='lost':final['metrics']['line'][scope]['bits']='0x0'
            else:bad['tests']=[self.before['tests'][0]]
            with self.assertRaises(ValueError):c.exact_raw_union(self.before,bad,final)

    def test_actual_all2989_toggle_OR_and_missing_extra_shape(self):
        self.assertEqual(set(c.exact_toggle_union(self.tgl,self.tgl)),set(self.tgl))
        for mode in ('missing','extra','shape','overflow'):
            sample=copy.deepcopy(self.tgl);scope=next(iter(sample))
            if mode=='missing':sample.pop(scope)
            elif mode=='extra':sample['foreign']=sample[scope]
            elif mode=='shape':sample[scope]['checksum']='wrong'
            else:sample[scope]['bits']=hex(1<<sample[scope]['width'])
            with self.assertRaises(ValueError):c.exact_toggle_union(self.tgl,sample)

    def test_terminal_nonzero_timeout_and_command_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);manifest=dict(command=r.command(run));actual=dict(manifest,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
            state=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,case=r.NAME,
                coverage_admitted=False,admission_performed=False,pid=100,wall_seconds=1.0)
            started=dict(command=manifest['command'],input_elf=str(r.ELF),elf_sha256=r.ELF_SHA,image=str(r.life.IMAGE),
                image_sha256=r.IMAGE_SHA,pid=100,process_group=100,budget_s=300,foreground_lifetime=True)
            for name,data in (('manifest.json',actual),('started.json',started),('simulation-status.json',state)):(run/name).write_text(json.dumps(data))
            self.assertEqual(c.terminal(run,manifest)['returncode'],0)
            for change in ({'returncode':1},{'timeout':True},{'pid':101}):
                (run/'simulation-status.json').write_text(json.dumps(dict(state,**change)))
                with self.assertRaises(ValueError):c.terminal(run,manifest)


if __name__=='__main__':unittest.main()
