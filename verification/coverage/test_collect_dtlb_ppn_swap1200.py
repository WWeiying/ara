import copy
from pathlib import Path
import unittest
import collect_dtlb_ppn_swap1200 as m


class Memory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commits=[]
        for c in m.spike_trace.parse_spike_commits(m.runner.PRE.parent/'spike.trace'):
            if not cls.commits and c.pc!=0x80000000:continue
            cls.commits.append(c)
            if (0x80001000,1) in c.memory_accesses:break
        cls.rows=[]
        for i,c in enumerate(cls.commits):
            g={r:v for r,v in c.gpr_writes.items() if r};rd=next(iter(g),0)
            row=dict(event='retire',order=str(i),pc=hex(c.pc),insn=hex(c.instruction),trap='0',
                     rd=str(rd),rd_wdata=hex(g.get(rd,0)),mem_rmask='0',mem_wmask='0',mem_addr='0',mem_wdata='0')
            if c.memory_accesses:
                a,v=c.memory_accesses[0]
                access=m.rv64c.decode(c.instruction) if c.instruction&3!=3 else \
                    dict(size=m.spike_trace._scalar_memory_access(c.instruction)[1])
                row['mem_addr']=hex(a);row['mem_rmask' if v is None else 'mem_wmask']=hex(((1<<access['size'])-1)<<(a&7))
                if v is not None:row['mem_wdata']=hex(v)
            cls.rows.append(row)

    def test_actual_frozen_reference_complete19071(self):
        r=m.memory_gate(self.rows,self.commits)
        self.assertEqual((r['retired'],r['total'],r['compressed'],r['uncompressed'],r['loads'],r['stores']),
                         (191475,19071,16823,2248,8553,10518))

    def mutate(self,key,value,kind=None,compressed=None):
        rows=list(self.rows)
        i=next(i for i,c in enumerate(self.commits) if c.memory_accesses and
            (kind is None or (c.memory_accesses[0][1] is not None)==(kind=='store')) and
            (compressed is None or (c.instruction&3!=3)==compressed))
        rows[i]=dict(rows[i],**{key:value})
        with self.assertRaises(ValueError):m.memory_gate(rows,self.commits)

    def test_rvc_store_address_rejected(self):self.mutate('mem_addr','0','store',True)
    def test_rvc_store_mask_rejected(self):self.mutate('mem_wmask','0','store',True)
    def test_rvc_store_data_rejected(self):self.mutate('mem_wdata','0xdeadbeef','store',True)
    def test_rvc_load_return_rejected(self):self.mutate('rd_wdata','0xdeadbeef','load',True)
    def test_uncompressed_load_mask_rejected(self):self.mutate('mem_rmask','0','load',False)
    def test_pc_opcode_trap_rejected(self):
        for k,v in [('pc','0'),('insn','0'),('trap','1')]:self.mutate(k,v)
    def test_missing_retirement_rejected(self):
        with self.assertRaises(ValueError):m.memory_gate(self.rows[:-1],self.commits)


