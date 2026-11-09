import unittest

from replay_native_boundary import engine_boundaries,native_spans,partition


def row(cycle,event,pc,insn='13'):
    return dict(cycle=str(cycle),event=event,pc=hex(pc),insn=insn,trap='0')


class NativeBoundaryTest(unittest.TestCase):
    def test_full_boundary_log_not_a_truncated_window(self):
        fire='[CHAIN_BOUNDARY] cycle=10 insn=00b5045b qbs_fire=1 qbs_terminal=0 akv_fire=0 akv_terminal=0'
        done='[CHAIN_BOUNDARY] cycle=30 insn=00b5045b qbs_fire=0 qbs_terminal=1 akv_fire=0 akv_terminal=0'
        self.assertEqual(engine_boundaries(fire+'\n'+done),[dict(fire=10,terminal=30,cycles=20)])
        for bad in (fire,done,fire+'\n'+fire+'\n'+done):
            with self.assertRaises(ValueError):
                engine_boundaries(bad)

    def test_nonretirement_pc_zero_does_not_end_call(self):
        rows=[row(1,'retire',100),row(2,'load',0),row(3,'retire',102,'8082'),
              row(3,'write',0),row(4,'retire',200)]
        self.assertEqual(native_spans(rows,100,110,10),[dict(entry=1,exit=4,cycles=3,retired=2)])

    def test_partial_or_nonreturn_span_is_rejected(self):
        for rows in ([row(1,'retire',102)],
                     [row(1,'retire',100),row(2,'retire',200)],
                     [row(1,'retire',100)]):
            with self.assertRaises(ValueError):
                native_spans(rows,100,110,10)

    def test_partition_keeps_one_time_prefix(self):
        spans=[dict(entry=20,exit=50,cycles=30),dict(entry=55,exit=85,cycles=30)]
        bounds=[dict(fire=22,terminal=48,cycles=26),dict(fire=57,terminal=83,cycles=26)]
        r=partition(10,90,spans,bounds)
        self.assertEqual(r['sdk_prefix'],10)
        self.assertEqual(r['between_callbacks'],5)
        self.assertEqual(r['sdk_outside_native'],20)
        self.assertEqual(r['native_outside_engine'],8)
        self.assertEqual(r['execute_outside_engine'],28)
        bounds[1]['terminal']=86
        with self.assertRaises(ValueError):
            partition(10,90,spans,bounds)


if __name__=='__main__':
    unittest.main()
