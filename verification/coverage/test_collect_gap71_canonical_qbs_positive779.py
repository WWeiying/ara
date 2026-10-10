import copy
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ara_verify.vector_commit import ArchActivity, VectorWrite
import collect_gap71_canonical_qbs_positive779 as c


def frame():
    keys = ('rst_ni','burst_fifo_count_q','fault_pending_q','ar_stalled_q',
        'axi_ar_valid_o','axi_ar_ready_i','axi_r_valid_i','axi_r_ready_o',
        'fault_valid_o','response_fault_event','response_drain_q','planner_fault_event',
        'en_ld_st_translation_i','mmu_req_o','mmu_vaddr_o','mmu_valid_i',
        'mmu_exception_valid_i','physical_check_valid_o','plan_state_q')
    s = dict.fromkeys(keys,0); s['rst_ni']=1
    return s


def samples():
    a=frame(); a.update(axi_ar_valid_o=1,axi_ar_ready_i=1)
    a['axi_ar_o.addr']=0x80000000
    f=frame(); f.update(burst_fifo_count_q=1,en_ld_st_translation_i=1,plan_state_q=2,
        mmu_req_o=1,mmu_vaddr_o=c.FAULT,mmu_exception_valid_i=1,
        planner_fault_event=1,planner_fault_kind=2,planner_fault_vaddr=c.FAULT)
    for field in ('mmu_exception_i','planner_fault_mmu_exception'):
        f[field+'.cause']=13; f[field+'.tval']=c.FAULT
    d=frame(); d.update(burst_fifo_count_q=1,fault_pending_q=1,axi_r_valid_i=1,axi_r_ready_o=1)
    d['axi_r_i.resp']=0; d['axi_r_i.last']=1
    o=frame(); o.update(fault_pending_q=1,fault_valid_o=1,fault_ready_i=1,fault_kind_o=2,fault_vaddr_o=c.FAULT)
    o['fault_mmu_exception_o.cause']=13; o['fault_mmu_exception_o.tval']=c.FAULT
    r=frame(); r.update(en_ld_st_translation_i=1,mmu_req_o=1,mmu_vaddr_o=c.FAULT,
        mmu_valid_i=1,physical_check_valid_o=1,physical_range_allowed_i=1,plan_state_q=2)
    return [(i+1,s) for i,s in enumerate([a,f,d,o,r,frame()])]


