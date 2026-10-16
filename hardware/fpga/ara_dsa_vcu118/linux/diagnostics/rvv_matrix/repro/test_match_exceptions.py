import unittest
from match_exceptions import fault_records, candidates, scenario_counts


class MatchTests(unittest.TestCase):
    def block(self, address, tval):
        return (f'unhandled signal 11 code 0x2\nepc : 10300\na0 : {address:x}\n'
                f'badaddr: {tval:x} cause: d\n')

    def test_independent_children(self):
        output=self.block(4092,4096)+self.block(8192,8192)
        self.assertEqual([r['offset'] for r in fault_records(output)],[4,0])
        self.assertEqual(len(candidates(dict(output=output),0,8)),1)
        self.assertEqual(len(candidates(dict(output=output),3,8)),1)

    def test_incomplete_child_cannot_borrow_registers(self):
        output='unhandled signal 11 code 0x2\nepc : 99999\n'+self.block(4092,4096)
        self.assertEqual([r['epc'] for r in fault_records(output)],[0x10300])
        self.assertEqual(fault_records(self.block(4092,4096)+'epc : 10400\n'),[])

    def test_scenario_status_and_unique_counters(self):
        line='RVV_EXCEPTION_SCENARIO id=3 unexpected_signals=1 nonzero_exits=0 wait_failures=0\n'
        r=dict(status='failed',exit_code=1,output=line)
        self.assertEqual(scenario_counts(r,3),(1,0,0))
        for bad in (dict(r,output=line*2),dict(r,exit_code=0)):
            with self.assertRaises(ValueError):
                scenario_counts(bad,3)


if __name__ == '__main__':
    unittest.main()
