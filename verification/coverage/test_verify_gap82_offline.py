import unittest
from dataclasses import replace
import verify_gap82_offline as sidecar
from test_run_gap82_old_image import activity


class BackendVLTests(unittest.TestCase):
    def test_exact_backend_vl(self):
        a=activity();a.vl=128
        sidecar.activity_bytes(a,10,32)

    def test_other_vl_rejected(self):
        for vl in (0,1,32,64,127,129,256):
            a=activity();a.vl=vl
            with self.subTest(vl=vl),self.assertRaises(ValueError):
                sidecar.activity_bytes(a,10,32)

    def test_output_tail_source_unknown_and_missing_rejected(self):
        for field,value in [('data',0),('known_be',0),('source',3),('cycle',33)]:
            a=activity();a.vl=128;a.writes[0]=replace(a.writes[0],**{field:value})
            with self.subTest(field=field),self.assertRaises(ValueError):
                sidecar.activity_bytes(a,10,32)
        a=activity();a.vl=128;a.writes.pop()
        with self.assertRaises(ValueError):sidecar.activity_bytes(a,10,32)


if __name__ == '__main__':unittest.main()
