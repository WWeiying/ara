import copy
from pathlib import Path
from types import SimpleNamespace
import unittest

import gap112_fof_flush as g


class Tests(unittest.TestCase):
    def fixture(self):
        symbols={n:0x80004000+0x400*i for i,n in enumerate(g.NAMES)}
        symbols['gf_read_vl']=symbols['gf_fof']+4
        memory=[(symbols[n]+4*i,v) for n,values in g.expected().items() for i,v in enumerate(values)]
        memory += [(0x801ffffc,g.WORD),(symbols['g75_result'],194),(symbols['g75_result']+4,0),
            (symbols['num_failed'],0),*[(symbols['g75_trap']+i,0) for i in (0,8,16)],(symbols['tohost'],1)]
        commits=[SimpleNamespace(pc=0x80000000,instruction=0x13,memory_accesses=memory),
            SimpleNamespace(pc=symbols['gf_fof'],instruction=0x01006407,memory_accesses=[]),
            SimpleNamespace(pc=symbols['gf_read_vl'],instruction=0xc2002573,memory_accesses=[])]
        return commits,symbols

    def test_oracle(self):
        c,s=self.fixture();self.assertEqual(g.validate(c,s)['checks'],194)

    def test_div_corruption(self):
        c,s=self.fixture();c[0].memory_accesses.append((s['gf_div']+4,0))
        with self.assertRaises(ValueError):g.validate(c,s)

    def test_neighbor_corruption(self):
        c,s=self.fixture();c[0].memory_accesses.append((s['gf_neighbor']+4,0))
        with self.assertRaises(ValueError):g.validate(c,s)

    def test_mask_or_fof_pair_drift(self):
        c,s=self.fixture();c[1].instruction|=1<<25
        with self.assertRaises(ValueError):g.validate(c,s)

    def test_vl_not_reduced(self):
        c,s=self.fixture();c[0].memory_accesses.append((s['gf_csr'],4))
        with self.assertRaises(ValueError):g.validate(c,s)

    def test_unexpected_trap(self):
        c,s=self.fixture();c[0].pc=s['trap_fail']
        with self.assertRaises(ValueError):g.validate(c,s)

    def test_actual_frozen_target(self):
        pins,target=g.binding()
        self.assertFalse(target['before']);self.assertEqual(target['raw_index'],78)
        self.assertEqual(target['destination'],'WAIT_IDLE');self.assertEqual(len(target['full_before_vector']),92)

    def test_frozen_foreground_namespace_is_private(self):
        before=g.frozen.BUDGET
        ns=g.namespace(Path('/sealed/preflight-manifest.json'),dict(elf_sha256='a'*64),dict(command=['sealed']))
        self.assertEqual(ns['BUDGET'],180);self.assertEqual(g.frozen.BUDGET,before)

    def test_stack_below_witness_and_one_adjacent_pair(self):
        self.assertIn('li sp, 0x801ff000',g.START.read_text())
        text=g.APP.read_text()
        self.assertEqual(text.count('vle32ff.v'),1)
        self.assertEqual(text.count('gf_fof:'),1)
        self.assertNotIn('fence',text[text.index('gf_fof:'):text.index('csrr %[vl]')])

    def test_actual_objdump_word_format(self):
        self.assertEqual(g.rvv_inventory('800020fc: 01046407    vle32ff.v v8,(s0),v0.t'),[(0x800020fc,0x01046407)])

    def test_scalar_and_compressed_not_vector(self):
        self.assertEqual(g.rvv_inventory('80002100: c20023f3   csrr t2,vl\n80002404: 6462 ld s0,0x18(sp)'),[])


if __name__=='__main__':unittest.main()
