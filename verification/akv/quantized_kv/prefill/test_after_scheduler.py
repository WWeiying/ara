import copy
import unittest
from after_scheduler import accepted_parent


class ParentGateTest(unittest.TestCase):
    def test_accept_and_reject(self):
        good = dict(state='PASS', elf_sha256='expected', performance_measured=True,
                    independent_protocol_checked=True, post_pins_match=True,
                    measured=dict(paired_bitexact=True, speedup=2., trials=[
                        dict(cycles=c, shared=s) for c,s in [(100,0),(50,1),(50,1),(100,0)]]))
        self.assertEqual(accepted_parent(good, 'expected'), 2.)
        for key in ('state', 'elf_sha256', 'performance_measured',
                    'independent_protocol_checked', 'post_pins_match'):
            bad = copy.deepcopy(good); bad[key] = None
            with self.subTest(key=key), self.assertRaises(ValueError):
                accepted_parent(bad, 'expected')
        for key,value in [('paired_bitexact',False),('speedup',3.),('trials',[])]:
            bad = copy.deepcopy(good); bad['measured'][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                accepted_parent(bad, 'expected')
        for key,value in [('cycles',0),('cycles',True),('shared',1)]:
            bad = copy.deepcopy(good); bad['measured']['trials'][0][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                accepted_parent(bad, 'expected')


if __name__ == '__main__': unittest.main()
