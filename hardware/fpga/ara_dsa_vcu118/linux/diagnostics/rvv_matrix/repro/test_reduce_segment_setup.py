import unittest
from reduce_segment_setup import first_operation
from trace_masks import TOOLS
import segments


class SegmentReductionTests(unittest.TestCase):
    def test_archived_first_operation_unchanged(self):
        for sew,lmul in ((16,'m1'),(32,'mf2'),(64,'m2')):
            source=segments.assembly(sew,lmul)
            reduced=first_operation(source)
            self.assertEqual(reduced,source[:source.index('.global op_1\n')])
            self.assertIn(f'vle{sew}.v v24,(a6)',reduced)
            self.assertIn(f'vlseg3e{sew}.v v24,(a0),v0.t',reduced)

    def test_invalid_boundaries_rejected(self):
        source=segments.assembly(16,'m1')
        for bad in ('',source.replace('.global op_1\n',''),source.replace('capacity:','unknown:')):
            with self.assertRaises(ValueError):first_operation(bad)


if __name__=='__main__':unittest.main()
