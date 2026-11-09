import unittest
import attribution as a


def instructions(arm):
    result = []
    for row in range(3):
        reg = 10 if arm and row % 2 else 8
        start = 100 + row*30
        for index, (insn, delta, duration) in enumerate((
            (0x0205305B | reg << 7, 0, 26),
            (0xB2005057 | reg << 20, 5, 30),
            (0xB200D157 | reg << 20, 16, 28))):
            result.append(dict(seq=3*row+index, insn=insn, vl=128, vstart=0,
                               alloc=start+delta, done=start+delta+duration))
    return result


class AttributionTests(unittest.TestCase):
    def test_rotation_overlap_is_not_same_register_overwrite(self):
        stats = a.pv_tile(instructions(1), dict(begin=99, end=210), 3, 1)
        self.assertEqual(stats["row_allocation_period_histogram"], {30: 2})
        self.assertEqual(stats["next_row_minus_previous_last_fma_done_histogram"], {-14: 2})
        self.assertEqual(stats["same_register_reuse_minus_previous_reader_done_histogram"], {16: 1})

    def test_unchanged_register_rejected_in_candidate(self):
        with self.assertRaisesRegex(ValueError, "pairing"):
            a.pv_tile(instructions(0), dict(begin=99, end=210), 3, 1)

    def test_wrong_fma_source_rejected(self):
        work = instructions(1)
        work[4]["insn"] = 0xB2805057
        with self.assertRaisesRegex(ValueError, "pairing"):
            a.pv_tile(work, dict(begin=99, end=210), 3, 1)

    def test_wrong_vl_rejected(self):
        work = instructions(1)
        work[2]["vl"] = 127
        with self.assertRaisesRegex(ValueError, "shape"):
            a.pv_tile(work, dict(begin=99, end=210), 3, 1)

    def test_baseline_jump_is_inside_pv_span(self):
        def span(name, first, last):
            return dict(helper=name, begin=first, end=last, retired=1, opcodes={"13": 1})
        spans = a.merge_pv_spans([span(a.WRAPPER, 10, 14), span(a.PV, 14, 40),
                                 span(a.WRAPPER, 50, 90)])
        self.assertEqual([(s["begin"], s["end"]) for s in spans], [(10, 40), (50, 90)])
        self.assertEqual(spans[0]["retired"], 2)


if __name__ == "__main__":
    unittest.main()
