import unittest
import observer as o

class Completion(unittest.TestCase):
    def test_exact_boot_zero_vs_final_done(self):
        s={'_start':0x80000000,'__bss_start':0x80001000,'__bss_end':0x80008000,'fx_completed':0x80007060}
        self.assertFalse(o.completion_phase(False,0x80000046,0x0002b023,8,0,s))
        self.assertTrue(o.completion_phase(True,0x80000600,0x00a73023,8,o.DONE,s))
        for args in [(False,0x80000048,0x0002b023,8,0,s),
                     (False,0x80000046,0x0002b023,8,1,s),
                     (False,0x80000046,0x0002b023,1,0,s),
                     (True,0x80000600,0x00a73023,8,0,s),
                     (False,0x80000046,0x0002b023,8,0,dict(s,__bss_end=0x80007064))]:
            with self.subTest(args=args),self.assertRaises(ValueError):o.completion_phase(*args)

if __name__=='__main__':unittest.main(verbosity=2)
