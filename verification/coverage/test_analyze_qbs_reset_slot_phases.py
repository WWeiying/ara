import unittest
import analyze_qbs_reset_slot_phases as analysis


class SlotPhaseTests(unittest.TestCase):
    def stream(self, unknown=False, active=True):
        ids = {k: str(i) for i,k in enumerate(analysis.WIDTHS)}
        declarations = {'ara_tb.' + k: dict(code=v) for k,v in ids.items()}
        initial = {ids['clk']: '0', ids['rst_n']: '1',
                   ids[analysis.REL + '.entry_valid_q']: '0000000000000011'}
        for i in range(16):
            initial[ids[analysis.REL + '.entry_state_q[%d]' % i]] = '001' if i < 2 else 'xxx'
        reset = dict(initial, **{ids['rst_n']: '0'})
        restored = dict(initial, **{ids[analysis.REL + '.entry_valid_q']: '0'*14 + ('11' if active else '00')})
        if unknown:
            restored[ids[analysis.REL + '.entry_state_q[1]']] = 'xxx'
        yield 'declarations', declarations
        yield 20, initial, reset
        yield 60, reset, restored
        yield 65, restored, dict(restored, **{ids['clk']: '1'})

    def test_all_slots_observed_not_only_target_zero(self):
        result = analysis.summarize(iter(self.stream()))
        self.assertEqual(result['maximal_recovery_stage_groups']['1']['active_slots'], [0, 1])

    def test_unknown_active_state_rejected(self):
        with self.assertRaises(ValueError):
            analysis.summarize(iter(self.stream(unknown=True)))

    def test_inactive_uninitialized_state_is_not_coverage(self):
        result = analysis.summarize(iter(self.stream(unknown=True, active=False)))
        self.assertEqual(result['maximal_recovery_stage_groups']['1']['active_slots'], [])


if __name__ == '__main__':
    unittest.main()
