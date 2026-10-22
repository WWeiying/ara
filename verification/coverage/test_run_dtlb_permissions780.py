"""Prepared host/probe and strict collector models; never launches a simulator."""
import copy
from pathlib import Path
import subprocess
import unittest

import run_dtlb_permissions780 as run
import collect_dtlb_permissions780 as collect


def record():
    out=run.life.OUT/'dtlb-permissions780-test-only'
    return dict(schema=run.SCHEMA,case=run.CASE,output=str(out),timeout_s=1200,
        systemd_runtime_max_s=1260,automatic_retry=False,coverage_admitted=False,
        preflight=str(run.PRE),preflight_seal=run.PRE_SHA,baseline_seal=run.BASE_SHA,
        service='ara-dtlb-permissions780-test.service',command=run.command(out))


class Host(unittest.TestCase):
    def test_frozen_private_lifecycle(self):
        for name in ('command','validate_record','check','process_identity','run'):
            self.assertIs(getattr(run,name).__code__,getattr(run.host,name).__code__)
        self.assertNotEqual(run.host.PRE,run.PRE)
        self.assertEqual(run.namespace['pre'].BASE_SHA,run.BASE_SHA)

    def test_exact_command(self):
        r=record();self.assertEqual(run.validate_record(r),Path(r['output']))
        self.assertIn('+COMMIT_TOHOST=80001000',r['command'])
        self.assertIn('+NO_FSDB',r['command'])
        self.assertEqual(r['command'][-2:],['-do',str(run.PROBE)])

    def test_wrong_baseline(self):
        r=record();r['baseline_seal']=run.host.pre.BASE_SHA
        with self.assertRaises(ValueError):run.validate_record(r)

    def test_wrong_timeout(self):
        for value in (False,600):
            r=record();r['timeout_s']=value
            with self.assertRaises(ValueError):run.validate_record(r)

    def test_terminal_bool_is_not_zero(self):
        r=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,
               case=run.CASE,coverage_admitted=False,automatic_retry=False)
        collect.terminal_gate(r);r['returncode']=False
        with self.assertRaises(ValueError):collect.terminal_gate(r)

    def test_plain_tcl_probe(self):
        text='proc show {args} {}\nproc dump {args} {return 1}\nproc run {} {}\n'
        text+=f'source {{{run.PROBE}}}\n'
        result=subprocess.run(['tclsh'],input=text,text=True,capture_output=True,check=True)
        self.assertEqual(result.stdout.splitlines().count('DTLB_PERMISSIONS_READY'),1)
        self.assertEqual(len([x for x in result.stdout.splitlines() if x.startswith('DTLB_PERMISSIONS_OBJECT ')]),37)


def wave_fixture():
    widths={'ara_tb.clk':1,'ara_tb.rst_n':1,collect.native.MONITOR:64,
        collect.SCOPE+'.content_q':2048,collect.SCOPE+'.tags_q':976}
    widths.update({collect.SCOPE+'.'+k:w for k,w in dict(update_i=189,replace_en=16,lu_hit_o=1,
        flush_i=1,asid_to_be_flushed_i=16,vaddr_to_be_flushed_i=64).items()})
    widths.update({collect.MMU+'.'+k:w for k,w in dict(ld_st_priv_lvl_i=2,sum_i=1,mxr_i=1,
        lsu_is_store_i=1,lsu_req_i=1,lsu_req_q=1,lsu_vaddr_i=64,lsu_valid_o=1,
        lsu_exception_o=203,dtlb_pte_q=64,dtlb_hit_q=1).items()})
    decl={name:dict(code=name,width=w) for name,w in widths.items()}
    state={name:'0'*w for name,w in widths.items()};state['ara_tb.rst_n']='1'
    frames=[(0,decl)];cycle=0;contents=[0]*16;tags=[0]*16
    def setv(s,name,value):s[name]=format(value,f'0{widths[name]}b')
    def frame(update=0,mask=0,fence=0,asid=0,owner=None,pte=0,error=False):
        nonlocal cycle,state
        cycle+=1;before=dict(state);before['ara_tb.clk']='0'
        setv(before,collect.native.MONITOR,cycle)
        for field,value in (('update_i',update),('replace_en',mask),('flush_i',fence),('asid_to_be_flushed_i',asid)):
            setv(before,collect.SCOPE+'.'+field,value)
        if error:
            setv(before,collect.MMU+'.lsu_req_q',1);setv(before,collect.MMU+'.lsu_valid_o',1)
            setv(before,collect.MMU+'.lsu_exception_o',(13<<139)|(run.software.p.address(0)<<75)|1)
        after=dict(before);after['ara_tb.clk']='1'
        if fence and asid==0:tags[:]=[0]*16
        if owner is not None:contents[owner]=pte<<64;tags[owner]=1
        setv(after,collect.SCOPE+'.content_q',sum(c<<(128*i) for i,c in enumerate(contents)))
        setv(after,collect.SCOPE+'.tags_q',sum(t<<(61*i) for i,t in enumerate(tags)))
        frames.append((cycle,before,after));state=after
    for phase,flags in enumerate((0xc7,0x79,0xc7)):
        frame(fence=1)
        for i in range(16):
            pte=run.software.p.pte(run.software.p.pa(17*i),flags)
            update=(1<<188)|(run.software.p.shared.vpn(0,i)<<159)|(1<<143)|(pte<<64)
            frame(update=update,mask=1<<i,owner=i,pte=pte)
        if phase==1:frame(fence=1,asid=1)
    for row in [r for i,r in enumerate(run.software.audit.cases()) if i!=3]:
        pte=run.software.p.pte(run.software.p.pa(0),row['pte_flags'])
        frame(update=(1<<188)|(run.software.p.shared.vpn(0,0)<<159)|(1<<143)|(pte<<64),mask=1,owner=0,pte=pte)
    frame(error=True)
    return frames


class Wave(unittest.TestCase):
    def test_exact_source_bound_model(self):
        result=collect.wave_gate(iter(wave_fixture()))
        self.assertEqual(len(result['replacements']),56)
        self.assertEqual(result['global_asid_fence_cycles'],1)

    def test_wrong_pte_flags(self):
        frames=copy.deepcopy(wave_fixture())
        i=next(i for i,x in enumerate(frames[1:],1) if int(x[1][collect.SCOPE+'.update_i'],2))
        word=int(frames[i][1][collect.SCOPE+'.update_i'],2)^(1<<69)
        frames[i][1][collect.SCOPE+'.update_i']=format(word,'0189b')
        with self.assertRaises(ValueError):collect.wave_gate(iter(frames))

    def test_missing_phase_slot(self):
        frames=wave_fixture();del frames[2]
        with self.assertRaises(ValueError):collect.wave_gate(iter(frames))

    def test_global_invalidated(self):
        frames=copy.deepcopy(wave_fixture())
        i=next(i for i,x in enumerate(frames[1:],1) if int(x[1][collect.SCOPE+'.asid_to_be_flushed_i'],2)==1)
        frames[i][2][collect.SCOPE+'.tags_q']='0'*976
        with self.assertRaises(ValueError):collect.wave_gate(iter(frames))

    def test_empty_wave(self):
        with self.assertRaises((ValueError,StopIteration)):collect.wave_gate(iter([]))


if __name__=='__main__':unittest.main()
