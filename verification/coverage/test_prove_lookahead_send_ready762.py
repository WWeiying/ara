import unittest
import copy
import prove_lookahead_send_ready762 as p


class ProofTests(unittest.TestCase):
    def test_complete_reset_reachable_eight_beats(self):
        result = p.explore()
        self.assertGreater(result['reachable_states'], 50)
        self.assertEqual(result['send_ready_edges'], 0)

    def test_one_beat_counterexample(self):
        self.assertGreater(p.explore(1)['send_ready_edges'], 0)

    def test_illegal_initial_pointer_counterexample(self):
        q = ((p.S, p.E), 7, (0, 0))
        self.assertFalse(p.invariant(q))
        self.assertEqual(p.step(q, (0,1,1,1,1,0,0,0), 0, -1)[0][0], p.R)

    def test_same_cycle_ar_early_last(self):
        nxt = p.step(((p.S,p.E),0,(0,0)), (1,1,1,1,1,0,0,0),0,-1)
        self.assertEqual(nxt[0], (p.E,p.P)); self.assertEqual(nxt[1], 0)

    def test_terminal_old_fill_pending_next_cycle(self):
        nxt = p.step(((p.F,p.P),7,(0,0)), (0,0,1,1,1,0,0,0),0,-1)
        self.assertEqual(nxt[0], (p.R,p.P)); self.assertEqual(nxt[1], 0)
        promoted = p.step(nxt, (0,0,0,0,1,0,0,0),0,-1)
        self.assertEqual(promoted[0], (p.R,p.S)); self.assertTrue(p.invariant(promoted))

    def test_pending_cancel_overrides_promotion(self):
        nxt = p.step(((p.P,p.E),0,(0,0)), (1,0,0,0,1,0,0,0),1,-1)
        self.assertEqual(nxt[0], (p.E,p.P))

    def test_overlong_response_killed_then_empty(self):
        q = p.step(((p.F,p.P),7,(0,0)), (0,0,1,0,1,0,0,0),0,-1)
        self.assertEqual(q[1], 7); self.assertEqual(q[2][0], 1)
        self.assertEqual(p.step(q,(0,0,1,1,1,0,0,0),0,-1)[0][0],p.E)

    def test_two_private_owners_rejected(self):
        self.assertFalse(p.invariant(((p.S,p.F),0,(0,0))))

    def test_actual_shape_exact_targets_and_hit_rejection(self):
        book = p.life.read_bound(p.prior.BASE/'admission-manifest.json', p.BASE_SHA)
        path = p.prior.BASE/'combined-bits.json'
        bits = p.life.read_bound(path, book['output_pins'][str(path)])
        shape_path = p.life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml'
        shape = p.native.read_xml(shape_path)
        gs = p.groups(shape,bits)
        self.assertEqual([r['raw_index'] for g in gs for r in g['rows'] if r['target']], [23,47])
        self.assertEqual(sum(len(g['rows']) for g in gs),48)
        bad = copy.deepcopy(bits)
        bad['metrics']['fsm'][p.SCOPE]['bits'] = format(int(bits['metrics']['fsm'][p.SCOPE]['bits'],16)|(1<<24),'x')
        with self.assertRaises(Exception): p.groups(shape,bad)
        wrong = copy.deepcopy(shape)
        for d in wrong.iter('fsmdef'):
            if d.get('chksum') == '3008642282': d.set('file','999')
        with self.assertRaises(Exception): p.groups(wrong,bits)


if __name__ == '__main__': unittest.main()
