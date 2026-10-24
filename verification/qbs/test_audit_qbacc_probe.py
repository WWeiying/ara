import unittest

from audit_qbacc_probe import normalized_log
from run_qbacc_soc import check_probe
import test_qbacc_soc as fixture


class BinaryTraceFormat(fixture.ProbeChecker):
    def test_constant_zero_short_format(self):
        log=self.log.replace("store_valid=0000","store_valid=0")
        self.assertEqual(check_probe(normalized_log(log),self.trace)["commands"],13)

    def test_unknown_partial_and_nonzero(self):
        for field,value in (("store_valid","000x"),("store_valid","0x0"),
                            ("store_valid","00001"),("store_valid","1"),
                            ("owner","1x"),("fire","111x"),("fire","111")):
            original={"store_valid":"0000","owner":"1","fire":"1111"}[field]
            text=self.log.replace(field+"="+original,field+"="+value,1)
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                check_probe(normalized_log(text),self.trace)

    def test_unknown_geometry_and_counter(self):
        for text in (self.log.replace("vl=32 sew=2","vl=32x sew=2",1),
                     self.log.replace("success=1 fault=0","success=1x fault=0",1)):
            with self.assertRaises(ValueError):normalized_log(text)


if __name__=="__main__":unittest.main()
