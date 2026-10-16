import tempfile
import unittest
from pathlib import Path
import permutation


class PartitionValidation(unittest.TestCase):
    def test_invalid_selection_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as root:
            for selected in ([], [0,0], [-1], [21], [True]):
                output=Path(root)/'output'
                with self.assertRaises(ValueError):
                    permutation.run(output,'unused-',operation_ids=selected)
                self.assertFalse(output.exists())

    def test_invalid_shapes_and_reserved_operation(self):
        for selected in ([], ['e64_mf2'], ['e8_m1','e8_m1']):
            with self.assertRaises(ValueError):
                permutation.partition_shapes(selected,[0])
        with self.assertRaises(ValueError):
            permutation.partition_shapes(['e8_m8'],[20])
        self.assertEqual(permutation.partition_shapes(['e16_m8'],[20]),
                         [(16,'m8',[20])])

    def test_default_keeps_every_legal_operation(self):
        selected=permutation.partition_shapes()
        self.assertEqual(len(selected),22)
        for sew,lmul,ids in selected:
            self.assertEqual(ids,list(range(len(permutation.operations(sew,lmul)))))

    def test_split_preserves_exact_legal_operation_union(self):
        selected=permutation.partition_shapes(split_operations=True)
        self.assertEqual(len(selected),22*21-1)
        self.assertTrue(all(len(ids)==1 for _,_,ids in selected))
        for sew,lmul,ids in permutation.partition_shapes():
            self.assertEqual([item[2][0] for item in selected if item[:2]==(sew,lmul)],ids)

    def test_partition_keeps_original_operation_ids_and_assembly(self):
        self.assertEqual(permutation.partition_shapes(['e32_m1'],[19,1]),
                         [(32,'m1',[1,19])])
        assembly=permutation.assembly(32,'m1',True)
        for i in range(21):
            self.assertIn(f'op_{i}:',assembly)
        self.assertIn('csrw vstart,a7',assembly)
        source=Path(permutation.__file__).with_name('permutation_oracle.c').read_text()
        self.assertIn('if(!(PERMUTE_OP_MASK & (1U << op)))continue;',source)
        self.assertIn('for(unsigned trial=0;trial<(RESTART_PERMUTATIONS ? 4U:1U);++trial)',source)


if __name__=='__main__':
    unittest.main()
