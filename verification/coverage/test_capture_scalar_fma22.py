"""Real approved scalar22 fixture and complete typed native negative cases."""
import unittest
import capture_scalar_fma22 as m


class ExactTwentyTwo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r=m.life.read_bound(m.eight.REVIEW,m.eight.REVIEW_SHA)
        cls.c=dict(instances=[dict(scope=i['scope'],design_module_checksum='2431620414',
            toggle_checksum=i['checksum'],signals=[dict(t,left=int(t['left']),right=int(t['right'])) for t in
            i['field_partition']['initial_four']+i['field_partition']['extension_seven_source_candidates']])
            for i in r['instances']])
        cls.text=m.eight.primitive.candidate_text(cls.c['instances'])

    def test_actual_source_partition(self):
        self.assertEqual(len(m.records(self.text,self.c)),22)
        self.assertEqual(sum(s['logical_bits'] for i in self.c['instances'] for s in i['signals']),1566)

    def test_member_identity(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('operand_a.mantissa','operand_a.sign'),self.c)

    def test_checksum(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('3893821548','3893821549'),self.c)

    def test_bounds(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('mantissa_a[23:0]','mantissa_a[22:0]'),self.c)

    def test_type(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('logic product','wire product'),self.c)

    def test_duplicate(self):
        with self.assertRaises(ValueError):m.records(self.text+self.text,self.c)

    def test_no_carry(self):
        with self.assertRaises(ValueError):m.records(self.text+'Toggle sum_raw "logic sum_raw[76:0]"\n',self.c)

    def test_reorder(self):
        self.assertEqual(m.records(self.text,self.c),m.records(m.eight.primitive.candidate_text(list(reversed(self.c['instances']))),self.c))

    def test_complete_direction_pair(self):
        line='Toggle operand_a.mantissa "logic operand_a.mantissa[22:0]"'
        split=self.text.replace(line,line.replace('Toggle ','Toggle 0to1 ')+'\n'+line.replace('Toggle ','Toggle 1to0 '))
        self.assertEqual(m.records(split,self.c),m.records(self.text,self.c))
        for bad in (line.replace('Toggle ','Toggle 0to1 '),line+'\n'+line.replace('Toggle ','Toggle 0to1 ')):
            with self.assertRaises(ValueError):m.records(self.text.replace(line,bad),self.c)

    def test_prefix_full_dimensions(self):
        text=self.text.replace('logic operand_a.mantissa[22:0]','logic [22:0]operand_a.mantissa')
        self.assertEqual(m.records(text,self.c),m.records(self.text,self.c))

    def test_source_struct_and_sum(self):
        r=m.life.read_bound(m.eight.REVIEW,m.eight.REVIEW_SHA)
        lines=(m.life.ROOT/'hardware/deps/fpnew/src/fpnew_fma.sv').read_text().splitlines()
        for i in r['instances']:
            for t in i['field_partition']['extension_seven_source_candidates']:
                self.assertEqual(m.source_binding(t,lines)['native_type'],'logic')
        bad=list(lines);bad[95]='logic wrong_member;'
        with self.assertRaises(ValueError):m.source_binding(r['instances'][0]['field_partition']['extension_seven_source_candidates'][0],bad)


if __name__=='__main__':unittest.main()
