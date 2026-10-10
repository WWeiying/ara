import copy
import json
from pathlib import Path
import tempfile
import unittest
import collect_btb_target_ring as c


S={'btb_bank0':0x80002000,'btb_bank1':0x80002042}


def packed(fields,values):
    return ''.join(format(values.get(n,0),'0%db'%w) for n,w in fields)


def fixture():
    decl={n:dict(width=w,code=n) for n,w in {'ara_tb.clk':1,'ara_tb.rst_n':1,
        c.BTB+'.update_pc':4,c.BTB+'.update_row_index':1,c.BTB+'.debug_mode_i':1,c.BTB+'.flush_bp_i':1,
        c.BTB+'.btb_update_i':129,c.CORE+'.i_frontend.resolved_branch_i':134}.items()}
    head=('declarations',decl);edges=[]
    for bank in (0,1):
        for row in range(16):
            for target in c.pre.TARGETS:
                pc=S['btb_bank%d'%bank]+4*row
                state={n:format(0,'0%db'%v['width']) for n,v in decl.items()}
                state.update({'ara_tb.clk':'0','ara_tb.rst_n':'1',c.BTB+'.update_pc':format(row,'04b'),
                    c.BTB+'.update_row_index':str(bank),c.BTB+'.btb_update_i':packed(c.UPDATE,dict(valid=1,pc=pc,target_address=target)),
                    c.CORE+'.i_frontend.resolved_branch_i':packed(c.RESOLVE,dict(valid=1,pc=pc,target_address=target,
                        is_mispredict=1,is_taken=1,cf_type=3))})
                edges.append((len(edges)+10,state,dict(state,**{'ara_tb.clk':'1'})))
    return [head]+edges


def audit(rows):return c.update_audit(iter(c.branch_projection(iter(rows))),S)


