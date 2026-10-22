import copy
import unittest
from unittest.mock import patch
import prepare_scalar_slot_rotation793 as a


class Admission(unittest.TestCase):
    def fixture(self):
        before=dict(design={'shape':'same'},tests=['vdb%d'%i for i in range(792)],metrics={})
        single=dict(design=before['design'],tests=['new'],metrics={})
        for m,n in a.COUNTS.items():
            before['metrics'][m]={str(i):dict(width=2,checksum='5',bits='0x1') for i in range(n)}
            single['metrics'][m]={str(i):dict(width=2,checksum='5',bits='0x2') for i in range(n)}
        before['input_hashes']={}; single['input_hashes']={}
        return before,single

    def test_actual_full6162_OR_prefix(self):
        b,s=self.fixture(); after=a.full_union(b,s)
        self.assertEqual(sum(len(r) for r in after['metrics'].values()),6162)
        self.assertEqual(after['tests'],b['tests']+s['tests'])
        self.assertTrue(all(row['bits']=='0x3' for rows in after['metrics'].values() for row in rows.values()))

    def test_prefix_duplicate_and_shape_negatives(self):
        b,s=self.fixture()
        for mode in ('duplicate','short','design','missing','checksum','width','overflow'):
            bb,ss=copy.deepcopy(b),copy.deepcopy(s)
            if mode=='duplicate': ss['tests']=[b['tests'][0]]
            elif mode=='short': bb['tests'].pop()
            elif mode=='design': ss['design']={'shape':'wrong'}
            elif mode=='missing': ss['metrics']['line'].pop('0')
            elif mode=='checksum': ss['metrics']['line']['0']['checksum']='6'
            elif mode=='width': ss['metrics']['line']['0']['width']=3
            else: ss['metrics']['line']['0']['bits']='0x8'
            with self.subTest(mode=mode),self.assertRaises(ValueError): a.full_union(bb,ss)

    def test_base_is_exact792(self):
        self.assertEqual(a.life.digest(a.BASE/'admission-manifest.json'),a.BASE_SHA)
        self.assertEqual(a.BASE_SHA,'0aadd9e4fa71a5a582830a043fedc67669b0f53cea866a1b8147a5526c8f81f4')

    def test_actual_compiled_full_fields_not_historical_missing_subset(self):
        base=a.life.read_bound(a.BASE/'admission-manifest.json',a.BASE_SHA)
        rows=a.life.read_bound(a.BASE/'combined-toggle-bits.json',
            base['output_pins'][str(a.BASE/'combined-toggle-bits.json')])
        row=rows[a.c.SB]
        before={a.c.SB:dict(row,bits='0x0')}
        sample={a.c.SB:dict(row,bits=hex((1<<row['width'])-1))}
        fields=a.target_gain(before,sample)
        self.assertEqual(len(fields),12)
        self.assertTrue(all(len(f['gained'])==len(f['remaining_before'])==128 for f in fields))
        coordinates=[p for f in fields for p in f['gained']]
        self.assertEqual(len(set(coordinates)),1536)
        self.assertTrue(all(f['gained']==list(range(f['gained'][0],f['gained'][0]+128)) for f in fields))
        wrong=copy.deepcopy(sample);wrong[a.c.SB]['checksum']='0'
        with self.assertRaises(ValueError): a.target_gain(before,wrong)

    def test_no_qualification_no_evaluate(self):
        with self.assertRaises((FileNotFoundError,ValueError)): a.evaluate(a.life.OUT/'no-real-qualification','0'*64)


if __name__=='__main__': unittest.main()
