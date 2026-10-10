"""Additional readonly metric-collision regressions; frozen report files unchanged."""
import unittest
import report_population783_fpnew90 as m


class ActualMetricCollision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=(m.life.OUT/'current-population781-plus9700-prepared-agent-20261008-01/combined.el').read_text()
        cls.addition=(m.LOCAL/'first.el').read_text()
        cls.scope='ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_vfus.i_vmfpu'
        cls.target=cls.scope+'.fpu_gen.i_fpnew_bulk.gen_operation_groups[4].i_opgroup_block'

    def test_actual_collision_is_source_approved_FSM_not_whole_observer(self):
        old=m.stable.semantic(self.base)
        collision=[r for r in old[0] if r[0]==self.scope]
        self.assertTrue(collision)
        self.assertIn((self.scope,'3652315676 3873291691','','Fsm mfpu_state_q "3873291691"'),collision)
        self.assertTrue(all(r[3].startswith(('Fsm ','State ','Transition ')) for r in collision))
        merged=m.stable.semantic(m.union_gate(self.base,self.addition))
        self.assertEqual(old[0],merged[0])

    def test_all_actual60_colliding_FSM_records_strictly_bound(self):
        old=m.stable.semantic(self.base)[0]
        scopes={k[0] for k in m.prior.frozen.physical(m.stable.semantic(self.addition))}
        collisions={r for r in old if any(s==r[0] or s.startswith(r[0]+'.') for s in scopes)}
        self.assertEqual(len(collisions),60)
        headers={r for r in old if m.exact_fsm_header(r)}
        self.assertTrue(all(m.exact_fsm_record(r,headers) for r in collisions))

    def test_ancestor_whole_observer_rejected(self):
        whole='CHECKSUM: "3652315676 3873291691"\nINSTANCE: '+self.scope+'\nANNOTATION: "whole mutation"\n'
        with self.assertRaises(ValueError):m.union_gate(self.base+whole,self.addition)

    def test_ancestor_opaque_Toggle_rejected(self):
        unknown='CHECKSUM: "3652315676 3873291691"\nINSTANCE: '+self.scope+'\nToggle opaque "logic unsupported_decl"\n'
        opaque=m.stable.semantic(unknown)[0]
        self.assertTrue(opaque and all(r[3].startswith('Toggle ') for r in opaque))
        with self.assertRaises(ValueError):m.union_gate(self.base+unknown,self.addition)


if __name__=='__main__':unittest.main()