class Updates(unittest.TestCase):
    def test_real_frozen_source_layout(self):
        pins=c.source_contract();self.assertIn(str(c.life.ROOT/'hardware/deps/cva6/core/include/ariane_pkg.sv'),pins)

    def test_all32_slot_lowbit_and_preedge(self):
        rows=fixture()
        # NBA values deliberately differ: sampling the after bucket is wrong.
        rows[1][2][c.BTB+'.btb_update_i']='0'*129
        r=audit(rows);self.assertEqual((r['slots'],r['updates']),(32,96))
        self.assertEqual({(x['row'],x['slot']) for x in r['records']},{(r,b) for r in range(16) for b in (0,1)})

    def test_missing_duplicate_reordered(self):
        base=fixture()
        for rows in (base[:-1],base+[base[-1]],base[:1]+[base[2],base[1]]+base[3:]):
            with self.assertRaisesRegex(ValueError,'Exact32'):audit(rows)

    def test_wrong_lowbit_index_debug_flush_unknown(self):
        for name,value in ((c.BTB+'.update_row_index','1'),(c.BTB+'.update_pc','0010'),
            (c.BTB+'.debug_mode_i','1'),(c.BTB+'.flush_bp_i','1'),(c.BTB+'.update_pc','xxxx')):
            rows=fixture();rows[1][1][name]=value
            with self.assertRaises(ValueError):audit(rows)

    def test_mispredict_valid_target_foreign_cf(self):
        for changes in (dict(is_mispredict=0),dict(cf_type=4),dict(target_address=0x44),dict(valid=0)):
            rows=fixture();v=dict(valid=1,pc=S['btb_bank0'],target_address=c.pre.TARGETS[0],is_mispredict=1,is_taken=1,cf_type=3)
            v.update(changes);rows[1][1][c.CORE+'.i_frontend.resolved_branch_i']=packed(c.RESOLVE,v)
            with self.assertRaises(ValueError):audit(rows)

    def test_mixed_width_unknown_encoding(self):
        for kind in ('width','mixed','unknown'):
            rows=fixture()
            if kind=='width':rows[0][1][c.BTB+'.btb_update_i']['width']=128
            elif kind=='mixed':rows[0][1][c.BTB+'.btb_update_i.valid']=dict(width=1,code='extra')
            else:rows[1][1][c.BTB+'.btb_update_i']='x'*129
            with self.assertRaises(ValueError):audit(rows)

    def test_complete_native_children_equivalent(self):
        rows=list(c.branch_projection(iter(fixture())))
        # Keep exact child declarations but remove packed parents.
        for name in (c.BTB+'.btb_update_i',c.CORE+'.i_frontend.resolved_branch_i'):rows[0][1].pop(name)
        self.assertEqual(audit(rows)['updates'],96)

    def test_actual_vcd_parser_pipeline(self):
        rows=fixture();decl=rows[0][1]
        # Flat escaped references retain complete full hierarchy names.
        header='$timescale 100fs $end\n'+''.join('$var wire %d id%d \\%s $end\n'%(v['width'],i,n)
            for i,(n,v) in enumerate(decl.items()))+'$enddefinitions $end\n'
        codes={n:'id%d'%i for i,n in enumerate(decl)};body=[];time=0
        for _,before,after in rows[1:]:
            time+=10;body.append('#%d\n'%time)
            body.extend(('b%s %s\n'%(bits,codes[n]) if decl[n]['width']>1 else bits+codes[n]+'\n') for n,bits in before.items())
            time+=5;body.append('#%d\n1%s\n'%(time,codes['ara_tb.clk']))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.vcd';p.write_text(header+''.join(body))
            parser=c.FunctionType(c.wave.vcd.__code__,dict(c.wave.vcd.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
            self.assertEqual(c.update_audit(iter(c.branch_projection(iter(parser(p)))),S)['updates'],96)

    def test_real_reference_vector_seeds(self):
        path=c.life.OUT/'btb-target-ring-preflight777-agent-20261007-03/preflight.json'
        q=c.life.read_bound(path,'06d7896e2b58dffbd0bdaec20c0141894ac242ed292fa238d75a5006856c75e3')
        commits=c.pre.interval(c.pre.build.parse_spike_commits(path.parent/'spike.trace'))
        writers=[x for x in commits if x.vector_writes]
        self.assertEqual(len(writers),4);self.assertEqual(sum(len(x.vector_writes)*128 for x in writers),4096)
        self.assertEqual(c.pre.validate(commits,q['symbols'],[('trap_supervisor_ecall',q['symbols']['btb_s_ecall'])]),q['counts'])


class Lifecycle(unittest.TestCase):
    def sample(self):
        base=dict(order='0',trans_id='1',insn='00000057',pc='80000000',trap='0',cycle='1',port='2')
        rows=[dict(base,event=e,cycle=str(i+1)) for i,e in enumerate(('arch_start','cvx_req','uop_alloc','uop_done','cvx_resp','retire'))]
        rows[4].update(order='-1',insn='00000000',pc='00000000')
        v=dict(arch_seq='0',vid='2',insn='00000057',nr_lanes='4',vlen_bits='1024',use_vd='1',vd='0',eew='0',vl='1024',vstart='0')
        vectors=[dict(v,event='alloc',cycle='3'),dict(v,event='write',cycle='4'),dict(v,event='done',cycle='4')]
        return rows,vectors,dict(requests=1,responses=1)

    def test_complete(self):
        self.assertEqual(c.lifecycle(*self.sample())['backend_uops'],1)

    def test_missing_response_done_duplicate_latewrite_foreign(self):
        for kind in ('response','done','duplicate','late','foreign'):
            rows,vs,s=self.sample()
            if kind=='response':rows.pop(4)
            if kind=='done':vs.pop()
            if kind=='duplicate':rows.insert(2,copy.deepcopy(rows[1]))
            if kind=='late':vs.append(dict(vs[1],cycle='7'))
            if kind=='foreign':vs[1]['arch_seq']='5'
            with self.assertRaises(ValueError):c.lifecycle(rows,vs,s)


if __name__=='__main__':unittest.main()
