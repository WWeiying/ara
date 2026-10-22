import copy
import json
import unittest
import collect_btb_target_ring_v2 as c


class Scalar(unittest.TestCase):
    def actual(self):
        path=c.life.OUT/'btb-target-ring-qualified777-agent-20261007-01/scalar-comparison.json'
        result=json.loads(path.read_bytes())
        q=json.loads((c.life.OUT/'btb-target-ring-preflight777-agent-20261007-03/preflight.json').read_bytes())
        return result,dict(q['counts'],ara_trap_events=1)

    def test_actual_complete_comparison(self):
        c.scalar_exact(*self.actual())

    def test_count_skip_mismatch_type_extra_trap_terminal(self):
        a,e=self.actual()
        for k,v in (('ara_retired_instructions',37753),('ara_committed_instructions',37754),
            ('ara_trap_events',2),('skipped_unobservable_register_values',1),('mismatch',{}),
            ('ara_trap_events',True),('matched_scalar_memory_accesses',5959)):
            bad=copy.deepcopy(a);bad[k]=v
            with self.assertRaises(ValueError):c.scalar_exact(bad,e)
        a['terminal_tohost']['write_value']='0x3'
        with self.assertRaises(ValueError):c.scalar_exact(a,e)

    def test_original_still_strict_and_unchanged(self):
        a,e=self.actual()
        with self.assertRaisesRegex(ValueError,'ara_retired_instructions'):c.original.pre.arch.scalar_exact(a,e)
        self.assertEqual(c.original.pre.arch.scalar_exact.__module__,'collect_gap103_strict')


if __name__=='__main__':unittest.main()
