import unittest
from unittest.mock import patch
import qualify_half_fma_tail_source as q


class StrictTailTests(unittest.TestCase):
    def test_frozen_bijection(self):
        self.assertEqual(set(q.contract().values()),set(range(16)))

    def test_exact_tail(self):
        self.assertEqual(q.expected(3,31),((0,0x3c00,0),(0,0,0)))

    def test_not_predicate_padding(self):
        ports, result = q.expected(2,0)
        self.assertEqual(ports,(0x3bfe,0x3c01,0xbc00))
        self.assertEqual(result,(0x8010,0,0))

    def test_every_phase_index(self):
        for phase in range(4):
            for index in range(32 if phase == 3 else 64):
                ports,result = q.expected(phase,index)
                self.assertEqual(q.accepted(phase,index,ports,0,int(phase == 1),result[2]),result)

    def test_no_arbitrary_permutation(self):
        ports,result = q.expected(0,0)
        with self.assertRaises(ValueError):
            q.accepted(0,0,(ports[1],ports[0],ports[2]),0,0,result[2])

    def test_tail_not_ignored(self):
        for ports in ((1,0x3c00,0),(0,0x3c01,0),(0,0x3c00,1),(0xbc00,0x3c00,0x9000)):
            with self.assertRaises(ValueError): q.accepted(3,31,ports,0,0,0)

    def test_controls(self):
        ports,result = q.expected(0,0)
        for op,rm,mask in ((1,0,1),(0,1,1),(0,0,0)):
            with self.assertRaises(ValueError): q.accepted(0,0,ports,op,rm,mask)

    def test_pad_source_drift(self):
        with patch.object(q.life,'digest',return_value='0'*64):
            with self.assertRaises(ValueError): q.contract()


if __name__ == '__main__': unittest.main()
