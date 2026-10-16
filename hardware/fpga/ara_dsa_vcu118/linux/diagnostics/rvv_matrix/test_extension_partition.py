import tempfile
import unittest
from pathlib import Path
import extensions


class ExtensionPartitionTests(unittest.TestCase):
    def test_invalid_selection_has_no_output(self):
        with tempfile.TemporaryDirectory() as root:
            for operations in ([], [0, 0], [-1], [4], [True]):
                output = Path(root)/'output'
                with self.assertRaises(ValueError):
                    extensions.run(output, 'unused-', operations=operations)
                self.assertFalse(output.exists())
            with self.assertRaises(ValueError):
                extensions.run(output, 'unused-', only=['unknown'])
            self.assertFalse(output.exists())

    def test_fractional_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)/'output'
            with self.assertRaises(ValueError):
                extensions.run(output, 'unused-',
                    only=['rvv_extension_e16_m1_vf2'], operations=[2])
            self.assertFalse(output.exists())

    def test_original_operation_assembly_is_retained(self):
        assembly = extensions.assembly(16, 'm8', 2, 'm4')
        for op in range(4):
            self.assertIn(f'op_{op}:', assembly)
        self.assertIn('vzext.vf2 v24,v28,v0.t', assembly)
        self.assertIn('vsext.vf2 v24,v28,v0.t', assembly)


if __name__ == '__main__':
    unittest.main()
