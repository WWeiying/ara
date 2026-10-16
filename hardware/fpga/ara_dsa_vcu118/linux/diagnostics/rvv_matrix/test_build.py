import importlib.util
from pathlib import Path
import unittest
import re

path=Path(__file__).with_name('build.py')
spec=importlib.util.spec_from_file_location('rvv_build',path)
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)

class MatrixTest(unittest.TestCase):
    def test_extension_is_bounded_and_preserves_csrs(self):
        self.assertEqual(len(build.EXTRA_OPS),20)
        for sew,lmul in build.shapes():
            asm=build.assembly(sew,lmul,extra=True,agnostic=True)
            self.assertEqual(asm.count('csrwi vxsat, 0'),20)
            self.assertEqual(asm.count('csrw vxrm, t4'),20)
            self.assertEqual(asm.count('csrw vxsat, t5'),20)
            self.assertIn('ta, ma',asm)
            self.assertIn('vredmax.vs v24, v8, v16, v0.t',asm)
            self.assertNotIn('vfadd',asm)

    def test_fp_fixture_shape_and_signed_zero(self):
        for sew in (32,64):
            header=build.fp_header(sew)
            values=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',header)]
            self.assertEqual(len(values),8+10*64)
            self.assertEqual(values[2],1<<(sew-1))
            self.assertEqual(values[3],0)
            canonical=0x7fc00000 if sew==32 else 0x7ff8000000000000
            self.assertEqual(values[8+3*64+2*8+3],canonical)
            self.assertEqual(values[8+4*64+2*8+3],1<<(sew-1))
            self.assertEqual(values[8+5*64+2*8+3],0)

    def test_shapes(self):
        shapes=build.shapes()
        self.assertEqual(len(shapes),22)
        self.assertEqual(len(set(shapes)),22)
        self.assertIn((8,'mf8'),shapes)
        self.assertNotIn((64,'mf2'),shapes)

    def test_register_groups_and_restart_check(self):
        for sew,lmul in build.shapes():
            asm=build.assembly(sew,lmul)
            self.assertEqual(asm.count('csrr a0, vstart'),25+(10 if sew>=32 else 0))
            self.assertIn('vcompress.vm v24, v8, v0\n',asm)
            self.assertNotIn('vcompress.vm v24, v8, v0, v0.t',asm)
            self.assertIn('vle%d.v v24, (a0), v0.t'%sew,asm)
            for part in asm.split('csrr a0, vstart')[1:]:
                self.assertTrue(part.startswith('\nvsetvli'))

if __name__=='__main__':unittest.main()
