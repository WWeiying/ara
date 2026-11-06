#!/usr/bin/env python3
"""Strict evidence-parser mutation tests; no simulator or old campaign replay."""
from pathlib import Path
import tempfile
import unittest
import run_wide_clients as m


def row(tag, fields):
    return tag+' '+' '.join(f'{k}={v}' for k,v in fields.items())


def normal_fixture():
    rows=['WIDE_CLIENTS_BEGIN version=1']
    for w in (128,256):
        cases=[m.expected_case(w,o,p) for o in (0,1) for p in range(32)]
        rows += [row('WIDE_CLIENTS_CASE',c) for c in cases]
        for o in (0,1):
            beats=m.geometry(0x8003,61,4)[1]+m.geometry(0x9007,65,5 if w==256 and o==0 else 4)[1]
            for mode in (0,1):
                rows.append(row('WIDE_CLIENTS_FAULT',dict(width=w,owner=o,mode=mode,kind=3,ars=2,beats=beats,payload=0)))
        for o,mode,kind in ((0,2,5),(1,3,2)):
            rows.append(row('WIDE_CLIENTS_FAULT',dict(width=w,owner=o,mode=mode,kind=kind,ars=0,beats=0,payload=0)))
        rows.append(row('WIDE_CLIENTS_COPY_PASS',dict(width=w,vectors=64,fields=24)))
        rows.append(row('WIDE_CLIENTS_FIXTURE_PASS',dict(width=w,per_range=int(w==256),normal=64,faults=6,
            commands=70,payload=sum(c['payload'] for c in cases),ars=sum(c['ars'] for c in cases),
            beats=sum(c['beats'] for c in cases),lower_half=1,upper_half=2*int(w==256),full32=int(w==256),
            data_stalls=1,completion_stalls=1,stalled_faults=2,inactive_checks=1,
            mixed_pairs=int(w==256),akv_upper=int(w==256))))
    return '\n'.join(rows+[m.TERMINAL])+'\n'


class WideClientsTests(unittest.TestCase):
    def test_normal_exact(self):
        self.assertEqual(len(m.check_normal(0,normal_fixture())['cases']),128)

    def test_normal_diagnostics_and_terminal(self):
        text=normal_fixture()
        for bad in ('Fatal: other.sv\n','Fatal: ignored\n','Error-[TEST] bad\n','UVM_ERROR other\n'):
            with self.assertRaises(ValueError): m.check_normal(0,text+bad)
        for bad in (text.replace(m.TERMINAL,''),text+ m.TERMINAL+'\n',text.replace('normal=128','normal=127')):
            with self.assertRaises(ValueError): m.check_normal(0,bad)
        with self.assertRaises(ValueError): m.check_normal(1,text)

    def test_accounting_and_coverage(self):
        text=normal_fixture()
        mutations=(text.replace('max_outstanding=2','max_outstanding=1',1),
                   text.replace('upper_half=2','upper_half=0'),text.replace('full32=1','full32=0'),
                   text.replace('payload=0','payload=1',1),text.replace('fields=24','fields=23',1),
                   text.replace('stalled_faults=2','stalled_faults=0',1),
                   text.replace('phase=0','phase=1',1),text+'WIDE_CLIENTS_UNKNOWN value=1\n')
        for bad in mutations:
            with self.assertRaises(ValueError): m.check_normal(0,bad)

    def test_field_parser(self):
        for line in ('WIDE_CLIENTS_X x=1 x=2','WIDE_CLIENTS_X x=-1','WIDE_CLIENTS_X broken'):
            with self.assertRaises(ValueError): m.records(line)

    def test_negative_exit_zero_and_global_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            dut=Path(tmp)/'qbs_reader_narrow_view.sv'
            dut.write_text('// fixture\nelse $fatal(1, "'+m.NEGATIVE_REASON+'");\n')
            text=(m.NEGATIVE_ARMED+'\nFatal: "'+str(dut)+'", 2: dut at time 35\n'+
                  m.NEGATIVE_REASON+'\n$finish called from file "'+str(dut)+'"\n')
            self.assertEqual(m.check_negative(0,text,dut)['global_fatals'],1)
            self.assertEqual(m.check_negative(1,text,dut)['global_fatals'],1)
            for bad in (text+'Fatal: other.sv unrelated\n',text+'Fatal: "second.sv", 1: other\n',
                        text.replace(str(dut),'foreign.sv'),text.replace(', 2:',', 3:'),
                        text.replace(m.NEGATIVE_REASON,'WRONG_REASON'),text+m.TERMINAL+'\n',
                        text+'Error: unrelated\n',text+text,text.replace(m.NEGATIVE_ARMED,'')):
                with self.assertRaises(ValueError): m.check_negative(0,bad,dut)

    def test_geometry_independent_examples(self):
        self.assertEqual(m.geometry(0x10010,16,4),(1,1))
        self.assertEqual(m.geometry(0x10010,16,5),(1,1))
        self.assertEqual(m.geometry(0x21ff0,840,5),(2,27))
        self.assertEqual(m.geometry(0x21ff0,840,4),(2,53))


if __name__=='__main__':
    unittest.main()
