#!/usr/bin/env python3
"""Negative tests for the standalone reader evidence checker."""
import unittest
import reader_gate as gate


def record(tag, row):
    return tag+' '+' '.join(f'{k}={v}' for k,v in row.items())+'\n'


def fixture():
    cases = gate.expected_cases()
    text = ''.join(record('READER_GATE_CASE', row) for row in cases)
    text += ''.join(record('READER_GATE_INTERRUPT', dict(phase=p, reset=r))
                    for r in range(2) for p in range(4))
    text += ''.join(record('READER_GATE_CANCEL', dict(phase=p, busy_cycles=8 if p==2 else 0,
                                                    repeat_pulses=int(p==2))) for p in range(4))
    text += record('READER_GATE_PASS', dict(normal=232,cancel=4,reset=4,invalid=4,
        checks=1000000,qlatency=10000,vlatency=100000,stalls=1,lane_stalls=1,held_done=1200))
    return text


class Evidence(unittest.TestCase):
    def test_complete_ledger(self):
        self.assertEqual(len(gate.check_log(fixture())['cases']), 232)

    def test_missing_reordered_duplicate(self):
        rows=fixture().splitlines(True)
        for bad in (''.join(rows[1:]), rows[1]+rows[0]+''.join(rows[2:]), fixture()+rows[0]):
            with self.assertRaises(ValueError): gate.check_log(bad)

    def test_bad_work(self):
        for key in ('qreads=8', 'columns=16', 'base=7', 'tokens=17'):
            with self.assertRaises(ValueError): gate.check_log(fixture().replace(key,key[:-1]+'0',1))

    def test_summary_and_protocol(self):
        for old,new in (('normal=232','normal=231'), ('stalls=1','stalls=0'),
                        ('qlatency=10000','qlatency=1'), ('vlatency=100000','vlatency=1'),
                        ('checks=1000000','checks=1'), ('held_done=1200','held_done=0'),
                        ('phase=2 reset=1','phase=1 reset=1'), ('READER_GATE_PASS','MISSING')):
            with self.assertRaises(ValueError): gate.check_log(fixture().replace(old,new))

    def test_diagnostics(self):
        for line in ('Fatal: bad', 'Error-[TEST] bad', 'Warning-[TEST] bad', 'Assertion failed'):
            with self.assertRaises(ValueError): gate.check_log(fixture()+line+'\n')

    def test_busy_cancel(self):
        for old,new in (('busy_cycles=8','busy_cycles=0'), ('repeat_pulses=1','repeat_pulses=0'),
                        ('READER_GATE_CANCEL phase=2','MISSING phase=2')):
            with self.assertRaises(ValueError): gate.check_log(fixture().replace(old,new))


if __name__ == '__main__':
    unittest.main()
