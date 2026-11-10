import random
import unittest

import run


def reference(words):
    maximum = max(w & 0x7fffffff for w in words)
    valid = (min(((w & 0x7fffffff)-1) & 0xffffffff for w in words) >= 0x007fffff and
             (maximum == 0 or 0x08800000 <= maximum <= 0x77000000))
    signed = next((w for w in words if (w & 0x7fffffff) == maximum), 0) if maximum else 0
    return valid, signed


def lanes(words, width):
    maxima = [0]*width; positions = [0xffffffff]*width
    for index, word in enumerate(words):
        lane = index % width; absolute = word & 0x7fffffff
        if absolute > maxima[lane]: maxima[lane], positions[lane] = absolute, index
    maximum = max(maxima)
    if not maximum: return 0
    return words[min(p for m, p in zip(maxima, positions) if m == maximum)]


class Contracts(unittest.TestCase):
    def test_global_ties(self):
        for width in (1, 4, 7, 8, 13, 16, 32):
            for first, second in ((31, 32), (3, 35), (127, 128), (0, 255)):
                words = [0x3e000000]*256; words[first] = 0x40000000; words[second] = 0xc0000000
                self.assertEqual(lanes(words, width), reference(words)[1])

    def test_random_positions(self):
        rng = random.Random(0x4a)
        for _ in range(100):
            words = [rng.choice((0, 0x80000000, 0x3f800000, 0xbf800000, 0x40000000, 0xc0000000)) for _ in range(256)]
            for width in (4, 7, 13, 32): self.assertEqual(lanes(words, width), reference(words)[1])

    def test_zeros(self):
        self.assertEqual(reference([0x80000000]*256), (True, 0))
        self.assertEqual(lanes([0x80000000]*256, 13), 0)

    def test_domain_edges(self):
        for word, good in ((0x087fffff, False), (0x08800000, True), (0x77000000, True),
                           (0x77000001, False), (1, False), (0x007fffff, False),
                           (0x7f800000, False), (0x7fc01234, False), (0x7f801234, False)):
            self.assertEqual(reference([word]*256)[0], good)

    def test_accepted_identity(self):
        self.assertEqual(run.BASE, 'da56aa750559c180d631b466de983ff2bb5d54d9')
        self.assertEqual(len(run.ACCEPTED), 4)
        self.assertIn('q8_K-m4-group-sums.h', run.ACCEPTED)

    def test_spike_receipt_mutations(self):
        valid = '0x0000000000000000\nSTAGE4_M4_VLEN bits=128\n'+run.SUMMARY+'\n'
        run.check_spike(valid, 0, 128)
        for bad in (valid.replace('checks=323', 'checks=322'), valid+run.SUMMARY+'\n',
                    valid.replace('0x0000000000000000', '0x0000000000000001'), valid+'TRAP\n',
                    valid.replace('fallback_entries=74', 'fallback_entries=0'),
                    valid.replace('bits=128', 'bits=1024')):
            with self.assertRaises(ValueError): run.check_spike(bad, 0, 128)
        with self.assertRaises(ValueError): run.check_spike(valid, 1, 128)

    def test_fp_preflight_mutation(self):
        body = '80000100 <bool qbs_experimental_m4_preflight::preflight<32ul>()>:\n 0: vredmaxu.vs v1,v2,v3\n 4: vredminu.vs v1,v2,v3\n'
        self.assertEqual(run.audit_preflight(body), 1)
        self.assertEqual(run.audit_preflight(body.replace('qbs_experimental_m4_preflight::preflight', 'preflight_probe')), 1)
        for instruction in ('fdiv.s', 'fmadd.s', 'vfmacc.vf', 'vfadd.vv', 'fcvt.w.s'):
            with self.assertRaises(ValueError): run.audit_preflight(body+' 8: '+instruction+' v1,v2,v3\n')

    def test_missing_preflight(self):
        with self.assertRaises(ValueError): run.audit_preflight('80000100 <other>:\n ret\n')
        with self.assertRaises(ValueError): run.audit_preflight('80000100 <qbs_experimental_m4_preflight::preflight<32>()>:\n ret\n')


if __name__ == '__main__': unittest.main()