class CollectorTests(unittest.TestCase):
    def recovery_fixture(self):
        pre=c.life.read_bound(c.runner.PRE,c.runner.PRE_SHA)
        info=pre['artifacts']['dut']['metadata']; blob=c.runner.ELF.read_bytes()
        pc=info['symbols']['canon_recovery_site']; words=c.recovery_words(blob,pc)
        rows=[]; activities={}
        for i,word in enumerate(words):
            rows.extend(dict(event=e,order=str(i+80),pc=hex(pc+i*4),insn=hex(word),trap='0')
                for e in ('arch_start','retire'))
            a=ArchActivity(word,allocations=1,completions=1,eew=3,vl=16,vstart=0)
            if i!=2:
                for k in range(16):
                    a.writes.append(VectorWrite(row=k,cycle=100+k,arch_seq=80+i,vid=i,lane=k%4,
                        source=0,instruction=word,eew=3,addr=(10+i)*4+k//4,be=255,
                        data=c.runner.p.recovery_word(k)*(i+1)&((1<<64)-1),known_be=255))
            activities[i+80]=a
        return rows,activities,info,blob

    def test_recovery_full_bytes(self):
        rows,activities,info,blob=self.recovery_fixture()
        seqs,result=c.recovery_gate(rows,activities,info,blob)
        self.assertEqual(seqs,{80,81,82})
        self.assertEqual(result['source_bytes'],128)
        self.assertEqual(result['destination_bytes'],128)
        for mutation in ('missing','value','unknown','extra_store','metadata',
                         'extra_be','write_eew','wrong_lane','wrong_addr','vl','eew','alloc','done'):
            bad=copy.deepcopy(activities)
            if mutation=='missing': bad[81].writes.pop()
            elif mutation in ('value','unknown','extra_be','write_eew','wrong_lane','wrong_addr'):
                from dataclasses import replace
                w=bad[81].writes[0]
                changes={'value':{'data':w.data^1},'unknown':{'known_be':0},
                    'extra_be':{'be':511},'write_eew':{'eew':2},
                    'wrong_lane':{'lane':4},'wrong_addr':{'addr':12*4}}
                bad[81].writes[0]=replace(w,**changes[mutation])
            elif mutation=='extra_store': bad[82].writes=bad[81].writes[:1]
            elif mutation=='vl': bad[80].vl=15
            elif mutation=='eew': bad[80].eew=2
            elif mutation=='alloc': bad[80].allocations=2
            elif mutation=='done': bad[80].completions=2
            else: bad[80].vstart=1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                c.recovery_gate(rows,bad,info,blob)

    def test_recovery_duplicate_request_or_trap(self):
        rows,activities,info,blob=self.recovery_fixture()
        with self.assertRaises(ValueError): c.recovery_gate(rows+[rows[0]],activities,info,blob)
        bad=copy.deepcopy(rows); bad[1]['trap']='1'
        with self.assertRaises(ValueError): c.recovery_gate(bad,activities,info,blob)

    def test_recovery_lifetime_negative(self):
        fields=['arch_seq','cycle','event','vid','eew','vl','vstart']
        records=[dict(zip(fields,values)) for values in [
            (80,1,'alloc',0,3,16,0),(80,2,'write',0,3,16,0),(80,3,'done',0,3,16,0)]]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lifetime.csv'
            def write(rows):
                with path.open('w',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
            write(records); c.recovery_lifetimes(path,{80})
            cases=[records[:-1],records+[records[0]],records+[records[2]],
                records+[dict(records[1],cycle=4)], [records[1]]+records,
                [dict(records[0],cycle=3)]+records[1:],
                [records[0],dict(records[1],vid=1),records[2]],
                [records[0],dict(records[1],eew=2),records[2]]]
            for pos in (0,2):
                for field,value in [('eew',2),('vl',15),('vstart',1)]:
                    bad=copy.deepcopy(records); bad[pos][field]=value; cases.append(bad)
            for rows in cases:
                write(rows)
                with self.assertRaises(ValueError): c.recovery_lifetimes(path,{80})

    def test_projection_preserves_all_nonrecovery_rows(self):
        recovery_rows,activities,info,blob=self.recovery_fixture()
        fields=['event','order','pc','insn','trap','mem_addr','mem_wmask','mem_wdata','cycle']
        rows=[]
        for i in range(3):
            r=dict(recovery_rows[i*2],cycle=str(i+1)); rows.append(r)
            r=dict(recovery_rows[i*2+1],order=str(i),cycle=str(i+1)); rows.append(r)
        rows[-1].update(mem_addr='80001000',mem_wmask='ff',mem_wdata='1')
        vrfields=['event','arch_seq','insn','cycle']; retained=[
            dict(event='config',arch_seq='0',insn='0',cycle='0'),
            dict(event='write',arch_seq='7',insn='00b5045b',cycle='1'),
            dict(event='alloc',arch_seq='8',insn='02007507',cycle='2'),
            dict(event='alloc',arch_seq='9',insn='c2002573',cycle='3')]
        removed=[dict(event='alloc',arch_seq=str(80+i),insn=hex(a.instruction),cycle='4')
            for i,a in enumerate(activities.values())]
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory); commit=output/'commit.csv'; vector=output/'vector.csv'
            for path,fs,data in ((commit,fields,rows),(vector,vrfields,retained+removed)):
                with path.open('w',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=fs); writer.writeheader(); writer.writerows(data)
            calls=[]
            def owner(cp,vp,name,metadata):
                self.assertEqual(cp,commit); self.assertIs(metadata,info)
                with vp.open(newline='') as stream: self.assertEqual(list(csv.DictReader(stream)),retained)
                calls.append(name); return {'status':'MOCK_OWNER_ONLY'}
            with patch.object(c,'_parse_vector_trace',return_value=(4,1024,activities)), \
                patch.object(c,'recovery_lifetimes'), \
                patch.object(c.runner.p.audit,'custom_write_lifetimes') as lifetime, \
                patch.object(c.runner.p,'oracle',return_value={'runtime_traces':owner}):
                c.native_architecture(commit,vector,info,blob,output)
                lifetime.assert_called_once_with(vector,[])
            self.assertEqual(calls,['gap71_qbs_fault'])

    def test_preedge_fault_drain_retry(self):
        result=c.cycle_gate(samples())
        self.assertEqual(result['accepted_AR'],1)
        self.assertEqual(result['accepted_RLAST'],1)
        self.assertFalse(result['per_beat_protocol_certified'])

    def test_fault_gate_negative(self):
        for index,name,value in [(3,'ar_stalled_q',1),(3,'burst_fifo_count_q',1),
            (1,'physical_check_valid_o',1),(1,'axi_ar_valid_o',1),
            (1,'mmu_exception_i.cause',5),(1,'mmu_exception_i.tval',0x40002080),
            (1,'planner_fault_mmu_exception.cause',5),(2,'response_fault_event',1),
            (2,'response_drain_q',1),(4,'physical_range_allowed_i',0)]:
            bad=copy.deepcopy(samples()); bad[index][1][name]=value
            with self.subTest(name=name), self.assertRaises(ValueError): c.cycle_gate(bad)

    def test_missing_unknown_and_truncation(self):
        bad=samples(); del bad[0][1]['ar_stalled_q']
        with self.assertRaises(ValueError): c.cycle_gate(bad)
        bad=samples(); bad[1][1]['mmu_exception_i.cause']=None
        with self.assertRaises(ValueError): c.cycle_gate(bad)
        with self.assertRaises(ValueError): c.cycle_gate(samples()[:4])
        with self.assertRaises(ValueError): c.cycle_gate(samples(),last_cycle=7)
        with self.assertRaises(ValueError): c.cycle_gate(samples(),last_cycle=6)
        reset=frame(); reset['rst_ni']=0
        with self.assertRaises(ValueError): c.cycle_gate([(0,reset)]+samples(),last_cycle=6)

    def test_duplicate_fault_or_ack(self):
        bad=samples(); bad.insert(2,copy.deepcopy(bad[1]))
        with self.assertRaises(ValueError): c.cycle_gate(bad)
        bad=samples(); bad.insert(4,copy.deepcopy(bad[3]))
        with self.assertRaises(ValueError): c.cycle_gate(bad)

    def test_real_linked_recovery_sites(self):
        pre=c.life.read_bound(c.runner.PRE,c.runner.PRE_SHA)
        info=pre['artifacts']['dut']['metadata']
        words=c.recovery_words(c.runner.ELF.read_bytes(),info['symbols']['canon_recovery_site'])
        self.assertEqual(len(words),3)
        with self.assertRaises(ValueError):
            c.recovery_words(c.runner.ELF.read_bytes(),info['symbols']['canon_recovery_site']+4)

    def test_real_pinned_markers(self):
        lines=['CANONICAL_QBS_OBJECT '+c.SCOPE+'.'+n for n in c.runner.PROBE_NAMES]+['CANONICAL_QBS_PROBE_READY']
        c.markers('\n'.join(lines))
        for bad in (lines[:-1],lines+[lines[0]],lines+['CANONICAL_QBS_PROBE_REJECT capacity']):
            with self.assertRaises(ValueError): c.markers('\n'.join(bad))

    def test_bool_terminal_rejected(self):
        for value in (False,True,None,-1):
            with self.assertRaises(ValueError): c.terminal_gate(dict(returncode=value),{},{},Path('/unused'))


if __name__ == '__main__': unittest.main()
