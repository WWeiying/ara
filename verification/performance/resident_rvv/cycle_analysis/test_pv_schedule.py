import unittest
from pv_schedule import lifetimes, pv_tiles, ROW_LOAD, PAIR_FMAS


def event(cycle, kind, vid, seq, insn=ROW_LOAD):
    return dict(cycle=str(cycle), event=kind, vid=str(vid), arch_seq=str(seq),
                insn=f"{insn:08x}", vl="128", vstart="0")


class ScheduleTests(unittest.TestCase):
    def test_lifetimes(self):
        rows = [event(2, "alloc", 0, 1), event(5, "alloc", 1, 2, PAIR_FMAS[0]),
                event(7, "done", 0, 1), event(9, "done", 1, 2, PAIR_FMAS[0])]
        result = lifetimes(rows)
        self.assertEqual(result[0]["done"], 7)
        self.assertEqual(result[1]["alloc"], 5)

    def test_missing_completion_rejected(self):
        with self.assertRaises(ValueError):
            lifetimes([event(1, "alloc", 0, 1)])

    def test_wrong_completion_rejected(self):
        with self.assertRaises(ValueError):
            lifetimes([event(1, "alloc", 0, 1), event(2, "done", 0, 2)])

    def test_overlap_and_period_are_distinct(self):
        insns = []
        for base in (10, 55):
            insns.extend(dict(insn=op, alloc=base+offset, done=base+duration, vstart=0)
                         for op, offset, duration in
                         ((ROW_LOAD, 0, 26), (PAIR_FMAS[0], 4, 36), (PAIR_FMAS[1], 5, 44)))
        result = pv_tiles(insns, [dict(begin=5, end=110)], [2])[0]
        self.assertEqual(result["row_allocation_period_histogram"], {45: 1})
        self.assertEqual(result["next_row_minus_previous_last_fma_done_histogram"], {1: 1})
        self.assertEqual(result["first_fma_alloc_before_replay_done_count"], 2)

    def test_missing_second_head_rejected(self):
        insns = [dict(insn=ROW_LOAD, alloc=1, done=5, vstart=0),
                 dict(insn=PAIR_FMAS[0], alloc=3, done=8, vstart=0)]
        with self.assertRaises(ValueError):
            pv_tiles(insns, [dict(begin=0, end=10)], [1])


if __name__ == "__main__":
    unittest.main()
