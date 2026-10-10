import unittest
import json
import report_fsm_observers742 as r


class NativeUnionTest(unittest.TestCase):
    def test_actual_approved66_plus_four_leafs(self):
        text = (r.FSM / 'first.el').read_text() + (r.OBS / 'observers.el').read_text()
        fsm, obs = r.combined_records(text)
        self.assertEqual(len(fsm), 66)
        self.assertTrue(all(x[-3] == 'Transition' for x in fsm))
        self.assertEqual(obs, {s: v[1] for s, v in r.observer.TARGETS.items()})

    def test_duplicate_fsm_rejected(self):
        text = (r.FSM / 'first.el').read_text()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            r.combined_records(text + text)

    def test_duplicate_observer_rejected(self):
        text = (r.OBS / 'observers.el').read_text()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            r.combined_records(text + text)

    def test_observer_attribute_mutation_rejected(self):
        text = (r.OBS / 'observers.el').read_text().replace(r.ANNOTATION, 'different annotation', 1)
        with self.assertRaisesRegex(ValueError, 'attributes'):
            r.combined_records(text)

    def test_foreign_directive_rejected(self):
        text = (r.OBS / 'observers.el').read_text() + 'Line 1\n'
        with self.assertRaisesRegex(ValueError, 'Non-observer'):
            r.combined_records(text)

    def test_reset_and_exact_import_no_new_ui_exclusions(self):
        text = (r.HERE / 'report_fsm_observers742.tcl').read_text()
        self.assertNotIn('gui_exclude_items', text)
        self.assertIn('combined.el', text)
        self.assertIn('p740_save cleanup-empty.el', text)
        self.assertIn('fx_audit final 0', text)

    def test_actual_six_stage_transitions_only(self):
        bits = json.loads((r.BASE / 'combined-bits.json').read_text())
        groups = r.capture.groups_from_shape(r.native.read_xml(r.capture.BUILD / 'sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml'), bits)
        proof = json.loads(r.PTW_PROOF.read_text())
        r.add_ptw(groups, proof, bits)
        self.assertEqual(sum(x['target'] for g in groups for x in g['rows']), 72)
        self.assertFalse(any(x['target'] for g in groups if g['mode'] == 'State' for x in g['rows']))


if __name__ == '__main__':
    unittest.main()