class Slots(unittest.TestCase):
    def fixture(self):
        widths={'ara_tb.clk':1,'ara_tb.rst_n':1,m.MONITOR:64}
        widths.update({m.SCOPE+'.'+k:w for k,w in dict(update_i=189,replace_en=16,lu_hit=16,
            lu_hit_o=1,lu_access_i=1,lu_vaddr_i=64,lu_asid_i=16,plru_tree_q=30,flush_i=1,s_st_enbl_i=1,
            content_q=2048,tags_q=976).items()})
        widths.update({m.LOAD+'.'+k:w for k,w in dict(pop_ld_o=1,valid_i=1,dtlb_hit_i=1,vaddr_o=64,
            dtlb_ppn_i=44,flush_i=1,ex_i=203).items()})
        decl={p:dict(code=str(i),width=w) for i,(p,w) in enumerate(widths.items())}
        state={d['code']:'0'*d['width'] for d in decl.values()};frames=[];targets=[];cycle=0
        def setv(s,name,v):s[decl[name]['code']]=format(v,'0%db'%decl[name]['width'])
        def edge(values,aftervalues=None):
            nonlocal cycle,state
            before=dict(state)
            for p,v in values.items():setv(before,p,v)
            setv(before,'ara_tb.clk',0);setv(before,'ara_tb.rst_n',1);setv(before,m.MONITOR,cycle)
            after=dict(before);setv(after,'ara_tb.clk',1);setv(after,m.MONITOR,cycle+1)
            for p,v in (aftervalues or {}).items():setv(after,p,v)
            frames.append((cycle*100,before,after));state=after;cycle+=1
        content=tags=0
        for p in range(3):
            edge({m.SCOPE+'.flush_i':1,m.SCOPE+'.update_i':0,m.LOAD+'.pop_ld_o':0})
            for i in range(16):
                owner=m.pre.shared.plru_order()[p][i];v=m.pre.shared.vpn(0,i)
                ppn=m.pre.pa(m.pre.page(p,i))>>12;pte=(ppn<<10)|0xc7
                content=(content&~(((1<<128)-1)<<(128*owner)))|((pte<<64)<<(128*owner))
                tags=(tags&~(((1<<61)-1)<<(61*owner)))|(((v<<4)|3)<<(61*owner))
                edge({m.SCOPE+'.flush_i':0,m.SCOPE+'.update_i':(1<<188)|(v<<159)|(pte<<64),
                    m.SCOPE+'.replace_en':1<<owner,m.SCOPE+'.lu_hit_o':0,m.LOAD+'.pop_ld_o':0},
                    {m.SCOPE+'.content_q':content,m.SCOPE+'.tags_q':tags})
                for b in range(2):
                    edge({m.SCOPE+'.update_i':0,m.SCOPE+'.s_st_enbl_i':1,m.SCOPE+'.lu_hit_o':1,
                        m.SCOPE+'.lu_hit':1<<owner,m.SCOPE+'.lu_vaddr_i':m.pre.address(i),
                        m.LOAD+'.pop_ld_o':1,m.LOAD+'.valid_i':1,m.LOAD+'.dtlb_hit_i':1,
                        m.LOAD+'.vaddr_o':m.pre.address(i),m.LOAD+'.dtlb_ppn_i':ppn})
                    targets.append(dict(cycle=str(cycle-1),order=str(len(targets)),pc=hex(0x80002204+4*b)))
        edge({m.SCOPE+'.flush_i':1,m.SCOPE+'.update_i':0,m.LOAD+'.pop_ld_o':0}, {m.SCOPE+'.tags_q':0})
        return decl,frames,targets

    def test_exact48_updates96_hits(self):
        d,f,t=self.fixture();r=m.wave_gate(iter([('declarations',d)]+f),t)
        self.assertEqual(len(r['updates']),48);self.assertEqual(len(r['accepted_loads']),96)

    def bad(self,mutate):
        d,f,t=self.fixture();mutate(d,f,t)
        with self.assertRaises(ValueError):m.wave_gate(iter([('declarations',d)]+f),t)

    def test_bad_owner_ppn_unknown_and_exception(self):
        for name,value,idx in [(m.SCOPE+'.replace_en',3,1),(m.LOAD+'.dtlb_ppn_i',0,2),
                              (m.LOAD+'.ex_i',1,2),(m.SCOPE+'.lu_hit',3,2)]:
            def mutate(d,f,t,name=name,value=value,idx=idx):
                f[idx][1][d[name]['code']]=format(value,'0%db'%d[name]['width'])
            self.bad(mutate)

    def test_missing_load_update_flush(self):
        for idx in (0,1,2):self.bad(lambda d,f,t,idx=idx:f.pop(idx))

    def test_wrong_postslot_state(self):
        self.bad(lambda d,f,t:f[1][2].__setitem__(d[m.SCOPE+'.content_q']['code'],'0'*2048))

    def test_final_flush_valid_entries_rejected(self):
        self.bad(lambda d,f,t:f[-1][2].__setitem__(d[m.SCOPE+'.tags_q']['code'],format(1,'0976b')))

    def test_native_parent_child_ambiguity(self):
        d,f,t=self.fixture();d[m.SCOPE+'.content_q[0]']=dict(code='foreign',width=128)
        with self.assertRaises(ValueError):m.wave_gate(iter([('declarations',d)]+f),t)

    def test_explicit_packed_child_indices(self):
        decl={f'obj[{i}]':dict(code=str(i),width=128) for i in range(16)}
        state={str(i):format(i,'0128b') for i in range(16)}
        self.assertEqual([int(b,2) for b in m.packed_slots(decl,state,'obj',128)],list(range(16)))


class Gates(unittest.TestCase):
    def test_identity_cgroup_types_and_command(self):
        r=dict(output='/exact/run',command=['simv'],pins={str(m.life.IMAGE):'0'*64},service='ara-dtlb-test.service')
        identity=dict(pid=2147483647,executable=str(m.life.IMAGE.resolve()),executable_sha256='0'*64,
            cwd=r['output'],command=r['command'],service=r['service'],
            cgroup='0::/user.slice/ara-dtlb-test.service\n')
        m.identity_gate(identity,r)
        for key,value in [('pid',True),('command',['other']),('cgroup','0::/wrong.service\n')]:
            with self.assertRaises(ValueError):m.identity_gate(dict(identity,**{key:value}),r)

    def test_terminal_strict_types(self):
        t=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,case=m.runner.CASE,
               coverage_admitted=False,automatic_retry=False)
        m.terminal_gate(t)
        for k,v in [('returncode',False),('timeout',0),('timeout',True),('returncode',1)]:
            with self.assertRaises(ValueError):m.terminal_gate(dict(t,**{k:v}))

    def test_real_error_not_echoed_script(self):
        summary='[ARA_CONTRACT] requests=0 responses=0 exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'
        objects=['ara_tb.clk','ara_tb.rst_n',m.MONITOR]+[m.SCOPE+'.'+s for s in
            ('update_i','replace_en','lu_hit','lu_hit_o','lu_access_i','lu_vaddr_i','lu_asid_i','plru_tree_q',
             'flush_i','s_st_enbl_i','content_q','tags_q')]+[m.LOAD+'.'+s for s in
            ('pop_ld_o','valid_i','translation_req_o','dtlb_hit_i','vaddr_o','paddr_i','dtlb_ppn_i','flush_i','ex_i')]
        console='\n'.join(['puts "DTLB_PPN1200_ERROR $failure"']+['DTLB_PPN1200_OBJECT '+x for x in objects]+
            ['DTLB_PPN1200_READY','Core Test *** SUCCESS ***',summary,'UVM_ERROR : 0','UVM_FATAL : 0'])
        m.logs(console,'Core Test *** SUCCESS ***\n'+summary)
        for bad in ['UVM_ERROR message','UVM_FATAL message','DTLB_PPN1200_ERROR bad','DTLB_PPN1200_READY',
                    'UVM_ERROR : 1']:
            with self.assertRaises(ValueError):m.logs(console+'\n'+bad,'Core Test *** SUCCESS ***\n'+summary)


if __name__=='__main__':unittest.main()
