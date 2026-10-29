import copy
import unittest
from compare_projection import compare


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.build = dict(state='CANONICAL_SOC_BUILT_NOT_EXECUTED', post_pins_match=True,
                          image_pins={'image': 'hash'}, config={'vlen': '1024'})
        self.run = dict(state='PASS', post_pins_match=True, performance_measured=True,
                        image_pins={'image': 'hash'}, elf_sha256='same-elf', measured=dict(
                            state='PASS', traffic=dict(commands=256, result_bytes=131072),
                            trials=[dict(id=i, candidate=int(i in (1, 2)), hits=2, misses=1,
                                         stores=1, fcsr=17, vcsr=5, errors=0,
                                         total=100, prep=20, execute=70) for i in range(4)]))

    def test_separate_software_paths(self):
        new = copy.deepcopy(self.run)
        for i in (1, 2):
            new['measured']['trials'][i]['total'] = 80
        result = compare(self.run, new, self.build, self.build)['variants']
        self.assertEqual(result['original_sums']['total']['speedup'], 1)
        self.assertEqual(result['parallel_sums']['total']['speedup'], 1.25)

    def test_reject_invalid_pair(self):
        for key, value in (('elf_sha256', 'other'), ('state', 'FAIL'),
                           ('post_pins_match', False), ('image_pins', {})):
            new = copy.deepcopy(self.run)
            new[key] = value
            with self.assertRaises(ValueError):
                compare(self.run, new, self.build, self.build)
        changed = copy.deepcopy(self.build)
        changed['config']['vlen'] = '256'
        with self.assertRaises(ValueError):
            compare(self.run, self.run, self.build, changed)
