import copy
import csv
import unittest
import review_fp16_c910742 as r


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = r.patterns(r.SOURCE.read_text())
        cls.segments = r.load_segments(r.CASE / 'input.elf')
        with (r.CASE / 'commit_trace.csv').open() as stream: cls.rows = list(csv.DictReader(stream))

    def test_full_actual64(self):
        result = r.trace_evidence(self.rows, self.segments, self.cases)
        self.assertEqual(result['observed_halfwords'], 64)
        self.assertEqual(result['independently_compared_bytes'], 128)

    def test_golden_mutation(self):
        cases = copy.deepcopy(self.cases); cases[0]['expected'][4] ^= 1
        with self.assertRaises(ValueError): r.trace_evidence(self.rows, self.segments, cases)

    def test_observation_mutation(self):
        rows = copy.deepcopy(self.rows)
        targets = [x for x in rows if x['event'] == 'retire' and x['pc'] == '0000000080000296']
        self.assertEqual(len(targets), 1); targets[0]['rd_wdata'] = '0000000000003fde'
        with self.assertRaises(ValueError): r.trace_evidence(rows, self.segments, self.cases)

    def test_missing_readback(self):
        rows = [x for x in self.rows if not (x['event'] == 'retire' and x['pc'] == '0000000080000296')]
        with self.assertRaises(ValueError): r.trace_evidence(rows, self.segments, self.cases)

    def test_wrong_actual_ELF_instruction(self):
        rows = copy.deepcopy(self.rows)
        target = next(x for x in rows if x['event'] == 'retire' and x['pc'] == '000000008000023e')
        target['insn'] = '802190d7'
        with self.assertRaises(ValueError): r.trace_evidence(rows, self.segments, self.cases)

    def test_wrong_RTZ_input_register(self):
        rows = copy.deepcopy(self.rows)
        target = next(x for x in rows if x['event'] == 'retire' and x['pc'] == '0000000080001ff8')
        target['rd_wdata'] = '0000000000000000'
        with self.assertRaises(ValueError): r.trace_evidence(rows, self.segments, self.cases)

    def test_exception(self):
        rows = copy.deepcopy(self.rows)
        next(x for x in rows if x['event'] == 'retire')['trap'] = '1'
        with self.assertRaises(ValueError): r.trace_evidence(rows, self.segments, self.cases)

    def test_all16_lane_subslots(self):
        mapping = r.shuffle_map((r.ROOT / 'hardware/include/ara_pkg.sv').read_text())
        added = [(x['lane'], x['subslot']) for x in mapping if x['subslot'] in (2, 3)]
        self.assertEqual(set(added), {(l, s) for l in range(4) for s in (2, 3)})

    def test_nonfinite_and_zero_not_accepted(self):
        for a, b in [(0x7c00, 0x3c00), (0x3c00, 0)]:
            with self.assertRaises(ValueError): r.div_rtz(a, b)


if __name__ == '__main__': unittest.main()
