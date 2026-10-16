from pathlib import Path
import tempfile
import unittest
from fault_replay import assembly, run


class ZeroStrideFaultTests(unittest.TestCase):
    def test_nonzero_stride_register(self):
        for nf in (1, 2, 8):
            asm = assembly(8, fields=nf, strided=True)
            self.assertIn('ld t3,0(a5)', asm)
            self.assertIn('(a0),t3,v0.t', asm)
            self.assertNotIn('(a0),zero', asm)

    def test_invalid_controls_rejected_before_files_created(self):
        for options in (dict(zero_stride=True),
                        dict(strided=True, zero_stride=True, negative_stride=True),
                        dict(strided=True, zero_stride=True, negative_restart=True),
                        dict(negative_skip=True)):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)/'case'
                with self.assertRaises(ValueError):
                    run(out, 'unused-', **options)
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
