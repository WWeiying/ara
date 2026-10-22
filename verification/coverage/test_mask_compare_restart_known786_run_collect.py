import copy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import collect_mask_compare_restart_known786 as c


class KnownOldGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=c.runner.preflight()
        cls.reference=c.reference_prefix(cls.pre)

    def fixture(self):
        symbols=self.pre['symbols']; activities={}; mapping={}; rows=[]
        names=('mc_init_a','mc_init_b','mc_clear24','mc_load2','mc_clear1','mc_compare','mc_xor',
               'mc_mask_store','mc_a_read','mc_b_read','mc_x_read','mc_v2_read')
        phase=0
        for index,commit in enumerate(self.reference):
            name=next((n for n in names if commit.pc==symbols[n]),None)
            if name is None: continue
            seq=len(mapping); mapping[seq]=index
            writer=bool(commit.vector_writes)
            vl=64 if name in ('mc_compare','mc_xor') else 8 if name=='mc_mask_store' else 128
            start=c.p.STARTS[phase] if name=='mc_compare' else 0
            if name=='mc_compare': phase+=1
            vd=next(iter(commit.vector_writes)) if writer else 0
            a=c.vc.ArchActivity(commit.instruction,allocations=1,completions=1,
                use_vd=writer,vd=vd,eew=0 if writer else None,vl=vl if writer else None,
                vstart=start if writer else None)
            source=4 if name in ('mc_init_a','mc_init_b','mc_load2','mc_clear1') else 2 if name=='mc_compare' else 1
            for reg,value in commit.vector_writes.items():
                for word in range(4):
                    for lane in range(4):
                        data=0; be=0
                        for byte in range(8):
                            b=word*32+c.vc._deshuffle_byte(lane*8+byte,4,0)
                            if name=='mc_xor' and b>=64: continue
                            be|=1<<byte; data|=((value>>(8*b))&255)<<(8*byte)
                        if be:
                            a.writes.append(c.vc.VectorWrite(row=len(a.writes),cycle=seq*3+1,arch_seq=seq,
                                vid=seq%8,lane=lane,source=source,instruction=commit.instruction,
                                eew=0,addr=reg*4+word,be=be,data=data,known_be=255))
            activities[seq]=a
            row=dict(event='alloc',arch_seq=str(seq),insn='%08x'%commit.instruction,vl=str(vl),
                vstart=str(start),eew='0',vd=str(vd),use_vd=str(int(writer)),nr_lanes='4',
                vlen_bits='1024',vid=str(seq%8),cycle=str(seq*3))
            rows += [row,dict(row,event='done',cycle=str(seq*3+2))]
        return activities,mapping,rows

    def native(self,activities,mapping,rows):
        return c.native_state(self.reference,activities,mapping,self.pre['symbols'],rows)

    def test_actual_reference_prefix(self):
        self.assertEqual(len(self.reference),58822)
        self.assertEqual(self.pre['counts']['checks'],2705)

    def test_integrated_all13_native_writers_and15_stores(self):
        proof=self.native(*self.fixture())
        self.assertEqual(proof['primary_writers'],13)
        self.assertEqual(sum(proof['counts'].values()),28)
        self.assertEqual(proof['counts']['mc_v2_read'],3)

    def test_active_and_prestart_strict(self):
        before=int.from_bytes(c.p.old_bytes(0),'little')
        for start in c.p.STARTS:
            gold=int.from_bytes(c.p.mask_gold(start),'little')
            after=(before&~((1<<64)-1))|gold
            c.mask_postimage(before,after,start)
            for bit in (0,start,63):
                with self.assertRaises(Exception): c.mask_postimage(before,after^(1<<bit),start)

    def test_tail_VLMAX_computation_and_old_one(self):
        before=int.from_bytes(c.p.old_bytes(0),'little'); gold=int.from_bytes(c.p.mask_gold(4),'little')
        after=(before&~((1<<64)-1))|gold
        a,b=c.p.source_bytes(0),c.p.source_bytes(1)
        for i in range(64,128):
            after=(after&~(1<<i))|(int(a[i]<b[i])<<i)
        c.mask_postimage(before,after,4)
        c.mask_postimage(before,after|(1<<1000),4)
        illegal=next(i for i in range(64,128) if before>>i&1 and a[i]<b[i])
        base=(before&~((1<<64)-1))|gold
        with self.assertRaises(Exception): c.mask_postimage(before,base&~(1<<illegal),4)
        high=next(i for i in range(128,1024) if before>>i&1)
        with self.assertRaises(Exception): c.mask_postimage(before,base&~(1<<high),4)

    def test_wrong_unknown_prestate_rejected(self):
        before=int.from_bytes(c.p.old_bytes(0),'little')
        for value in (None,0,before^1):
            with self.assertRaises(Exception): c.mask_postimage(value,before,4)

    def test_native_unknown_write_rejected(self):
        acts,mapping,rows=self.fixture()
        first=next(a for a in acts.values() if a.writes)
        first.writes[0]=replace(first.writes[0],known_be=0)
        with self.assertRaises(Exception): self.native(acts,mapping,rows)

    def test_native_adjacent_corruption_rejected(self):
        acts,mapping,rows=self.fixture()
        seq=next(s for s,i in mapping.items() if self.reference[i].pc==self.pre['symbols']['mc_load2'])
        acts[seq].writes[0]=replace(acts[seq].writes[0],data=acts[seq].writes[0].data^1)
        with self.assertRaises(Exception): self.native(acts,mapping,rows)

    def test_native_prestart_corruption_rejected(self):
        acts,mapping,rows=self.fixture()
        seq=next(s for s,i in mapping.items() if self.reference[i].pc==self.pre['symbols']['mc_compare'])
        # Physical lane0 byte0 is architectural byte0 for EW8.
        acts[seq].writes[0]=replace(acts[seq].writes[0],data=acts[seq].writes[0].data^1)
        with self.assertRaises(Exception): self.native(acts,mapping,rows)

    def test_store_raw_context_mutations(self):
        acts,mapping,rows=self.fixture()
        seq=next(s for s,i in mapping.items() if self.reference[i].pc==self.pre['symbols']['mc_v2_read'])
        insn=self.reference[mapping[seq]].instruction
        c.request_context(rows,seq,insn,128,0,0,False)
        for key,value in (('vl','64'),('eew','3'),('vstart','4'),('vd','2'),('use_vd','1'),('insn','00000000')):
            changed=copy.deepcopy(rows)
            next(r for r in changed if r['arch_seq']==str(seq) and r['event']=='alloc')[key]=value
            with self.assertRaises(Exception): c.request_context(changed,seq,insn,128,0,0,False)

    def test_missing_duplicate_backend_rejected(self):
        acts,mapping,rows=self.fixture()
        seq=next(s for s,i in mapping.items() if self.reference[i].pc==self.pre['symbols']['mc_compare'])
        missing=dict(acts); missing.pop(seq)
        with self.assertRaises(Exception): self.native(missing,mapping,rows)
        row=next(r for r in rows if r['arch_seq']==str(seq) and r['event']=='alloc')
        with self.assertRaises(Exception): self.native(acts,mapping,rows+[dict(row)])

    def test_no_backend_not_pass(self):
        with self.assertRaises(Exception): c.native_state([],{}, {}, {},[])

    def test_missing_terminal_not_pass(self):
        with self.assertRaises(Exception): c.terminal(c.life.OUT/'nonexistent-known-old-terminal',{})

    def terminal_fixture(self):
        run=c.life.OUT/'synthetic-known-old-terminal'
        manifest=dict(command=c.runner.command(run))
        state=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,
            case=c.runner.NAME,coverage_admitted=False,admission_performed=False,pid=42)
        started=dict(command=manifest['command'],input_elf=str(c.runner.ELF),elf_sha256=c.runner.ELF_SHA,
            image=str(c.life.IMAGE),image_sha256=c.runner.IMAGE_SHA,pid=42,process_group=42,
            budget_s=360,foreground_lifetime=True)
        identity=dict(pid=42,exe=str(c.life.IMAGE.resolve()),executable_sha256=c.runner.IMAGE_SHA,
            cwd=str(run),command=manifest['command'],service=c.runner.SERVICE,runtime66_verified=True,
            cgroup='0::/user.slice/'+c.runner.SERVICE)
        files={'simulation-status.json':state,'manifest.json':dict(manifest,
            authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'),
            'started.json':started,'live-simv-identity.json':identity}
        return run,manifest,files

    def test_exact_terminal_and_live_receipt(self):
        run,manifest,files=self.terminal_fixture()
        with patch.object(Path,'read_bytes',lambda path:json.dumps(files[path.name]).encode()):
            self.assertEqual(c.terminal(run,manifest)['returncode'],0)

    def test_live_receipt_mutations_rejected(self):
        for key,value in (('pid',43),('exe','/foreign/simv'),('executable_sha256','0'*64),
                          ('cwd','/foreign'),('command',[]),('runtime66_verified',False),
                          ('cgroup','0::/unrelated.service')):
            run,manifest,files=self.terminal_fixture()
            files['live-simv-identity.json'][key]=value
            with patch.object(Path,'read_bytes',lambda path:json.dumps(files[path.name]).encode()):
                with self.assertRaises(Exception): c.terminal(run,manifest)

    def test_timeout_nonzero_unknown_OSstatus_rejected(self):
        for key,value in (('timeout',True),('returncode',1),('returncode',None)):
            run,manifest,files=self.terminal_fixture()
            files['simulation-status.json'][key]=value
            with patch.object(Path,'read_bytes',lambda path:json.dumps(files[path.name]).encode()):
                with self.assertRaises(Exception): c.terminal(run,manifest)

    def test_live_proc_NUL_command_and_cgroup(self):
        import os
        out=c.life.OUT/'synthetic-live-known-old'
        manifest=dict(command=c.runner.command(out))
        original=Path.resolve
        def resolve(path,strict=False):
            if str(path)=='/proc/42/exe': return original(c.life.IMAGE,strict=strict)
            if str(path)=='/proc/42/cwd': return out
            return original(path,strict=strict)
        with patch.object(Path,'resolve',resolve),patch.object(Path,'read_bytes',
                return_value=b'\0'.join(x.encode() for x in manifest['command'])+b'\0'),\
                patch.object(Path,'read_text',return_value='0::/user.slice/'+c.runner.SERVICE),\
                patch.object(c.life,'digest',return_value=c.runner.IMAGE_SHA),patch.object(os,'getpgid',return_value=42):
            self.assertTrue(c.runner.live_identity(42,out,manifest)['runtime66_verified'])

    def test_actual786_baseline(self):
        _,bits,before,targets,_=c.runner.baseline(self.pre)
        self.assertEqual(len(bits['tests']),786)
        self.assertEqual(len(before),4)
        self.assertEqual(len(targets),8)
        self.assertEqual(sum(len(t['missing_coordinates']) for t in targets),176)

    def test_budget_command_and_no_launch_without_review(self):
        self.assertEqual(c.runner.BUDGET,360)
        cmd=c.runner.command(c.life.OUT/'unused-known-old')
        self.assertIn('+NO_FSDB',cmd); self.assertIn('-ucli',cmd)
        self.assertEqual(cmd[-1],str(c.runner.PROBE))
        result=subprocess.run(['python3','-B',c.runner.__file__,'run','--output',str(c.life.OUT/'unused-known-old'),
            '--seal','0'*64],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((c.life.OUT/'unused-known-old').exists())

    def tcl(self,unavailable=False,missing=False):
        code='''
set runs 0
set seen [list]
proc show {args} {return signal}
proc dump {args} {
    global seen
    if {[lindex $args 0] eq "-add"} {
        set path [lindex $args 1]
        lappend seen $path
        if {MISSING && [string match *.operand_request_i $path]} {return 0}
        if {UNAVAILABLE && [string match *.rdata $path]} {return 0}
    }
    return 1
}
proc run {} {global runs; incr runs}
'''.replace('MISSING',str(int(missing))).replace('UNAVAILABLE',str(int(unavailable)))
        code+='\nsource {'+str(c.runner.PROBE)+'}\n'
        code+='if {$runs != 1} {exit 2}\nputs "HOST_SCOPE_COMPLETE"\n'
        result=subprocess.run(['tclsh'],input=code,text=True,capture_output=True)
        return result

    def test_actual_Tcl_bracketed_scope_full_flow(self):
        result=self.tcl()
        self.assertEqual(result.returncode,0,result.stderr)
        required,optional=c.probe_objects()
        self.assertEqual([s.removeprefix('MC_PROBE_REQUIRED ') for s in result.stdout.splitlines()
            if s.startswith('MC_PROBE_REQUIRED ')],required)
        self.assertEqual([s.removeprefix('MC_PROBE_OPTIONAL_CAPTURED ') for s in result.stdout.splitlines()
            if s.startswith('MC_PROBE_OPTIONAL_CAPTURED ')],optional)

    def test_missing_required_Tcl_fails_before_run(self):
        result=self.tcl(missing=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('MC_PROBE_ERROR',result.stdout)
        self.assertNotIn('MC_PROBE_READY',result.stdout)

    def test_optional_unavailable_explicit_no_false_capture(self):
        result=self.tcl(unavailable=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.count('MC_PROBE_OPTIONAL_UNAVAILABLE '),4)


if __name__=='__main__': unittest.main()
