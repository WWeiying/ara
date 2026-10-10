import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import run_scalar_fpu_fma_arbiter792 as r
import collect_scalar_fpu_fma_arbiter792 as c


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof=r.source_contract()
        cls.decl={n:dict(width=w,code=n,type='wire') for n,w in c.paths(cls.proof).items()}

    def state(self,**updates):
        values={n:0 for n in self.decl}
        for name in ('fpu_in_ready','fpu_out_ready'):values[c.GEN+'.'+name]=1
        values[c.SCOPE+'.fpu_ready_o']=1
        values.update(updates)
        return {n:format(v,'0%db'%self.decl[n]['width']) for n,v in values.items()}

    def owner(self,base,op,tid,abc):
        d={};d[c.SCOPE+'.fpu_valid_i']=1;d[c.GEN+'.fpu_in_valid']=1
        d[c.GEN+'.fpu_op_d']=self.proof['fpnew_ops'][op];d[c.GEN+'.fpu_tag_d']=tid
        names={'FMADD':'FMADD','DIV':'FDIV','CLASSIFY':'FCLASS'}
        fields=dict(operation=self.proof['ariane_ops'][names[op]],operand_a=abc[0],operand_b=abc[1],imm=abc[2],trans_id=tid)
        d[c.SCOPE+'.fu_data_i']=sum(fields.get(n,0)<<right for n,(left,right) in self.proof['fu_layout']['fields'].items())
        for n,v in zip('abc',abc):d[c.GEN+'.operand_'+n+'_d']=v
        result=dict(base);result.update(self.state(**d));return result

    def fixture(self):
        a,b=r.oracle.C_VALUES;one=0x3ff0000000000000;dv=0x3ffaaaaaaaab5555
        wants=[dict(op='DIV',pc=4,result=one,abc=[dv,dv,None]),
               dict(op='FMADD',pc=8,result=a,abc=[0,one,a]),dict(op='FMADD',pc=12,result=b,abc=[0,one,b])]
        first=self.owner(self.state(),'DIV',0,[dv,dv,0]);second=self.owner(self.state(),'FMADD',1,[0,one,a])
        capture=self.owner(self.state(),'FMADD',2,[0,one,b])
        def setv(s,path,value):s[path]=format(value,'0%db'%self.decl[path]['width'])
        def output(s,tid,value,valid,ready):
            for path,v in [(c.SCOPE+'.fpu_valid_o',1),(c.GEN+'.fpu_out_valid',1),
                (c.SCOPE+'.fpu_trans_id_o',tid),(c.SCOPE+'.result_o',value),
                (c.BULK+'.opgrp_out_valid',valid),(c.BULK+'.opgrp_out_ready',ready)]:setv(s,path,v)
        setv(capture,c.GEN+'.fpu_in_ready',0);setv(capture,c.SCOPE+'.fpu_ready_o',0)
        setv(capture,c.GEN+'.hold_inputs',1);output(capture,0,one,3,2)
        held=self.state(**{c.SCOPE+'.state_q':1,c.GEN+'.use_hold':1,c.GEN+'.fpu_in_valid':1,
            c.GEN+'.fpu_in_ready':0,c.SCOPE+'.fpu_ready_o':0,c.GEN+'.fpu_tag_q':2})
        for n,v in zip('abc',[0,one,b]):setv(held,c.GEN+'.operand_'+n+'_q',v)
        after_capture=dict(held);stall=dict(held);output(stall,1,a,1,1)
        release=dict(held);setv(release,c.GEN+'.fpu_in_ready',1);setv(release,c.SCOPE+'.fpu_ready_o',1)
        after_release=dict(release);setv(after_release,c.SCOPE+'.state_q',0)
        final=self.state();output(final,2,b,1,1)
        return wants,[(0,first,dict(first)),(1,second,dict(second)),(2,capture,after_capture),
                      (3,stall,dict(stall)),(4,release,after_release),(5,final,dict(final))]

    def test_source_complete_packed_layout_and_enum(self):
        self.assertEqual(self.proof['fu_layout']['width'],207)
        self.assertEqual(self.proof['fu_layout']['fields']['imm'],[66,3])
        self.assertEqual(self.proof['op_width'],5)

    def test_complete_fma_capture_stable_release_output(self):
        wants,edges=self.fixture();a=c.audit_edges(self.decl,edges,wants,self.proof)
        self.assertEqual(a['FMA_hold_count'],1);self.assertEqual(len(a['completed']),3)

    def rejection(self,mutation):
        wants,edges=self.fixture();mutation(edges)
        with self.assertRaises(ValueError):c.audit_edges(self.decl,edges,wants,self.proof)

    def test_wrong_c_capture_rejected(self):
        self.rejection(lambda e:e[2][2].update({c.GEN+'.operand_c_q':'0'*64}))

    def test_stall_a_changed_rejected(self):
        self.rejection(lambda e:e[3][1].update({c.GEN+'.operand_a_q':'1'.rjust(64,'0')}))

    def test_stall_b_changed_rejected(self):
        self.rejection(lambda e:e[3][1].update({c.GEN+'.operand_b_q':'0'*64}))

    def test_stall_tag_changed_rejected(self):
        self.rejection(lambda e:e[3][1].update({c.GEN+'.fpu_tag_q':'011'}))

    def test_active_unknown_rejected(self):
        self.rejection(lambda e:e[3][1].update({c.GEN+'.operand_c_q':'x'*64}))

    def test_pending_flush_rejected(self):
        self.rejection(lambda e:e[3][1].update({c.SCOPE+'.flush_i':'1'}))

    def test_wrong_retired_native_result_rejected(self):
        self.rejection(lambda e:e[5][1].update({c.SCOPE+'.result_o':'0'*64}))

    def test_wrong_native_flags_rejected(self):
        self.rejection(lambda e:e[5][1].update({c.SCOPE+'.fpu_exception_o':format(1<<139,'0203b')}))

    def exception_bits(self,field,char):
        bits=list('0'*203);left,right=self.proof['exception_layout']['fields'][field]
        bits[202-left:203-right]=[char]*(left-right+1)
        return ''.join(bits)

    def test_unknown_each_driven_exception_field_rejected(self):
        for name in ('cause','valid','tval'):
            for char in ('x','z'):
                with self.subTest(name=name,char=char):
                    self.rejection(lambda e:e[5][1].update({c.SCOPE+'.fpu_exception_o':self.exception_bits(name,char)}))

    def test_nonzero_each_driven_exception_field_rejected(self):
        for name in ('cause','valid','tval'):
            with self.subTest(name=name):
                self.rejection(lambda e:e[5][1].update({c.SCOPE+'.fpu_exception_o':self.exception_bits(name,'1')}))

    def test_unused_members_unknown_preserved_unobserved(self):
        wants,edges=self.fixture()
        for _,before,after in edges:
            for state in (before,after):
                bits=list(state[c.SCOPE+'.fpu_exception_o'])
                bits[128:202]=list('x'*74)
                state[c.SCOPE+'.fpu_exception_o']=''.join(bits)
        result=c.audit_edges(self.decl,edges,wants,self.proof)
        self.assertEqual(result['exception_unobserved'],dict(tval2='UNOBSERVED',tinst='UNOBSERVED',gva='UNOBSERVED'))
        self.assertEqual(len(result['completed']),3)

    def test_unused_unknown_cannot_hide_driven_error(self):
        for name in ('cause','valid','tval'):
            bits=list(self.exception_bits(name,'x'));bits[128:202]=list('z'*74)
            with self.subTest(name=name):
                self.rejection(lambda e:e[5][1].update({c.SCOPE+'.fpu_exception_o':''.join(bits)}))

    def test_wrong_completed_tid_rejected(self):
        self.rejection(lambda e:e[5][1].update({c.SCOPE+'.fpu_trans_id_o':'111'}))

    def test_no_competition_fma_capture_rejected(self):
        self.rejection(lambda e:e[2][1].update({c.BULK+'.opgrp_out_valid':'00010'}))

    def test_boolean_terminal_returncode_rejected(self):
        run=r.life.OUT/'fma-terminal-test-never-run'
        state=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=False,timeout=False,
            case=r.NAME,coverage_admitted=False,admission_performed=False,terminal_oracle_verified=False)
        with patch.object(Path,'read_bytes',return_value=json.dumps(state).encode()):
            with self.assertRaises(ValueError):c.terminal_gate(run,{})

    def test_missing_completion_rejected(self):
        wants,edges=self.fixture()
        with self.assertRaises(ValueError):c.audit_edges(self.decl,edges[:-1],wants,self.proof)

    def test_no_hold_is_functional_not_triggered(self):
        one=0x3ff0000000000000;a=r.oracle.C_VALUES[0]
        want=dict(op='FMADD',pc=4,result=a,abc=[0,one,a]);before=self.owner(self.state(),'FMADD',0,want['abc'])
        after=self.state(**{c.SCOPE+'.fpu_valid_o':1,c.GEN+'.fpu_out_valid':1,c.SCOPE+'.result_o':a,
                           c.BULK+'.opgrp_out_valid':1,c.BULK+'.opgrp_out_ready':1})
        audit=c.audit_edges(self.decl,[(0,before,before),(1,after,after)],[want],self.proof)
        self.assertFalse(audit['FMA_hold_observed'])

    def test_idle_ownerless_flush_allowed(self):
        wants,edges=self.fixture();idle=self.state(**{c.SCOPE+'.flush_i':1})
        a=c.audit_edges(self.decl,[(-1,idle,idle)]+edges,wants,self.proof)
        self.assertEqual(a['idle_ownerless_flush_times'],[-1])

    def test_wrong_probe_width_rejected(self):
        d=copy.deepcopy(self.decl);d[c.GEN+'.fpu_op_d']['width']=4;w,e=self.fixture()
        with self.assertRaises(ValueError):c.audit_edges(d,e,w,self.proof)

    def test_stdout_echo_not_execution(self):
        contract='[ARA_CONTRACT] requests=0 responses=0 exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'
        text='puts "FMA_ARB_PROBE_ERROR $failure"\nFMA_ARB_PROBE_READY\nCore Test *** SUCCESS ***\n'+contract
        c.stdout_gate(text)
        for extra in ('\nFMA_ARB_PROBE_READY','\nFMA_ARB_PROBE_ERROR actual','\nUVM_ERROR actual'):
            with self.assertRaises(ValueError):c.stdout_gate(text+extra)
        with self.assertRaises(ValueError):c.stdout_gate(text.replace('mmu_request_cycles=0','mmu_request_cycles=1'))

    def test_private_lifecycle_real_subprocess_constants(self):
        # Verify namespace only: never invoke its run/Popen.
        from types import FunctionType
        ns=dict(r.lifecycle.lifecycle_namespace.__globals__,PRE=r.PRE,ELF_SHA='elf',IMAGE_SHA=r.IMAGE_SHA,
                BUDGET=120,NAME=r.NAME,command=r.command)
        record=dict(command=r.command(r.life.OUT/'fma-test-unlaunched'),service=r.SERVICE)
        private=FunctionType(r.lifecycle.lifecycle_namespace.__code__,ns)(r.life.OUT/'fma-test-unlaunched',record)
        self.assertEqual(private['BUDGET'],120)
        self.assertIs(private['subprocess'].STDOUT,subprocess.STDOUT)
        self.assertIs(private['run'].__globals__,private)

    def test_command_fixed_elf_probe_and_no_fsdb(self):
        cmd=r.command(r.life.OUT/'fma-test-unlaunched')
        self.assertIn('+PRELOAD='+str(r.ELF),cmd);self.assertIn('+NO_FSDB',cmd)
        self.assertEqual(cmd[-2:],['-do',str(r.PROBE)])


if __name__=='__main__':unittest.main()
