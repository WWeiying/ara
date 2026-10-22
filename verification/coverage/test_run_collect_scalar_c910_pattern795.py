import copy
import json
from pathlib import Path
import subprocess
import unittest
import tempfile
from unittest.mock import patch
import run_scalar_c910_pattern795 as r
import collect_scalar_c910_pattern795 as c
import test_scalar_div_subnormal794 as fixtures


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof=r.source_contract();cls.table=c.literal_table()
        cls.decl={p:dict(width=w,code=p,type='wire') for p,w in c.probe_widths(cls.proof).items()}
        cls.implementation=staticmethod(c.owner_implementation())

    def fixture(self,sqrt=False):
        fixtures.Native.setUpClass();base=fixtures.Native();_,old=base.fixture()
        e=r.oracle.cells()[128 if sqrt else 2]
        expected=[dict(kind='FMV_X2F',pc=4,operand_a=e['a'],result=e['a'],fflags=0,rm=3),
            dict(kind='FMV_X2F',pc=8,operand_a=e['b'],result=e['b'],fflags=0,rm=3),
            dict(e,kind='SQRT' if sqrt else 'DIV',pc=12,operand_a=e['a']),
            dict(kind='FMV_F2X',pc=16,operand_a=e['result'],result=e['result'],fflags=0,rm=3)]
        if not sqrt:expected[2]['operand_b']=e['b']
        else:expected[2].pop('operand_b',None)
        expected=[dict(w,cell=0) for w in expected]
        edges=[[i,{p:'0'*v['width'] for p,v in self.decl.items()},
            {p:'0'*v['width'] for p,v in self.decl.items()}] for i in range(9)]
        def put(s,p,v):s[p]=format(v,'0%db'%self.decl[p]['width'])
        def fu(w,tid):
            op=self.proof['ariane_ops'][{'DIV':'FDIV','SQRT':'FSQRT'}.get(w['kind'],w['kind'])]
            values=dict(operation=op,trans_id=tid,operand_a=w['operand_a'],operand_b=w.get('operand_b',0))
            return sum(values.get(n,0)<<right for n,(left,right) in self.proof['fu_layout']['fields'].items())
        for w,tid,issue,request in zip(expected,(1,2,3,4),(0,1,2,6),(1,2,3,7)):
            before=edges[issue][1];put(before,c.ISSUE+'.fpu_valid_n',1)
            put(before,c.ISSUE+'.fu_data_n',fu(w,tid));put(before,c.ISSUE+'.issue_instr_i',(w['pc']<<374)|(tid<<371))
            for state in (edges[issue][2],edges[request][1]):
                for n,v in dict(fpu_valid_i=1,fpu_ready_o=1,fu_data_i=fu(w,tid)).items():put(state,c.SCOPE+'.'+n,v)
                for n,v in dict(fpu_in_ready=1,fpu_in_valid=1,fpu_tag_d=tid,
                    fpu_op_d=self.proof['fpnew_ops'][w['kind'] if w['kind'] in ('DIV','SQRT') else 'SGNJ'],fpu_rm_d=w['rm']).items():
                    put(state,c.SCOPE+'.fpu_gen.'+n,v)
                for n,v in zip('abc',(w['operand_a'],w.get('operand_b',0),0)):put(state,c.SCOPE+'.fpu_gen.operand_'+n+'_d',v)
        ex2,after=edges[4][1],edges[4][2]
        selector=0 if sqrt else 64+((e['b']&r.oracle.MASK)>>46)
        for n,v in dict(initial_srt_en=1,initial_srt_sel_div_in=int(not sqrt),initial_srt_sel_sqrt_in=int(sqrt),
                initial_bound_sel_in=selector,ex2_pipedown=1,vfdsu_ex2_double=1,vfdsu_ex2_sqrt=int(sqrt)).items():put(ex2,c.SRT+'.'+n,v)
        put(after,c.ITER+'.bound_sel',selector)
        if not sqrt:
            for n,v in self.table[selector].items():put(after,c.BOUND+'.ori_digit_bound_'+str(n),v)
        put(edges[5][1],c.ROUND+'.ex3_pipedown',1)
        for w,tid,index in zip(expected,(1,2,3,4),(2,3,6,8)):
            state=edges[index][1]
            for n,v in dict(fpu_valid_o=1,fpu_trans_id_o=tid,result_o=w['result'],fpu_exception_o=w['fflags']<<139).items():put(state,c.SCOPE+'.'+n,v)
        return expected,edges

    def audit(self,e,edges):return self.implementation(self.decl,edges,e,self.proof)

    def test_actual896_reference_owners(self):
        pre=r.life.read_bound(r.PRE/'preflight.json',r.PRE_SHA);owners=c.expected_requests(pre)
        self.assertEqual(len(owners),896)
        self.assertEqual(sum(e['kind']=='DIV' for e in owners),160)
        self.assertEqual(sum(e['kind']=='SQRT' for e in owners),64)

    def test_normal_div_and_sqrt_full_owners(self):
        for sqrt in (False,True):
            e,edges=self.fixture(sqrt);a=self.audit(e,edges)
            self.assertEqual(len(a['completed']),4);self.assertEqual(len(a['table_observations']),1)
            self.assertEqual(a['initial_observations'][0]['selector'],0 if sqrt else 65)

    def test_wrong_selector_table_format_or_round_rejected(self):
        for part,path in ((1,c.SRT+'.initial_bound_sel_in'),(2,c.ITER+'.bound_sel'),
                (2,c.BOUND+'.ori_digit_bound_1'),(1,c.SRT+'.vfdsu_ex2_double')):
            e,edges=self.fixture();edges[4][part][path]='0'*self.decl[path]['width']
            with self.assertRaises(ValueError):self.audit(e,edges)
        e,edges=self.fixture();edges[5][1][c.ROUND+'.ex3_rslt_denorm']='1'
        with self.assertRaises(ValueError):self.audit(e,edges)

    def test_sqrt_unused_B_X_pass_A_X_rejected(self):
        e,edges=self.fixture(True)
        left,right=self.proof['fu_layout']['fields']['operand_b']
        for index,path in ((2,c.ISSUE+'.fu_data_n'),(3,c.SCOPE+'.fu_data_i')):
            bits=list(edges[index][1][path]);width=self.decl[path]['width']
            bits[width-1-left:width-right]='x'*(left-right+1);edges[index][1][path]=''.join(bits)
        self.audit(e,edges)
        left,right=self.proof['fu_layout']['fields']['operand_a'];path=c.SCOPE+'.fu_data_i'
        bits=list(edges[3][1][path]);width=self.decl[path]['width'];bits[width-1-left:width-right]='x'*(left-right+1)
        edges[3][1][path]=''.join(bits)
        with self.assertRaises(ValueError):self.audit(e,edges)

    def test_wrong_move_result_flags_tid_or_missing_output_rejected(self):
        for path in ('result_o','fpu_exception_o','fpu_trans_id_o','fpu_valid_o'):
            e,edges=self.fixture();p=c.SCOPE+'.'+path;edges[2][1][p]='0'*self.decl[p]['width']
            if path=='fpu_exception_o':edges[2][1][p]=format(1<<139,'0203b')
            with self.assertRaises(ValueError):self.audit(e,edges)

    def test_source_op_contract_and_literal_table(self):
        self.assertEqual(self.proof['request_counts']['total'],896)
        self.assertEqual(set(range(64,128))-set(self.table),set())

    def test_flush_priority_cancel_then_reissue(self):
        e,normal=self.fixture();issue=[-2,dict(normal[0][1]),dict(normal[0][2])]
        before=dict(normal[1][1]);before[c.SCOPE+'.flush_i']='1'
        before[c.ISSUE+'.fpu_valid_n']='0';before[c.SCOPE+'.fpu_valid_o']='0'
        after={p:'0'*v['width'] for p,v in self.decl.items()}
        a=self.audit(e,[issue,[-1,before,after]]+normal)
        self.assertEqual(len(a['scheduled_cancellations']),1);self.assertEqual(len(a['completed']),4)
        with self.assertRaises(ValueError):self.audit(e,[issue,[-1,before,after]])

    def test_live_flush_rejected(self):
        e,edges=self.fixture();edges[2][1][c.SCOPE+'.flush_i']='1'
        with self.assertRaises(ValueError):self.audit(e,edges)

    def test_same_edge_old_output_new_TID_reuse(self):
        e,edges=self.fixture()
        for index,part,path in ((1,1,c.ISSUE+'.fu_data_n'),(1,2,c.SCOPE+'.fu_data_i'),(2,1,c.SCOPE+'.fu_data_i')):
            value=int(edges[index][part][path],2);edges[index][part][path]=format((value&~7)|1,'0207b')
        value=int(edges[1][1][c.ISSUE+'.issue_instr_i'],2)
        edges[1][1][c.ISSUE+'.issue_instr_i']=format((value&~(7<<371))|(1<<371),'0438b')
        for index,part in ((1,2),(2,1)):edges[index][part][c.SCOPE+'.fpu_gen.fpu_tag_d']='001'
        edges[3][1][c.SCOPE+'.fpu_trans_id_o']='001'
        self.assertEqual(len(self.audit(e,edges)['completed']),4)
        edges[2][1][c.SCOPE+'.fpu_valid_o']='0'
        with self.assertRaises(ValueError):self.audit(e,edges)

    def held(self,sqrt):
        e,edges=self.fixture(sqrt);before=edges[3][1];post=edges[3][2]
        before[c.SCOPE+'.fpu_ready_o']='0';before[c.SCOPE+'.fpu_gen.fpu_in_ready']='0'
        before[c.SCOPE+'.fpu_gen.hold_inputs']='1';post[c.SCOPE+'.state_q']='1'
        if sqrt:before[c.SCOPE+'.fpu_gen.operand_b_d']='xz'*32
        before[c.SCOPE+'.fpu_gen.operand_c_d']='xz'*32
        for name in ('operand_a','operand_b','operand_c','fpu_op','fpu_rm','fpu_tag'):
            post[c.SCOPE+'.fpu_gen.'+name+'_q']=before[c.SCOPE+'.fpu_gen.'+name+'_d']
        stable={p:'0'*v['width'] for p,v in self.decl.items()};stable[c.SCOPE+'.state_q']='1'
        stable[c.SCOPE+'.fpu_gen.use_hold']='1';stable[c.SCOPE+'.fpu_gen.fpu_in_valid']='1'
        for path in post:
            if path.endswith(('_a_q','_b_q','_c_q','_op_q','_rm_q','_tag_q')):stable[path]=post[path]
        release=dict(stable);release[c.SCOPE+'.fpu_ready_o']='1';release[c.SCOPE+'.fpu_gen.fpu_in_ready']='1'
        after=dict(release);after[c.SCOPE+'.state_q']='0'
        return e,edges[:4]+[[3.1,stable,dict(stable)],[3.2,release,after]]+edges[4:]

    def test_held_DIV_and_SQRT_with_raw_unused_X(self):
        for sqrt in (False,True):
            e,edges=self.held(sqrt);a=self.audit(e,edges)
            self.assertEqual(a['hold_count'],1);self.assertEqual(a['stall_cycles'],2)

    def test_held_used_unknown_unstable_unused_and_pendingflush_rejected(self):
        for field in ('operand_a_q','operand_c_q','fpu_tag_q','fpu_rm_q'):
            e,edges=self.held(True);p=c.SCOPE+'.fpu_gen.'+field;edges[4][1][p]='x'*self.decl[p]['width']
            with self.assertRaises(ValueError):self.audit(e,edges)
        e,edges=self.held(False);edges[4][1][c.SCOPE+'.flush_i']='1'
        with self.assertRaises(ValueError):self.audit(e,edges)

    def test_actual_terminal_chain_uses_new_runner_image(self):
        self.assertEqual(r.IMAGE_SHA,r.old.IMAGE_SHA)
        from types import FunctionType
        implementation=FunctionType(c.frozen.terminal_gate.__code__,dict(c.frozen.terminal_gate.__globals__,runner=r))
        with tempfile.TemporaryDirectory() as temp:
            run=Path(temp);pid=999999999
            record=dict(command=r.command(run),elf_sha256='a'*64,service=r.SERVICE)
            status=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,case=r.NAME,
                coverage_admitted=False,admission_performed=False,terminal_oracle_verified=False,wall_seconds=2,pid=pid)
            started=dict(pid=pid,process_group=pid,budget_s=600,input_elf=str(r.ELF),elf_sha256='a'*64,
                image=str(r.life.IMAGE),image_sha256=r.IMAGE_SHA,command=record['command'],foreground_lifetime=True,coverage_admitted=False)
            identity=dict(pid=pid,executable=str(r.life.IMAGE.resolve()),cwd=str(run),command=record['command'],
                process_group=pid,service=r.SERVICE,verified=True,cgroup='0::/app.slice/'+r.SERVICE)
            for name,value in (('simulation-status.json',status),('started.json',started),('live-identity.json',identity),('manifest.json',record)):
                (run/name).write_text(json.dumps(value))
            implementation(run,record)
            for name,key,value in (('simulation-status.json','returncode',False),('started.json','image_sha256','b'*64),
                    ('live-identity.json','cgroup','0::/wrong.service')):
                p=run/name;original=json.loads(p.read_text());mutant=dict(original);mutant[key]=value;p.write_text(json.dumps(mutant))
                with self.assertRaises(ValueError):implementation(run,record)
                p.write_text(json.dumps(original))

    def test_real_probe_Tcl_matches_exact_typed_paths(self):
        code='''proc show {args} {}
proc dump {args} {if {[lindex $args 0] eq "-add"} {puts "PATH [lindex $args 1]"};return 1}
proc run {} {}
'''+r.PROBE.read_text()
        p=subprocess.run(['tclsh'],input=code,text=True,capture_output=True,check=True)
        self.assertNotIn('PROBE_ERROR',p.stdout)
        paths=[l[5:] for l in p.stdout.splitlines() if l.startswith('PATH ')]
        self.assertEqual(set(paths),set(self.decl));self.assertEqual(len(paths),len(set(paths)))

    def test_zero_CVX_contract_marker_and_error(self):
        text='C910_PATTERN_PROBE_READY\nC910_PATTERN_PROBE_ERROR real\n'
        with self.assertRaises(ValueError):c.stdout_gate(text)

    def test_foreign_missing_and_duplicate_probe_markers_rejected(self):
        for text in ('SUBNORMAL_DIV_PROBE_READY\n', '',
                     'C910_PATTERN_PROBE_READY\nC910_PATTERN_PROBE_READY\n',
                     'C910_PATTERN_PROBE_READY\nSUBNORMAL_DIV_PROBE_READY\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):c.stdout_gate(text)

    def test_budget_frozen_ELF_and_noFSDB(self):
        cmd=r.command(r.life.OUT/'dry')
        self.assertIn('+NO_FSDB',cmd);self.assertIn('+PRELOAD='+str(r.ELF),cmd)
        self.assertEqual(r.BUDGET,600);self.assertEqual(r.IMAGE_SHA,r.old.IMAGE_SHA)


if __name__=='__main__':unittest.main()
