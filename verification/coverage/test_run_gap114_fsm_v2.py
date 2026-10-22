import unittest
import run_gap114_fsm_v2 as m
from test_run_gap114_fsm import Oracle


class Successor(unittest.TestCase):
    def test_distinct_artifacts(self):
        self.assertTrue(m.core.PRE.name.endswith('-02'))
        self.assertTrue(m.core.RUN.name.endswith('-02'))
        self.assertEqual(m.core.APP.name,'vgap114_spec_load_flush_v2.c')

    def test_explicit_scalar_publication(self):
        source=m.core.APP.read_text()
        self.assertIn('g114_vrf[i]=g114_snapshot[i]',source)
        self.assertIn('#include "vgap114_spec_load_flush.c"',source)


if __name__=='__main__':unittest.main()
