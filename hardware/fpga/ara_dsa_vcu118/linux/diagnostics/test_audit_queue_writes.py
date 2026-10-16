import tempfile
from pathlib import Path
import unittest

from audit_queue_writes import scan


class ScanTest(unittest.TestCase):
    def findings(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'test.sv'
            p.write_text('module m; ' + text + ' endmodule')
            return scan(p, [], [])['findings']

    def test_dynamic_whole_and_partial(self):
        f = self.findings('always_comb begin q[w].x=1; q[r]=0; end')
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]['root'], 'q')

    def test_multidimensional_and_nonblocking(self):
        self.assertEqual(len(self.findings(
            'always_ff @(posedge c) begin q[w][l].data[b+:8]<=v; q[r][l]<=0; end')), 1)

    def test_comparison_not_assignment(self):
        self.assertEqual(self.findings(
            'always_comb begin q[i]=0; if(q[j].x<=1) v=1; end'), [])

    def test_separate_processes_not_combined(self):
        self.assertEqual(self.findings('always_comb q[i]=0; always_comb q[j].x=1;'), [])

    def test_whole_root_default_is_not_entry_clear(self):
        self.assertEqual(self.findings('always_comb begin q=n; q[i].x=1; end'), [])

    def test_same_index_override_still_reported_for_review(self):
        self.assertEqual(len(self.findings('always_comb begin q[w]=n; q[w].x=1; end')), 1)


if __name__ == '__main__':
    unittest.main()
