import json
import unittest

import qbs_scale_hit_native762_v2 as fixed


class ActualNativeFormat(unittest.TestCase):
    def setUp(self):
        self.c = json.loads((fixed.FIRST.parent/'config.json').read_bytes())
        self.text = fixed.FIRST.read_text()
        self.bank0,self.bank1 = self.c['instances']

    def test_actual_first_exact240(self):
        self.assertEqual(len(fixed.parse_el(self.text,self.c)),240)
        self.assertEqual(fixed.parse_el(self.text,self.c),
                         fixed.old.parse_el((fixed.FIRST.parent/'candidate.el').read_text(),self.c))

    def test_actual_old_failure_reproduced(self):
        with self.assertRaisesRegex(ValueError,'Checksum grammar'):
            fixed.old.parse_el(self.text,self.c)

    def test_new_candidate_omits_only_empty_bank1_section(self):
        text = fixed.candidate(self.c)
        self.assertNotIn(self.bank1['scope'],text)
        self.assertEqual(len(fixed.parse_el(text,self.c)),240)
        self.assertEqual(len(self.c['instances']),2)

    def test_bank0_module_only_forbidden(self):
        with self.assertRaises(ValueError):
            fixed.parse_el(self.text.replace('1651389237 3657545390','1651389237'),self.c)

    def test_protected_bank1_metric_forbidden(self):
        name = self.bank0['signals'][0]['name']
        text = self.text.replace('CHECKSUM: "1651389237 3657545390"',
                                'Toggle 0to1 '+name+' [17]\nCHECKSUM: "1651389237 3657545390"')
        with self.assertRaises(ValueError): fixed.parse_el(text,self.c)

    def test_module_checksum_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            fixed.parse_el(self.text.replace('CHECKSUM: "1651389237"','CHECKSUM: "1"'),self.c)

    def test_bounds_and_reg_mismatch_rejected(self):
        for text in (self.text.replace('[31:0]"','[30:0]"'),self.text.replace('"net ','"reg ')):
            with self.assertRaises(ValueError): fixed.parse_el(text,self.c)

    def test_protected_bit_and_whole_vector_rejected(self):
        for text in (self.text.replace(' [17]',' [16]'),self.text.replace(' [17]','')):
            with self.assertRaises(ValueError): fixed.parse_el(text,self.c)

    def test_exact_private_runtime_callbacks(self):
        ns = fixed.backend()
        for name in ('prepare','checked_config','run','verify'):
            self.assertIs(ns[name].__globals__['parse_el'],fixed.parse_el)
            self.assertIs(ns[name].__globals__['checked_config'],ns['checked_config'])
        self.assertEqual(ns['__file__'],str(fixed.Path(fixed.__file__).resolve()))


if __name__ == '__main__': unittest.main()
