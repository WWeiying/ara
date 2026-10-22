import json
import unittest

import qbs_even_hit_native762 as native


class ExactPartialBits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=json.loads(native.PROOF.read_bytes())
        cls.targets=native.targets(p)
        cls.c=dict(instances=[dict(scope=scope,design_module_checksum='1651389237',toggle_checksum='3657545390',
                                 signals=signals) for scope,signals in sorted(cls.targets.items())])
        cls.text=native.primitive.candidate(cls.c)

    def test_exact_new_set_and_complete_partial_complement(self):
        self.assertEqual(len(native.parse_el(self.text,self.c)),19328)
        self.assertTrue(all(0<len(s['bits'])<s['left']+1 for i in self.c['instances'] for s in i['signals']))

    def test_old_and_scale_candidates_disjoint(self):
        p=json.loads(native.PROOF.read_bytes())
        forbidden={(scope,r['signal'],r['bit']) for scope,d in p['scopes'].items() for r in d['records']
                   if r['classification'] in ('OLD1792_INVARIANT_PROJECTION','FINITE_MAPPING_IMPOSSIBLE_CANDIDATE')}
        actual={(i['scope'],s['name'],b) for i in self.c['instances'] for s in i['signals'] for b in s['bits']}
        self.assertFalse(actual & forbidden)

    def test_whole_vector_rejected(self):
        line=next(l for l in self.text.splitlines() if l.startswith('Toggle'))
        with self.assertRaises(ValueError):native.parse_el(self.text.replace(line,line.rsplit(' [',1)[0]),self.c)

    def test_protected_bit_rejected(self):
        s=self.c['instances'][0]['signals'][0]
        protected=next(b for b in range(s['left']+1) if b not in s['bits'])
        text=self.text.replace(s['name']+' ['+str(s['bits'][0])+']',s['name']+' ['+str(protected)+']')
        with self.assertRaises(ValueError):native.parse_el(text,self.c)

    def test_control_alias_and_single_checksum_rejected(self):
        s=self.c['instances'][0]['signals'][0]
        for text in (self.text.replace(s['name'],'write_be[0][0][0]'),
                     self.text.replace('1651389237 3657545390','1651389237')):
            with self.assertRaises(ValueError):native.parse_el(text,self.c)

    def test_missing_direction_and_checksum_rejected(self):
        line=next(l for l in self.text.splitlines() if l.startswith('Toggle'))
        for text in (self.text.replace(line+'\n','',1),self.text.replace('3657545390','1')):
            with self.assertRaises(ValueError):native.parse_el(text,self.c)

    def test_sourcepins_and_observed_counterexample_gate(self):
        p=json.loads(native.PROOF.read_bytes())
        self.assertTrue(p['all_compiled_hit_bits_checked_for_observed_counterexamples'])
        self.assertEqual(p['compiled_read_toggle_checksum'],'2833497324')
        self.assertFalse(p['excluded_initial_X'])


if __name__=='__main__':unittest.main()
