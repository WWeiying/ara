"""Historical closure and real controlled mask config reads; no EDA."""
import unittest
from unittest.mock import patch

import eight_policy_epoch_735_report_v6 as r
import prepare_mask_store_snapshot_cond24 as mask


class Closure(unittest.TestCase):
    def test_exact_source_delta_and_coordinates(self):
        original = r.prior.prior.source_plan()
        value = r.source_plan()
        self.assertEqual(set(value['pins']) - set(original['pins']), {str(r.CONFIG), str(r.FIRST)})
        self.assertTrue(all(value['pins'][p] == h for p, h in original['pins'].items()))
        for key in ('targets', 'protected', 'audited', 'generated_paths', 'fixed_seal'):
            self.assertEqual(value[key], original[key])
        self.assertEqual(set(value['json_paths']) - set(original['json_paths']), {str(r.CONFIG)})

    def owner(self):
        pins, reads, jsons = r.closure({}, [], [])
        return r.DiagnosticWiring(pins, reads, jsons)

    def test_actual_controlled_read_config_and_first(self):
        owner = self.owner()
        private = r.base.clone(mask, Path=owner.Path, json=owner.json,
                              digest=lambda p: owner.phase.sha(p))
        config = private.read_config(owner.Path(r.CAPTURE), r.CONFIG_SHA)
        self.assertEqual(config['output'], str(r.CAPTURE))
        self.assertEqual(owner.phase.sha(r.FIRST), r.FIRST_SHA)
        self.assertTrue(owner.Path(r.FIRST).read_text())
        result = owner.phase.finish()
        self.assertEqual(result['consumed'][str(r.CONFIG)]['sha256'], r.CONFIG_SHA)
        self.assertEqual(result['consumed'][str(r.FIRST)]['sha256'], r.FIRST_SHA)

    def test_config_historical_hash_not_current_hash(self):
        with patch.object(r, 'CONFIG_SHA', '0' * 64):
            with self.assertRaises(Exception):
                r.closure({}, [], [])

    def test_el_historical_hash_not_current_hash(self):
        with patch.object(r, 'FIRST_SHA', '0' * 64):
            with self.assertRaises(Exception):
                r.closure({}, [], [])

    def test_direct_pin_conflict(self):
        with self.assertRaisesRegex(Exception, 'pin conflict'):
            r.closure({str(r.CONFIG): '0' * 64}, [], [])

    def test_transitive_pin_conflict(self):
        pins, _, _ = r.closure({}, [], [])
        name = next(p for p in pins if p not in (str(r.CONFIG), str(r.FIRST)))
        with self.assertRaisesRegex(Exception, 'pin conflict'):
            r.closure({name: '0' * 64}, [], [])

    def test_runtime_config_cannot_replace_prepared(self):
        with patch.object(r, 'CONFIG', r.CAPTURE / 'runtime-config.json'):
            with self.assertRaises(Exception):
                r.closure({}, [], [])

    def test_missing_declaration_still_rejected(self):
        owner = self.owner()
        with self.assertRaisesRegex(Exception, 'Unknown/conflicting pin'):
            owner.Path(r.CAPTURE / 'runtime-config.json').read_bytes()

    def test_no_json_capability_bypass(self):
        pins, reads, _ = r.closure({}, [], [])
        phase = r.base.CapturePhase(pins, reads, [], r.base.LINKS)
        with self.assertRaisesRegex(Exception, 'captured bytes'):
            phase.loads(phase.bytes(r.CONFIG))

    def test_audit_uses_supplemented_source_and_original_check(self):
        self.assertIs(r.local.audit.__globals__['source_plan'], r.source_plan)
        self.assertIs(r.local.audit.__globals__['DiagnosticWiring'], r.DiagnosticWiring)
        self.assertIs(r.report.check.__code__, r.prior.report.check.__code__)
        self.assertIn(r.CONFIG, r.dependencies())
        self.assertIn(r.FIRST, r.dependencies())


if __name__ == '__main__':
    unittest.main()
