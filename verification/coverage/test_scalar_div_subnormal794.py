import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import build_scalar_div_subnormal794 as o
import run_scalar_div_subnormal794 as r
import collect_scalar_div_subnormal794 as c


class Software(unittest.TestCase):
    def test_actual_spike_all144_results_flags_restore(self):
        pre=r.life.read_bound(r.PRE/'preflight.json',r.PRE_SHA)
        self.assertEqual(o.validate(o.build.parse_spike_commits(r.PRE/'spike.trace'),pre['symbols']),pre['counts'])
        self.assertEqual(pre['counts']['matched_instructions'],10013)

    def test_exact_all_signs_shifts(self):
        for sign in (0,1):
            for k in range(1,53):
                e=o.gold(k,0,sign,0)
                self.assertEqual(e['result'],(sign<<63)|(1<<(52-k)))
                self.assertEqual(e['fflags'],0)

    def test_even_tie_rne_and_rmm(self):
        self.assertEqual(o.gold(1,1,0,0)['result'],1<<51)
        self.assertEqual(o.gold(1,1,0,4)['result'],(1<<51)+1)

    def test_odd_tie_rne(self):
        self.assertEqual(o.gold(1,3,0,0)['result'],(1<<51)+2)
        self.assertEqual(o.gold(1,3,0,1)['result'],(1<<51)+1)

    def test_directed_sign_and_tiny_inexact_flags(self):
        for sign in (0,1):
            for rm in range(5):
                e=o.gold(52,1,sign,rm)
                extra=int((sign and rm==2) or (not sign and rm==3))
                self.assertEqual(e['result'],(sign<<63)|(1+extra))
                self.assertEqual(e['fflags'],3)

    def test_invalid_rm_rejected(self):
        for rm in (-1,5,6,7):
            with self.assertRaises(ValueError):o.gold(1,0,0,rm)

    def test_source_table_and794_compiled_intersection(self):
        evidence=o.source_evidence()
        self.assertEqual(len(evidence['table']),53)
        self.assertEqual(sum(t['capacity'] for t in evidence['targets']),580)
        self.assertEqual(len(evidence['targets']),7)
        self.assertTrue(all(t['file_id'] and t['decl_line'] for t in evidence['targets']))

    def test_wrong_result_gold_rejected_actual_reference(self):
        pre=r.life.read_bound(r.PRE/'preflight.json',r.PRE_SHA)
        expected=o.gold
        def wrong(*args):
            value=expected(*args);value['result']^=1;return value
        with patch.object(o,'gold',side_effect=wrong):
            with self.assertRaises(ValueError):o.validate(o.build.parse_spike_commits(r.PRE/'spike.trace'),pre['symbols'])

    def test_command_fixed_no_fsdb_no_extra_hints(self):
        cmd=r.command(r.life.OUT/'not-launched-subnormal-test')
        self.assertIn('+NO_FSDB',cmd);self.assertIn('+PRELOAD='+str(r.ELF),cmd)
        self.assertEqual(cmd[-2:],['-do',str(r.PROBE)])
        self.assertFalse(any('force' in a for a in cmd))

    def test_real_probe_tcl_paths_once_no_mutations(self):
        program='''proc show {args} {return 1}
proc dump {args} {return 1}
proc run {} {incr ::runs}
set runs 0
source {%s}
if {$runs != 1 || [llength $paths] != 42} {error wrong_paths}
foreach p $paths {if {[string first "\\\\" $p]>=0} {error literal_escape}}
'''%r.PROBE
        p=subprocess.run(['tclsh'],input=program,text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(p.stdout.splitlines().count('SUBNORMAL_DIV_PROBE_READY'),1)
        self.assertFalse(p.stderr)


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof=r.source_contract()
        cls.decl={p:dict(width=w,code=p,type='wire') for p,w in c.probe_widths(cls.proof).items()}

    def state(self):return {p:'0'*v['width'] for p,v in self.decl.items()}

    def fixture(self):
        e=o.gold(26,1,0,3)
        expected=[dict(kind='FMV_X2F',pc=4,result=e['a'],fflags=0,operand_a=e['a'],rm=3),
            dict(kind='FMV_X2F',pc=8,result=e['b'],fflags=0,operand_a=e['b'],rm=3),
            dict(e,kind='DIV',pc=12,operand_a=e['a'],operand_b=e['b']),
            dict(kind='FMV_F2X',pc=16,result=e['result'],fflags=0,operand_a=e['result'],rm=3)]
        edges=[[i,self.state(),self.state()] for i in range(9)]
        def put(s,p,value):s[p]=format(value,'0%db'%self.decl[p]['width'])
        def fu(w,tid):
            values=dict(operand_a=w['operand_a'],operand_b=w.get('operand_b',0),
                operation=self.proof['ariane_ops']['FDIV' if w['kind']=='DIV' else w['kind']],trans_id=tid)
            return sum(values.get(n,0)<<right for n,(left,right) in self.proof['fu_layout']['fields'].items())
        for w,tid,issue,request in zip(expected,(1,2,3,4),(0,1,2,6),(1,2,3,7)):
            before=edges[issue][1];put(before,c.ISSUE+'.fpu_valid_n',1)
            put(before,c.ISSUE+'.fu_data_n',fu(w,tid))
            packed=(w['pc']<<374)|(tid<<371)
            put(before,c.ISSUE+'.issue_instr_i',packed)
            for state in (edges[issue][2],edges[request][1]):
                for n,v in dict(fpu_valid_i=1,fpu_ready_o=1,fu_data_i=fu(w,tid)).items():put(state,c.SCOPE+'.'+n,v)
                for n,v in dict(fpu_in_ready=1,fpu_in_valid=1,fpu_tag_d=tid,
                    fpu_op_d=self.proof['fpnew_ops']['DIV' if w['kind']=='DIV' else 'SGNJ'],fpu_rm_d=w['rm']).items():
                    put(state,c.SCOPE+'.fpu_gen.'+n,v)
                for n,v in zip('abc',(w['operand_a'],w.get('operand_b',0),0)):
                    put(state,c.SCOPE+'.fpu_gen.operand_'+n+'_d',v)
        ex2,post=edges[4][1],edges[4][2];rounds=edges[5][1]
        for n,v in dict(ex2_pipedown=1,vfdsu_ex2_double=1,vfdsu_ex2_expnt_rst=e['exponent_predicate'],
            ex2_result_double_denorm_round_add_num=e['onehot'],ex2_result_denorm_round_add_num=e['onehot']).items():
            put(ex2,c.SRT+'.'+n,v)
        put(post,c.SRT+'.vfdsu_ex3_result_denorm_round_add_num',e['onehot'])
        for n,v in dict(ex3_pipedown=1,ex3_rslt_denorm=1,vfdsu_ex3_result_denorm_round_add_num=e['onehot'],
            frac_add1_op1_with_denorm=e['onehot']<<1,
            frac_sub1_op1_with_denorm=((1<<55)-1)^(e['onehot']<<1)).items():put(rounds,c.ROUND+'.'+n,v)
        for w,tid,index in zip(expected,(1,2,3,4),(2,3,6,8)):
            done=edges[index][1]
            for n,v in dict(fpu_valid_o=1,fpu_trans_id_o=tid,result_o=w['result'],fpu_exception_o=w['fflags']<<139).items():
                put(done,c.SCOPE+'.'+n,v)
            bits=list(done[c.SCOPE+'.fpu_exception_o']);bits[128:202]='x'*74;done[c.SCOPE+'.fpu_exception_o']=''.join(bits)
        return expected,edges

    def reject(self,edge,path,bits):
        e,edges=self.fixture();edges[edge][1][path]=bits
        with self.assertRaises(ValueError):c.audit_edges(self.decl,edges,e,self.proof)

    def test_owned_exponent_round_result_flags_with_unused_x(self):
        e,edges=self.fixture();a=c.audit_edges(self.decl,edges,e,self.proof)
        self.assertEqual(a['observed_k'],[26]);self.assertTrue(a['all_result_flags_checked'])

    def unknown_fu_field(self,state,path,name):
        left,right=self.proof['fu_layout']['fields'][name]
        bits=list(state[path]);width=self.decl[path]['width']
        bits[width-1-left:width-right]='x'*(left-right+1);state[path]=''.join(bits)

    def test_unused_move_b_unknown_issue_and_request_pass(self):
        e,edges=self.fixture()
        for index,path in ((0,c.ISSUE+'.fu_data_n'),(1,c.SCOPE+'.fu_data_i'),
                (1,c.ISSUE+'.fu_data_n'),(2,c.SCOPE+'.fu_data_i'),
                (6,c.ISSUE+'.fu_data_n'),(7,c.SCOPE+'.fu_data_i')):
            self.unknown_fu_field(edges[index][1],path,'operand_b')
        self.assertEqual(c.audit_edges(self.decl,edges,e,self.proof)['issued'],4)

    def test_used_issue_request_unknown_rejected(self):
        for index,path,names in ((0,c.ISSUE+'.fu_data_n',('operand_a','operation','trans_id')),
                (1,c.SCOPE+'.fu_data_i',('operand_a','operation','trans_id')),
                (2,c.ISSUE+'.fu_data_n',('operand_b',)),(3,c.SCOPE+'.fu_data_i',('operand_b',))):
            for name in names:
                with self.subTest(index=index,name=name):
                    e,edges=self.fixture();self.unknown_fu_field(edges[index][1],path,name)
                    with self.assertRaises(ValueError):c.audit_edges(self.decl,edges,e,self.proof)

    def held_move_fixture(self):
        e,edges=self.fixture();before=edges[7][1];post=edges[7][2]
        before[c.SCOPE+'.fpu_ready_o']='0';before[c.SCOPE+'.fpu_gen.fpu_in_ready']='0'
        before[c.SCOPE+'.fpu_gen.hold_inputs']='1';post[c.SCOPE+'.state_q']='1'
        for name in ('operand_a','operand_b','operand_c','fpu_op','fpu_rm','fpu_tag'):
            if name in ('operand_b','operand_c'):
                before[c.SCOPE+'.fpu_gen.'+name+'_d']='xz'*32
            post[c.SCOPE+'.fpu_gen.'+name+'_q']=before[c.SCOPE+'.fpu_gen.'+name+'_d']
        held=self.state();held[c.SCOPE+'.state_q']='1';held[c.SCOPE+'.fpu_gen.use_hold']='1'
        held[c.SCOPE+'.fpu_gen.fpu_in_valid']='1'
        for path in post:
            if path.endswith(('_a_q','_b_q','_c_q','_op_q','_rm_q','_tag_q')):held[path]=post[path]
        release=dict(held);release[c.SCOPE+'.fpu_ready_o']='1';release[c.SCOPE+'.fpu_gen.fpu_in_ready']='1'
        after=dict(release);after[c.SCOPE+'.state_q']='0'
        return e,edges[:8]+[[7.1,held,dict(held)],[7.2,release,after]]+edges[8:]

    def test_held_move_unused_four_state_capture_stable_pass(self):
        e,edges=self.held_move_fixture()
        self.assertEqual(c.audit_edges(self.decl,edges,e,self.proof)['hold_count'],1)

    def test_held_unused_raw_mutation_and_used_unknown_rejected(self):
        for index,name,bits in ((8,'operand_b_q','z'*64),(7,'operand_a_d','x'*64),
                (8,'operand_a_q','x'*64)):
            e,edges=self.held_move_fixture();edges[index][1][c.SCOPE+'.fpu_gen.'+name]=bits
            with self.assertRaises(ValueError):c.audit_edges(self.decl,edges,e,self.proof)

    def test_held_div_unused_c_unknown_pass_used_b_unknown_fail(self):
        e,edges=self.held_fixture()
        edges[3][1][c.SCOPE+'.fpu_gen.operand_c_d']='x'*64
        edges[3][2][c.SCOPE+'.fpu_gen.operand_c_q']='x'*64
        for index in (4,5):edges[index][1][c.SCOPE+'.fpu_gen.operand_c_q']='x'*64
        c.audit_edges(self.decl,edges,e,self.proof)
        edges[3][1][c.SCOPE+'.fpu_gen.operand_b_d']='x'*64
        with self.assertRaises(ValueError):c.audit_edges(self.decl,edges,e,self.proof)

    def test_wrong_exponent_rejected(self):
        self.reject(4,c.SRT+'.vfdsu_ex2_expnt_rst','0'*13)

    def test_wrong_table_onehot_rejected(self):
        self.reject(4,c.SRT+'.ex2_result_double_denorm_round_add_num','0'*53)

    def test_wrong_round_complement_rejected(self):
        self.reject(5,c.ROUND+'.frac_sub1_op1_with_denorm','0'*55)

    def test_wrong_result_or_flags_rejected(self):
        self.reject(6,c.SCOPE+'.result_o','0'*64)
        self.reject(6,c.SCOPE+'.fpu_exception_o','0'*203)

    def test_unknown_active_exception_fields_rejected(self):
        for name in ('cause','valid','tval'):
            e,edges=self.fixture();bits=list(edges[6][1][c.SCOPE+'.fpu_exception_o'])
            left,right=self.proof['exception_layout']['fields'][name];bits[202-left:203-right]='x'*(left-right+1)
            edges[6][1][c.SCOPE+'.fpu_exception_o']=''.join(bits)
            with self.subTest(name=name):
                with self.assertRaises(ValueError):c.audit_edges(self.decl,edges,e,self.proof)

    def test_missing_output_and_stage_rejected(self):
        e,edges=self.fixture()
        for subset in (edges[:-1],edges[:4]+edges[5:]):
            with self.assertRaises(ValueError):c.audit_edges(self.decl,subset,e,self.proof)

    def test_pipeline_flush_rejected(self):
        self.reject(4,c.SCOPE+'.flush_i','1')

    def test_wrong_stage_kind_rejected(self):
        self.reject(4,c.SRT+'.vfdsu_ex2_sqrt','1')

    def test_actual576_requests_and432_passthroughs(self):
        pre=r.life.read_bound(r.PRE/'preflight.json',r.PRE_SHA)
        e=c.expected_requests(pre)
        self.assertEqual(len(e),576)
        self.assertEqual(sum(x['kind']=='DIV' for x in e),144)
        self.assertEqual(sum(x['kind']=='FMV_X2F' for x in e),288)
        self.assertEqual(sum(x['kind']=='FMV_F2X' for x in e),144)

    def test_wrong_move_output_and_flags_rejected(self):
        self.reject(2,c.SCOPE+'.result_o','0'*64)
        self.reject(2,c.SCOPE+'.fpu_exception_o',format(1<<139,'0203b'))

    def test_wrong_move_tid_rejected(self):
        self.reject(2,c.SCOPE+'.fpu_trans_id_o','111')

    def test_wrong_issue_pc_rejected(self):
        self.reject(0,c.ISSUE+'.issue_instr_i','0'*438)

    def test_transfer_cannot_enter_div_stage(self):
        self.reject(1,c.SRT+'.ex2_pipedown','1')

    def reuse_fixture(self):
        expected,edges=self.fixture()
        # Old moveA writes back on the exact edge moveB enters with reused TID1.
        for edge,side,path in ((1,1,c.ISSUE+'.issue_instr_i'),(1,1,c.ISSUE+'.fu_data_n'),
            (1,2,c.SCOPE+'.fu_data_i'),(2,1,c.SCOPE+'.fu_data_i')):
            bits=edges[edge][side][path];value=int(bits,2)
            if path.endswith('issue_instr_i'):value=(value&~(7<<371))|(1<<371)
            else:value=(value&~7)|1
            edges[edge][side][path]=format(value,'0%db'%self.decl[path]['width'])
        for edge,side,path in ((1,2,c.SCOPE+'.fpu_gen.fpu_tag_d'),(2,1,c.SCOPE+'.fpu_gen.fpu_tag_d'),
            (3,1,c.SCOPE+'.fpu_trans_id_o')):edges[edge][side][path]='001'
        return expected,edges

    def test_same_edge_old_writeback_new_request_tid_reuse(self):
        expected,edges=self.reuse_fixture();a=c.audit_edges(self.decl,edges,expected,self.proof)
        self.assertEqual(len(a['completed']),4)

    def test_reuse_without_old_writeback_rejected(self):
        expected,edges=self.reuse_fixture();edges[2][1][c.SCOPE+'.fpu_valid_o']='0'
        with self.assertRaises(ValueError):c.audit_edges(self.decl,edges,expected,self.proof)

    def held_fixture(self):
        expected,edges=self.fixture()
        # DIV input backpressure; capture then stable STALL, release before EX2.
        before=edges[3][1];post=edges[3][2]
        before[c.SCOPE+'.fpu_ready_o']='0';before[c.SCOPE+'.fpu_gen.fpu_in_ready']='0'
        before[c.SCOPE+'.fpu_gen.hold_inputs']='1';post[c.SCOPE+'.state_q']='1'
        for n in 'abc':post[c.SCOPE+'.fpu_gen.operand_'+n+'_q']=before[c.SCOPE+'.fpu_gen.operand_'+n+'_d']
        for n in ('op','rm','tag'):post[c.SCOPE+'.fpu_gen.fpu_'+n+'_q']=before[c.SCOPE+'.fpu_gen.fpu_'+n+'_d']
        held=self.state();held[c.SCOPE+'.state_q']='1';held[c.SCOPE+'.fpu_gen.use_hold']='1'
        held[c.SCOPE+'.fpu_gen.fpu_in_valid']='1'
        for path in post:
            if path.endswith(('_a_q','_b_q','_c_q','_op_q','_rm_q','_tag_q')):held[path]=post[path]
        release=dict(held);release[c.SCOPE+'.fpu_ready_o']='1';release[c.SCOPE+'.fpu_gen.fpu_in_ready']='1'
        after=dict(release);after[c.SCOPE+'.state_q']='0'
        edges=edges[:4]+[[3.1,held,dict(held)],[3.2,release,after]]+edges[4:]
        return expected,edges

    def test_actual_held_div_capture_stability_release(self):
        expected,edges=self.held_fixture();a=c.audit_edges(self.decl,edges,expected,self.proof)
        self.assertEqual(a['hold_count'],1);self.assertEqual(a['stall_cycles'],2)
        self.assertEqual(len(a['completed']),4)

    def test_held_data_op_rm_tid_mutation_rejected(self):
        for name in ('operand_a_q','operand_b_q','operand_c_q','fpu_op_q','fpu_rm_q','fpu_tag_q'):
            expected,edges=self.held_fixture();path=c.SCOPE+'.fpu_gen.'+name
            old=edges[4][1][path];edges[4][1][path]=format(int(old,2)^1,'0%db'%len(old))
            with self.subTest(field=name):
                with self.assertRaises(ValueError):c.audit_edges(self.decl,edges,expected,self.proof)

    def test_held_flush_and_early_output_rejected(self):
        for change in ('flush','output'):
            expected,edges=self.held_fixture()
            if change=='flush':edges[4][1][c.SCOPE+'.flush_i']='1'
            else:
                edges[4][1][c.SCOPE+'.fpu_valid_o']='1'
                edges[4][1][c.SCOPE+'.fpu_trans_id_o']='011'
            with self.subTest(change=change):
                with self.assertRaises(ValueError):c.audit_edges(self.decl,edges,expected,self.proof)

    def terminal_fixture(self):
        run=r.life.OUT/'never-run-terminal-fixture';pid=2147483647
        record=dict(command=r.command(run),elf_sha256='a'*64,service=r.SERVICE)
        s=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,case=r.NAME,
            coverage_admitted=False,admission_performed=False,terminal_oracle_verified=False,
            wall_seconds=12,pid=pid)
        start=dict(pid=pid,process_group=pid,budget_s=r.BUDGET,input_elf=str(r.ELF),elf_sha256=record['elf_sha256'],
            image=str(r.life.IMAGE),image_sha256=r.IMAGE_SHA,command=record['command'],foreground_lifetime=True,
            coverage_admitted=False)
        identity=dict(pid=pid,executable=str(r.life.IMAGE.resolve()),cwd=str(run),command=record['command'],
            process_group=pid,service=r.SERVICE,verified=True,cgroup='0::/user.slice/'+r.SERVICE)
        return run,record,{'simulation-status.json':s,'started.json':start,'live-identity.json':identity,'manifest.json':record}

    def test_real_terminal_call_chain_positive(self):
        run,record,files=self.terminal_fixture()
        def read(path):return json.dumps(files[path.name]).encode()
        with patch.object(Path,'read_bytes',read):c.terminal_gate(run,record)

    def test_real_terminal_call_chain_bad_type_cgroup_image(self):
        for negative in ('return_bool','timeout','cgroup','image'):
            run,record,files=self.terminal_fixture()
            if negative=='return_bool':files['simulation-status.json']['returncode']=False
            elif negative=='timeout':files['simulation-status.json']['timeout']=True
            elif negative=='cgroup':files['live-identity.json']['cgroup']='0::/other.service'
            else:files['started.json']['image_sha256']='b'*64
            def read(path):return json.dumps(files[path.name]).encode()
            with self.subTest(negative=negative),patch.object(Path,'read_bytes',read):
                with self.assertRaises(ValueError):c.terminal_gate(run,record)

    def test_wrong_probe_width_rejected(self):
        d=copy.deepcopy(self.decl);d[c.SRT+'.vfdsu_ex2_expnt_rst']['width']=12;e,edges=self.fixture()
        with self.assertRaises(ValueError):c.audit_edges(d,edges,e,self.proof)

    def test_complete_zero_log_contract_and_error_negative(self):
        text='SUBNORMAL_DIV_PROBE_READY\nCore Test *** SUCCESS ***\n[ARA_CONTRACT] '+\
            'requests=0 responses=0 exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'
        self.assertEqual(c.stdout_gate(text)['exceptions'],0)
        for changed in (text+'\nSUBNORMAL_DIV_PROBE_ERROR failed',text+'\nSUBNORMAL_DIV_PROBE_READY',
            text.replace('mmu_request_cycles=0','mmu_request_cycles=1'),text.replace('SUBNORMAL_DIV','FMA_ARB')):
            with self.assertRaises(ValueError):c.stdout_gate(changed)

    def test_no_publication_and_explicit_600s_lifecycle(self):
        self.assertEqual(r.BUDGET,600)
        self.assertEqual(r.run.__code__.co_names,('dict','reused','run','__globals__','PRE','ELF','NAME','BUDGET','command','FunctionType','__code__'))


if __name__=='__main__':unittest.main()
