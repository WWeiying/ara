import copy
from types import SimpleNamespace
import unittest

import build_operand_index_snapshot_preflight as p


def fixture():
    names = p.SYMBOLS
    symbols = {name:0x80000000+i*0x2000 for i,name in enumerate(names)}
    indices, source, after = p.images()
    outputs = {'indices':indices,'source':source,
               'replay_dump':[0x07070707]*32+after+[0x0a0a0a0a]*32,
               'replay_csr':[37,17,13,0,37,0],'g75_trap':[0,0,0],
               'g75_result':[p.CHECKS,0],'num_failed':[0],'tohost':[1]}
    writes = []
    for name,values in outputs.items():
        size = 8 if name in ('replay_csr','g75_trap','tohost') else 4
        writes += [(symbols[name]+size*i,v) for i,v in enumerate(values)]
    blob = b''.join(v.to_bytes(4,'little') for v in after)
    c = SimpleNamespace(pc=symbols['replay_indexed_load'],memory_accesses=writes,
        instruction=p.WORD|(12<<15),vector_sew=32,vector_lmul='m2',vector_vl=37,
        vector_vstart=13,vector_tail_agnostic=False,vector_mask_agnostic=False,
        vector_writes={8:int.from_bytes(blob[:128],'little'),9:int.from_bytes(blob[128:],'little')})
    return [c],symbols


class Preflight(unittest.TestCase):
    def test_exact_oracle(self):
        c,s = fixture()
        self.assertEqual(p.validate(c,s,'')['checks'],457)

    def test_active_prefix_tail(self):
        idx,data,after = p.images()
        self.assertEqual(after[:13],idx[:13])
        self.assertEqual(after[37:],idx[37:])
        self.assertEqual(after[13:37],[data[idx[i]//4] for i in range(13,37)])
        self.assertEqual((13//8)*2 >> 1,1)

    def test_wrong_prefix_active_tail_or_neighbor(self):
        for index in (0,32,44,69,127):
            c,s = fixture()
            a = s['replay_dump']+4*index
            c[0].memory_accesses = [(addr,v^1 if addr == a else v) for addr,v in c[0].memory_accesses]
            with self.assertRaisesRegex(ValueError,'output differs'):
                p.validate(c,s,'')

    def test_wrong_csr_or_input(self):
        for name in ('replay_csr','source','indices'):
            c,s = fixture()
            c[0].memory_accesses = [(a,v^1 if a == s[name] else v) for a,v in c[0].memory_accesses]
            with self.assertRaises(ValueError):
                p.validate(c,s,'')

    def test_wrong_vector_register_or_bytes(self):
        c,s = fixture()
        c[0].vector_writes[8] ^= 1
        with self.assertRaisesRegex(ValueError,'destination image'):
            p.validate(c,s,'')
        c,s = fixture()
        c[0].vector_writes[10] = 0
        with self.assertRaisesRegex(ValueError,'destination group'):
            p.validate(c,s,'')

    def test_wrong_policy_start_opcode_or_population(self):
        for attribute,value in (('vector_vstart',0),('vector_tail_agnostic',True),('instruction',0)):
            c,s = fixture()
            setattr(c[0],attribute,value)
            with self.assertRaises(ValueError):
                p.validate(c,s,'')
        c,s = fixture()
        with self.assertRaises(ValueError):
            p.validate([*c,copy.deepcopy(c[0])],s,'')

    def test_trap_and_failed_terminal_rejected(self):
        c,s = fixture()
        with self.assertRaisesRegex(ValueError,'trap'):
            p.validate(c,s,'exception illegal instruction')
        c[0].memory_accesses = [(a,3 if a == s['tohost'] else v) for a,v in c[0].memory_accesses]
        with self.assertRaises(ValueError):
            p.validate(c,s,'')


if __name__ == '__main__':
    unittest.main()
