"""Exact native identity boundaries, using the real frozen scalar review."""
import copy
import json
import unittest
import capture_scalar_fma8 as m


class NativeEight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r=m.life.read_bound(m.REVIEW,m.REVIEW_SHA)
        cls.c=dict(instances=[dict(scope=i['scope'],design_module_checksum='2431620414',
            toggle_checksum=i['checksum'],signals=[dict(s,left=int(s['left']),right=int(s['right']))
            for s in i['targets']]) for i in r['instances']])
        cls.text=m.primitive.candidate_text(cls.c['instances'])

    def test_real_eight(self):
        self.assertEqual(len(m.records(self.text,self.c)),8)

    def test_semantic_reordering(self):
        text=m.primitive.candidate_text(list(reversed(self.c['instances'])))
        self.assertEqual(m.records(text,self.c),m.records(self.text,self.c))

    def test_checksum(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('3893821548','3893821549'),self.c)

    def test_bounds(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('product[47:0]','product[46:0]'),self.c)

    def test_type(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('logic product','wire product'),self.c)

    def test_duplicate(self):
        with self.assertRaises(ValueError):m.records(self.text+self.text,self.c)

    def test_missing(self):
        with self.assertRaises(ValueError):m.records('\n'.join(self.text.splitlines()[:-1]),self.c)

    def test_control_extra(self):
        with self.assertRaises(ValueError):m.records(self.text+'Toggle status "logic status[4:0]"\n',self.c)

    def test_direction_extra(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('Toggle product ', 'Toggle product 0to1 '),self.c)

    def test_typed_complement_disjoint(self):
        r=json.loads(m.REVIEW.read_bytes())
        for i in r['instances']:
            selected={s['name'] for s in i['targets']}
            protected=i['field_partition']['extension_seven_source_candidates']+i['field_partition']['protected_from_family51']+i['other_protected']
            self.assertFalse(selected & {s['name'] for s in protected})
            self.assertEqual(len(i['field_partition']['protected_from_family51']),40)


if __name__=='__main__':unittest.main()
