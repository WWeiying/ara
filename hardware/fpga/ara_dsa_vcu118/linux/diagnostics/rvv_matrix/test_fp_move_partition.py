import tempfile
import unittest
from pathlib import Path
import fp_moves


class PartitionValidation(unittest.TestCase):
    def test_invalid_selection_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as root:
            for selected in ([], [0,0], [-1], [8], [True]):
                output=Path(root)/'output'
                with self.assertRaises(ValueError):
                    fp_moves.run(output,'unused-',operations=selected)
                self.assertFalse(output.exists())

    def test_partition_uses_original_assembly(self):
        assembly=fp_moves.assembly(32,'m8',True)
        for index,(opcode,operands) in enumerate(fp_moves.OPS):
            self.assertIn(f'op_{index}:',assembly)
            self.assertIn(opcode+' '+operands,assembly)
        self.assertIn('csrw vstart,t2',assembly)


if __name__=='__main__':
    unittest.main()
