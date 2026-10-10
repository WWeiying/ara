import re
import unittest
import build_gap113_payload_full8_cached as b


class Cached(unittest.TestCase):
    def test_static_input_bytes_exact(self):
        header=b.inputs_header()
        rows=re.findall(r'gap110_(weights|activation)([01])\[(\d+)\]=\{([^}]+)\}',header)
        self.assertEqual(len(rows),4)
        for name,phase,count,values in rows:
            blob=b''.join(int(v,16).to_bytes(8,'little') for v in re.findall(r'UINT64_C\((0x[0-9a-f]+)\)',values))
            expected=b.fixture(int(phase))[0 if name=='weights' else 1]
            self.assertEqual(blob,expected);self.assertEqual(len(blob),int(count)*8)

    def test_no_runtime_recipe_same_shape_fullbody(self):
        source=(b.APP/'main.c').read_text()
        self.assertNotIn('full8_prepare',source)
        self.assertNotIn('for (',source)
        self.assertEqual(source.count('{8,8,1,5,3,4,'),2)
        self.assertIn('#include "checked_body.inc"',source)
        self.assertIn('full8_checked_body()',source)
        self.assertNotEqual(b.APP,b.frozen.APP)

    def test_private_builder_does_not_mutate_frozen(self):
        self.assertNotEqual(b.frozen.PRE,b.PRE)
        self.assertEqual(b.frozen.common.Build,b.common.Build)


if __name__=='__main__':unittest.main()
