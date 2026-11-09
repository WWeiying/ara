#!/usr/bin/env python3
from pathlib import Path
import unittest

import experiment as exp


def fixture():
    sf=exp.reference.OrderedReference().sf
    lines=[]
    flags_by_id=[]
    for i,t in enumerate((64,64,9)):
        probability=[0x3e000001+(i*71+k)*37 for k in range(128)]
        seed=[0x3800+k for k in range(256)]
        scale=[0x3f800000]*2
        source=seed+[0x7d01]*128
        flags=0
        for head in range(2):
            for token in range(t):
                source[256+2*token+head],ex=sf.evaluate('cast',32,16,0,probability[64*head+token])
                flags|=ex
        flags_by_id.append(flags)
        for kind,data,width in (('probability',probability,8),('seed',seed,4),
                                ('scale',scale,8),('source',source,4)):
            bits=''.join(f'{value:0{width}x}' for value in data)
            lines.append(f'PV_PREP_DATA id={i} kind={kind} bits={bits}')
    for i,t in enumerate((64,64,9)*2):
        lines.append(f'PV_PREP_META id={i} tokens={t} dimension=128 heads=2 issue=200 dump=400 '
                     f'fcsr_before=16 fcsr_after={16|flags_by_id[i%3]}')
    lines.append('PV_PREP_COMPLETE records=6 errors=0')
    return '\n'.join(lines)+'\n'


class PreparationTests(unittest.TestCase):
    def test_fixture_accepts_only_defined_source(self):
        result=exp.parse_preparation(fixture())
        self.assertEqual(len(result['records']),6)
        self.assertFalse(result['complete_call_speedup'])
        self.assertEqual(result['records'][2]['active_halfwords'],274)

    def test_numerical_seed_coefficient_and_input_mutations(self):
        text=fixture()
        for label,index in (('source',0),('source',256*4),('seed',0),('scale',0)):
            rows=text.splitlines()
            at=next(i for i,r in enumerate(rows) if r.startswith(f'PV_PREP_DATA id=0 kind={label} '))
            prefix,bits=rows[at].split(' bits=')
            bits=bits[:index]+('0' if bits[index]!='0' else '1')+bits[index+1:]
            rows[at]=prefix+' bits='+bits
            with self.subTest(label=label,index=index),self.assertRaises(ValueError):
                exp.parse_preparation('\n'.join(rows)+'\n')

    def test_flags_rounding_shape_and_timing_mutations(self):
        text=fixture()
        for old,new in (('fcsr_after=17','fcsr_after=1'),('fcsr_after=17','fcsr_after=16'),
                        ('fcsr_before=16','fcsr_before=176'),('tokens=9','tokens=8'),
                        ('dimension=128','dimension=96'),('issue=200','issue=0'),
                        ('dump=400','dump=199'),('errors=0','errors=1')):
            self.assertIn(old,text)
            with self.subTest(old=old,new=new),self.assertRaises(ValueError):
                exp.parse_preparation(text.replace(old,new,1))

    def test_missing_extra_duplicate_and_short_records(self):
        text=fixture()
        data=next(x for x in text.splitlines(True) if x.startswith('PV_PREP_DATA'))
        meta=next(x for x in text.splitlines(True) if x.startswith('PV_PREP_META'))
        for bad in (text.replace(data,'',1),text+data,text+meta,
                    text.replace(data,data[:-3]+'\n',1),
                    text+'PV_PREP_COMPLETE records=6 errors=1\n',
                    text+'PV_PREP_COMPLETE garbage\n',text+'PV_PREP_UNKNOWN x=1\n',
                    text+'PV_PREP_COMPLETE records=6 errors=0\n'):
            with self.assertRaises(ValueError): exp.parse_preparation(bad)

    def test_strong_control_and_helper_recipes(self):
        cmds=exp.recipes(Path('/tmp/resident_pv_prepare_test'))
        self.assertEqual([c['label'] for c in cmds],['compile-main','compile-rotation',
            'compile-prepare','compile-strong-control','link','disassembly','segments'])
        argv=next(c['argv'] for c in cmds if c['label']=='compile-strong-control')
        self.assertIn('-Dresident_pv_rotation_selected=resident_pv_rotation_always',argv)
        self.assertIn('-D__wrap_akv_experimental_pv_f16_pair=resident_pv_rotation_body',argv)
        self.assertIn('prepare.o',' '.join(next(c['argv'] for c in cmds if c['label']=='link')))


if __name__=='__main__': unittest.main()
