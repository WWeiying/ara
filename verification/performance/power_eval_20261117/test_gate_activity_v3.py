#!/usr/bin/env python3
import io
from pathlib import Path
import unittest
from unittest.mock import Mock
import gate_activity_v3 as g


class Activity(unittest.TestCase):
    def test_exact_roi_limits(self):
        self.assertEqual(len(g.CASES), 3)
        for case, first, last, maximum, scope in g.CASES.values():
            self.assertTrue(1024 <= last-first <= 4096 and last < maximum)

    def test_eof_audit_rejects_partial_and_missing_initial(self):
        header = ('$timescale 100 fs $end\n$scope module ara_tb $end\n$scope module dut $end\n'
            '$scope module i_ara_soc $end\n$var wire 1 ! clk_i $end\n$var wire 1 ? data $end\n'
            '$upscope $end\n$upscope $end\n$upscope $end\n$enddefinitions $end\n')
        body = '#10000\n$dumpvars\n0!\n0?\n$end\n#15000\n1!\n#20000\n0!\n#25000\n1!\n#30000\n0!\n'
        def check(text):
            return g.a.inspect_vcd(Mock(open=lambda: io.StringIO(text)), 10000, 30000, 2)
        self.assertEqual(check(header+body)['clock_edges'], 4)
        for bad in (body[:-1], body.replace('0?\n', ''), body.replace('#30000\n0!\n', ''),
                    body.replace('#20000', '#21000'), body.replace('1!', 'x!', 1)):
            with self.assertRaises(ValueError):
                check(header+bad)

    def test_unknown_dispatcher_fail_closed(self):
        self.assertEqual(g.n.reserved_slots({99: (1, ['python3', '/tmp/precheck_unknown.py', 'execute'])}), 4)

    def test_global_capacity_counts_external_and_excludes_own(self):
        rows = {i: (1, ['/tmp/simv']) for i in range(10, 14)}
        self.assertEqual(g.n.reserved_slots(rows), 4)
        self.assertEqual(g.n.reserved_slots(rows, own_child=13), 3)


if __name__ == '__main__':
    unittest.main()
