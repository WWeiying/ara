import copy
import unittest
from types import SimpleNamespace
import collect_csr_cause_wlrl788 as c

class CollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=c.life.read_bound(c.runner.PRE/'preflight-manifest.json',c.runner.PRE_SEAL)
        cls.pre=p;cls.reference=c.runner.reference(p)
        cls.rows=[dict(order=i,cycle=i+100) for i in range(664)]
        cls.expected=c.csr_expected(cls.reference,cls.rows,c.runner.source_contract()[0]['ops'])

    def test_owners(self):
        self.assertEqual(len(self.expected),30)
        self.assertEqual({x['csr'] for x in self.expected},{0x342,0x142})
        self.assertEqual(sum(x['operation']==c.runner.source_contract()[0]['ops']['CSR_WRITE'] for x in self.expected),14)

    def edges(self):
        result=[]
        for x in self.expected:
            result.append(dict(commit=0,buffer_commit=0,issue=1,buffer_valid=0,ready=0,
                issue_address=x['csr'],issue_operand=x['operand'],issue_tid=3,cycle=x['cycle']-1,flush=0))
            result.append(dict(commit=1,buffer_commit=1,issue=0,buffer_valid=1,ready=1,address=x['csr'],
                ack=1,pc=x['pc'],cycle=x['cycle'],tid=3,wdata=x['operand'],rdata=x['old'],operation=x['operation'],flush=0))
        return result

    def test_full_native_positive(self):self.assertEqual(len(c.owner_gate(self.edges(),self.expected)['committed']),30)
    def test_wrong_word(self):
        e=self.edges();e[1]['rdata']^=1
        with self.assertRaises(ValueError):c.owner_gate(e,self.expected)
    def test_wrong_tid(self):
        e=self.edges();e[1]['tid']=4
        with self.assertRaises(ValueError):c.owner_gate(e,self.expected)
    def test_wrong_cycle(self):
        e=self.edges();e[1]['cycle']+=1
        with self.assertRaises(ValueError):c.owner_gate(e,self.expected)
    def test_missing_owner(self):
        with self.assertRaises(ValueError):c.owner_gate(self.edges()[:-2],self.expected)
    def test_unknown_old_value(self):
        ref=copy.deepcopy(self.reference)
        i=next(i for i,x in enumerate(ref) if x.instruction&127==0x73 and x.instruction>>20==0x342 and x.gpr_writes)
        x=ref[i];ref[i]=SimpleNamespace(**dict(vars(x),gpr_writes={next(iter(x.gpr_writes)):1}))
        with self.assertRaises(ValueError):c.csr_expected(ref,self.rows,c.runner.source_contract()[0]['ops'])
    def test_private_no_original_mutation(self):
        ns=c.namespace();self.assertIsNot(ns['architecture'],c.original.architecture)
        self.assertEqual(c.original.runner.NAME,'csr_satp_sepc_matrix785')
    def test_strict_count_and_address_specialization(self):
        code=c.specialize(c.original.scalar_gate.__code__)
        self.assertIn(664,code.co_consts);self.assertNotIn(673,code.co_consts)

    def architectural_rows(self):
        regs={i:0 for i in range(32)};rows=[]
        for i,x in enumerate(self.reference):
            r=dict(order=i,cycle=i+100,event='retire',trap=0,pc=x.pc,insn=x.instruction,
                   rd=0,rd_wdata=0,mem_addr=0,mem_rmask=0,mem_wmask=0,mem_wdata=0)
            if x.gpr_writes:r['rd'],r['rd_wdata']=next(iter(x.gpr_writes.items()))
            d=c.original.primitive.memory_decode(x.instruction)
            if d:
                addr=(regs[d['base']]+d['offset'])&((1<<64)-1)
                r['mem_addr']=addr;mask=((1<<d['size'])-1)<<(addr&7)
                if d['kind']=='write':
                    r['mem_wmask']=mask;r['mem_wdata']=regs[d['register']]&((1<<(8*d['size']))-1)
                else:r['mem_rmask']=mask
            regs.update(x.gpr_writes);regs[0]=0;rows.append(r)
        return rows

    def test_full_architecture_reference_replay(self):
        result=c.namespace()['architecture'](self.architectural_rows(),self.reference,
                                            self.pre['symbols'],c.runner.ELF.read_bytes())
        self.assertEqual(result['instructions'],664)
        self.assertEqual(result['memory_accesses'],168)
        self.assertEqual(result['checks'],44)

    def test_bad_scalar_memory_mask(self):
        rows=self.architectural_rows();r=next(r for r in rows if r['mem_wmask']);r['mem_wmask']^=1
        with self.assertRaises(ValueError):c.namespace()['architecture'](rows,self.reference,self.pre['symbols'],c.runner.ELF.read_bytes())

    def test_bad_scalar_gpr(self):
        rows=self.architectural_rows();r=next(r for r in rows if r['rd']);r['rd_wdata']^=1
        with self.assertRaises(ValueError):c.namespace()['architecture'](rows,self.reference,self.pre['symbols'],c.runner.ELF.read_bytes())

if __name__=='__main__':unittest.main()
