"""The successor changes only unmeasured buffer checking and its self-test."""
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent


class ScopeTest(unittest.TestCase):
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
