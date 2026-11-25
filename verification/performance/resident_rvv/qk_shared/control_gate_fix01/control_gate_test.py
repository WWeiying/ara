#!/usr/bin/env python3
"""Mutation tests for the ownership gate receipt checker, not RTL evidence."""
import copy
import re
import unittest
from unittest.mock import patch

import control_gate as gate


def receipts():
    rows=[]
    for identity in gate.expected_cases():
        row=dict(identity,**gate.work(identity),error=int(identity['phase']!=0),
                 launches=int(identity['phase'] not in (1,5,6,7,9,10)),
                 barrier_hold=12,debt_hold=24,busy_hold=0,abort_busy=0,
                 stalls=8,checks=0,cycles=2000)
        phase=identity['phase']
        if phase:
            row.update(results=0,acks=0,debt_hold=0)
            if phase in (1,5,6,7,9,10):
                row.update(seeds=0,coefficients=0,values=0,queries=0,columns=0,reads=0,
                           barrier_hold=0,stalls=0)
            if phase in (2,8):
                row.update(seeds=1,coefficients=0,values=0,queries=0,columns=0,reads=0)
            if phase==3:
                row.update(seeds=8,coefficients=0,values=0,queries=2,columns=1,
                           busy_hold=3,abort_busy=7)
        row['checks']=sum(row[k] for k in ('seeds','coefficients','values','results'))
        rows.append(row)
    return rows


def render(rows):
    def line(prefix,values):
        return prefix+' '+' '.join(f'{k}={v}' for k,v in values.items())+'\n'
    return ''.join(line('CONTROL_GATE_CASE',row) for row in rows)+line('CONTROL_GATE_PASS',
        dict(cases=len(rows),checks=sum(r['checks'] for r in rows),cycles=sum(r['cycles'] for r in rows)+500))


class ControlGateChecker(unittest.TestCase):
    def test_untouched_vrf_matches_initializer(self):
        source=(gate.HERE/'control_gate.sv').read_text()
        def check(text):
            initializer=re.search(r"vrf\[l\]\[w\]=(64'h[0-9a-f]+);",text)
            expected=re.search(r"logic \[63:0\] expected=(64'h[0-9a-f]+);",text)
            self.assertIsNotNone(initializer)
            self.assertIsNotNone(expected)
            self.assertEqual(int(initializer[1][4:],16),int('a5'*8,16))
            self.assertEqual(int(expected[1][4:],16),int(initializer[1][4:],16))
        check(source)
        with self.assertRaises(AssertionError):
            check(source.replace("expected=64'ha5a5a5a5a5a5a5a5;", "expected=64'ha5a5a5a5a5a5a5;"))

    def test_complete(self):
        checked=gate.check_log(render(receipts()))
        self.assertEqual(checked['totals']['cases'],43)

    def test_required_matrix(self):
        cases=gate.expected_cases()
        self.assertEqual({(c['tokens'],c['heads']) for c in cases if c['qk'] and not c['phase']},
                         {(t,h) for t in (1,2,3,17,64) for h in (1,2)})
        self.assertEqual({c['phase'] for c in cases},set(range(11)))
        for i,c in enumerate(cases):
            if c['phase']:
                self.assertEqual([(v['qk'],v['phase']) for v in cases[i+1:i+3]],[(1,0),(0,0)])

    def test_geometry(self):
        for t in (1,2,3,17,64):
            for h in (1,2):
                row=dict(qk=1,tokens=t,heads=h,dimensions=64)
                independent=sum(((len(range(l,t,4))+1)//2)*h for l in range(4))
                self.assertEqual(gate.work(row)['seeds'],independent)
        self.assertEqual(gate.work(dict(qk=1,tokens=64,heads=2,dimensions=128))['results'],64)

    def test_identity_and_work_mutations(self):
        base=receipts()
        mutations=[(1,'base',0),(1,'sources',1),(1,'seeds',0),(1,'coefficients',0),
                   (1,'values',0),(1,'results',0),(1,'acks',0),(1,'queries',0),(1,'columns',0),
                   (1,'reads',1),(1,'error',1),(1,'launches',0),(1,'cycles',12001),
                   (1,'barrier_hold',0),(1,'debt_hold',0),(1,'stalls',0),(1,'checks',0)]
        for index,key,value in mutations:
            with self.subTest(key=key):
                rows=copy.deepcopy(base)
                rows[index][key]=value
                with self.assertRaises(ValueError):
                    gate.check_log(render(rows))

    def test_failed_phase_mutations(self):
        base=receipts()
        mutations=[(1,'launches',1),(1,'seeds',1),(2,'seeds',0),(3,'busy_hold',0),
                   (3,'abort_busy',0),(4,'barrier_hold',0),(4,'values',0),
                   (5,'queries',1),(6,'launches',1),(7,'results',1),
                   (8,'sources',0),(9,'error',0),(10,'sources',0)]
        for phase,key,value in mutations:
            with self.subTest(phase=phase,key=key):
                rows=copy.deepcopy(base)
                next(r for r in rows if r['phase']==phase)[key]=value
                with self.assertRaises(ValueError):
                    gate.check_log(render(rows))

    def test_missing_duplicated_reordered(self):
        rows=receipts()
        for bad in (rows[:-1],rows+[rows[-1]],rows[1:]+rows[:1]):
            with self.assertRaises(ValueError):
                gate.check_log(render(bad))

    def test_diagnostics_and_receipt_syntax(self):
        good=render(receipts())
        for bad in (good+'Error: assertion\n',good+'Fatal: failure\n',
                    good+'Warning-[PROTO]\n',good+'CONTROL_GATE_PASS cases=43 checks=1 cycles=1\n',
                    good.replace('id=1 ','id=1 id=1 ',1),good.replace('id=1 ','id=-1 ',1),
                    good.replace('id=1 ','bogus=1 ',1),good.replace('id=1 ','id=1 extra=2 ',1),
                    good.replace('CONTROL_GATE_PASS','CONTROL_GATE_UNKNOWN'),
                    good[good.index('CONTROL_GATE_PASS'):]+good[:good.index('CONTROL_GATE_PASS')]):
            with self.assertRaises(ValueError):
                gate.check_log(bad)

    def test_pin_drift(self):
        with patch.object(gate,'sha',return_value='new'):
            with self.assertRaisesRegex(ValueError,'identity drift'):
                gate.verify({'owned-file':'old'})


if __name__=='__main__':
    unittest.main()
