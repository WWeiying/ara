#!/usr/bin/env python3
import copy
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('resident_complete_work',HERE/'check_work.py')
c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
FIELDS='cycle event arch_seq vid lane source insn use_vd vd eew vl vstart addr be wdata nr_lanes vlen_bits'.split()


def fixture(kind):
    logs=[]
    expected=c.commands(kind)
    for i,command in enumerate(expected):
        shape=c.geometry(command)
        vid=i%8
        for lane in range(4):
            if not shape['writes'][lane]: continue
            r=dict(lane=lane,vid=vid,tokens=command['tokens'],elements=shape['elements'][lane],
                heads=2,issued=shape['fma'][lane],returned=shape['fma'][lane],
                writes=len(shape['writes'][lane]),flags=1,error=0)
            if command['mode']=='QK': r['dimensions']=128
            logs.append('[RESIDENT_'+command['mode']+'_LANE] '+' '.join(f'{k}={v}' for k,v in r.items()))
        r=dict(seq=i+1,vid=vid,cycles=100,error=0,flags=1,**shape['counts'])
        logs.append('[RESIDENT_'+command['mode']+'_PERF] '+' '.join(
            k+'='+(format(v,'04b') if k=='active' else str(v)) for k,v in r.items()))
    rows=[dict.fromkeys(FIELDS,'0')]
    rows[0].update(cycle='0',event='config',nr_lanes='4',vlen_bits='1024',insn='00000000')
    index=0
    for seq,insn in enumerate(c.signatures(kind),1):
        r=dict(rows[0],cycle=str(len(rows)),event='alloc',arch_seq=str(seq),vid=str(index%8),
               insn=f'{insn:08x}',use_vd='1',wdata='0000000000000000')
        resident=insn in (0x0485705b,0x0605705b)
        if resident:
            shape=c.geometry(expected[index])
            r.update(eew=str(shape['eew']),vl=str(shape['vl']))
        rows.append(r)
        if resident:
            for lane,addresses in enumerate(shape['writes']):
                for addr,be in addresses.items():
                    rows.append(dict(r,cycle=str(len(rows)),event='write',source='4',lane=str(lane),
                                     addr=str(addr),be=f'{be:02x}'))
            index+=1
        rows.append(dict(r,cycle=str(len(rows)),event='done'))
    return '\n'.join(logs),rows


class WorkTests(unittest.TestCase):
    def check_rows(self,rows,text,kind):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'vector.csv'
            with path.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            return c.check(path,text,kind)

    def test_valid_smoke_and_abba(self):
        for kind,count in (('smoke',6),('abba',12)):
            text,rows=fixture(kind)
            self.assertEqual(self.check_rows(rows,text,kind)['commands'],count)
        self.assertEqual(len(c.signatures('smoke')),6)
        self.assertEqual(len(c.signatures('abba')),478)

    def test_tail_masks_and_fma_count(self):
        shape=c.geometry(dict(mode='QK',tokens=9,heads=2,dimension=128,base=0))
        self.assertEqual(shape['fma'],[512,256,256,256])
        self.assertEqual(shape['writes'][0],{0:255,1:15,8:255,9:15})
        self.assertEqual(shape['counts']['result_words'],10)

    def test_probe_ledger_rejects_mutations(self):
        text,_=fixture('smoke')
        for old,new in (('seq=2','seq=1'),('issued=2048','issued=2047'),
                        ('source_words=0','source_words=1'),('query_reads=16','query_reads=15'),
                        ('active=1111','active=0111'),('flags=1','flags=2')):
            self.assertIn(old,text)
            with self.assertRaises(ValueError,msg=old):
                c.performance(text.replace(old,new,1),'smoke')
        with self.assertRaises(ValueError): c.performance(text.split('\n',1)[1],'smoke')

    def test_write_ledger_rejects_tail_and_final_write_loss(self):
        text,rows=fixture('smoke')
        tail=next(i for i,r in enumerate(rows) if r['event']=='write' and r['be']=='0f')
        altered=copy.deepcopy(rows)
        altered[tail]['be']='ff'
        with self.assertRaises(ValueError): self.check_rows(altered,text,'smoke')
        with self.assertRaises(ValueError): self.check_rows(rows[:tail]+rows[tail+1:],text,'smoke')

    def test_baseline_panel_removal_is_rejected(self):
        text,rows=fixture('abba')
        at=next(i for i,r in enumerate(rows) if r['event']=='alloc' and r['insn']=='0205745b')
        with self.assertRaises(ValueError): self.check_rows(rows[:at]+rows[at+1:],text,'abba')


if __name__=='__main__': unittest.main()
