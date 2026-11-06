import unittest
from check_output_native import BINDING,check_log
from test_selector_native_check import fixture


class NativeOutputTests(unittest.TestCase):
    def text(self,q4=1):
        return fixture(q4).replace('SELECTOR_','OUTPUT_NATIVE_').replace('aligned=','candidate=')+'\n'+BINDING

    def test_positive(self):
        for q4 in (0,1):
            self.assertEqual(check_log(self.text(q4),bytes(163840),q4)['speedup'],2)

    def test_wrong_baseline_or_bad_result(self):
        for old,new in (('baseline=register_pv','baseline=current_shared'),
                        ('commands=1','commands=0'),('errors=0','errors=1'),
                        ('OUTPUT_NATIVE_SUITE_PASS',''),('fcsr=1','fcsr=2')):
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_log(self.text().replace(old,new,1),bytes(163840),1)
