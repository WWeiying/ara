"""Negative gates and software fixtures; never launch the frozen simulator."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gather_war797 as g


class GatherTests(unittest.TestCase):
    def test_four_round_integer_gold(self):
        for r in range(4):
            c=g.case(r);a,idx,mem=c['sources']
            self.assertEqual(len(idx),1024)
            self.assertEqual(c['snapshots'][1],bytes(a[i] for i in idx))
            self.assertEqual(c['snapshots'][2],bytes(mem[i] for i in idx))
            self.assertNotEqual(c['snapshots'][1],c['snapshots'][2])
            self.assertEqual(c['csr'],[1024,1024,3,0,0,0])

    def test_reverse_and_repeated(self):
        self.assertEqual(g.case(0)['sources'][1][:256],bytes(range(255,-1,-1)))
        idx=g.case(1)['sources'][1]
        self.assertTrue(all(len(set(idx[i:i+4]))==1 for i in range(0,1024,4)))
        self.assertEqual(len(set(idx)),256)

    def test_bounds(self):
        for c in (-1,4,True):
            with self.assertRaises(Exception):g.case(c)

    def test_snapshot_guard_layout(self):
        self.assertEqual(len(g.image(bytes(1024))),1056)
        self.assertEqual(g.image(bytes(1024))[:16],g.GUARD.to_bytes(8,'little')*2)

    def test_fixture_size(self):
        syms={n:0x80002000+i*0x10000 for i,n in enumerate(('gw_source','gw_snapshot','gw_csr','g75_result','num_failed','gw_checks'))}
        wanted,reads=g.expected_footprint(syms)
        self.assertEqual(len(reads),12672*2+192)
        self.assertEqual(len(wanted),len(reads)+16)

    def test_exact797_targets(self):
        ts,pins=g.targets()
        self.assertEqual(len(ts),11)
        self.assertEqual(sum(len(t['raw_coordinates']) for t in ts),176)
        self.assertTrue(pins)

    def test_run_without_authorization_rejected(self):
        with patch.object(g,'invoke_run') as launch:
            with self.assertRaises(Exception):g.main(['run','--output','/tmp/not-allowed'])
            launch.assert_not_called()

    def test_prepare_with_authorization_rejected(self):
        with patch.object(g,'prepare') as prepare:
            with self.assertRaises(Exception):g.main(['prepare','--output','/tmp/not-allowed','--parent-authorized'])
            prepare.assert_not_called()

    def test_exact_toggle_or_negative(self):
        a={str(i):dict(width=2,checksum='1',bits='0') for i in range(2989)}
        b=copy.deepcopy(a);b['0']['checksum']='2'
        with self.assertRaises(Exception):g.mature.exact_toggle_union(a,b)

    def test_bad_reference_trap(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'trace';p.write_text('exception synthetic\n')
            with patch.object(g.build,'parse_spike_commits',return_value=[]):
                with self.assertRaises(Exception):g.validate(p,{'trap_fail':0})


if __name__=='__main__':unittest.main()
