"""The successor changes only unmeasured buffer checking and its self-test."""
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent


class ScopeTest(unittest.TestCase):
    def test_group_checks_only_defer_weight_rescans(self):
        q=(HERE/'projection_pair_groupcheck.c').read_text()
        q=q.replace('(trial==3 && weight_hash!=hash_bytes(projection_weights,1536*6*144));',
                    'weight_hash!=hash_bytes(projection_weights,1536*6*144);',1)
        self.assertEqual(q,(HERE/'projection_pair_fastcheck.c').read_text())
        q=(HERE/'context_qkv_pair_groupcheck.c').read_text()
        q=q.replace('errors += hash(qkv_input,1536*4)!=ih;\n        if(trial==3) errors += ',
                    'errors += hash(qkv_input,1536*4)!=ih||',1)
        self.assertEqual(q,(HERE/'context_qkv_pair_fastcheck.c').read_text())

    def test_measurement_bodies_unchanged(self):
        for stem,size in (('projection_pair','count'),('context_qkv_pair','bytes')):
            with self.subTest(stem=stem):
                original=(HERE/(stem+'.c')).read_text()
                successor=(HERE/(stem+'_fastcheck.c')).read_text()
                successor=successor.removeprefix('#include "integrity_words.h"\n')
                successor=successor.replace(
                    f'    if ({size}>=16384) return q8k_integrity_words(data,{size});\n','',1)
                successor=successor.replace('unsigned errors=q8k_integrity_selftest();','unsigned errors=0;',1)
                self.assertEqual(successor,original)


if __name__=='__main__':unittest.main()
