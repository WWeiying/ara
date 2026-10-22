"""No EDA. Real private function bodies plus explicitly scoped fixture gates."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import eight_policy_epoch_732_wiring as wiring
from verification_epoch import EpochError


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / 'config.json'
        self.config.write_bytes(b'{"population":732,"groups":{"a":[1,true]},"pins":{}}')
        self.binary = self.root / 'binary'
        self.binary.write_bytes(b'hash-only-binary')
        self.pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.config, self.binary)}

    def phase(self):
        return wiring.CapturePhase(self.pins, [str(self.config)], [str(self.config)], {})

    def test_json_legacy_types_immutable_and_one_parse(self):
        phase = self.phase()
        first = phase.load_sealed(self.config, self.pins[str(self.config)])
        self.assertIs(first, phase.load_sealed(self.config, self.pins[str(self.config)]))
        self.assertIsInstance(first, dict)
        self.assertIsInstance(first['groups']['a'], list)
        self.assertEqual(json.loads(json.dumps(first)), first)
        with self.assertRaises(EpochError):
            first['groups']['a'].append(99)
        with self.assertRaises(EpochError):
            first.update(groups={})
        facade = wiring.facade_copy(first)
        facade['population'] = 999
        self.assertIs(facade['groups'], first['groups'])
        self.assertEqual(first['population'], 732)
        phase.sha(self.binary)
        self.assertEqual(phase.finish()['parses'], 1)

    def test_hash_only_not_retained_and_byte_promotion_rejected(self):
        phase = self.phase()
        phase.sha(self.binary)
        self.assertNotIn(str(self.binary), phase.raw)
        with self.assertRaises(EpochError):
            phase.bytes(self.binary)

    def test_unknown_json_data_and_seal_rejected(self):
        with self.assertRaises(EpochError):
            self.phase().loads(b'{}')
        with self.assertRaises(EpochError):
            self.phase().load_sealed(self.config, '0' * 64)

    def test_immutable_pin_missing_or_conflicting_rejected(self):
        with self.assertRaises(EpochError):
            self.phase().pin(wiring.FrozenDict({}), self.config)
        with self.assertRaises(EpochError):
            self.phase().pin({str(self.config): '0' * 64}, self.config)

    def test_role_failure_poisons_phase_and_text_is_shared(self):
        phase = self.phase()
        self.assertIs(phase.text(self.config), phase.text(self.config))
        with self.assertRaises(EpochError):
            phase.loads(b'{}')
        with self.assertRaises(EpochError):
            phase.sha(self.binary)

    def test_budget_and_missing_obligation_rejected(self):
        phase = wiring.CapturePhase(self.pins, [str(self.config)], [], {}, max_bytes=1)
        with self.assertRaises(EpochError):
            phase.bytes(self.config)
        with self.assertRaises(EpochError):
            self.phase().finish()

    def test_fresh_phase_detects_changed_file(self):
        phase = self.phase()
        phase.sha(self.config)
        self.config.write_bytes(b'changed')
        with self.assertRaises(EpochError):
            self.phase().sha(self.config)

    def test_real_sealed_loader_private_globals_not_mutated(self):
        phase = self.phase()
        original = wiring.population.frozen.load_sealed
        loader = wiring.population.private(original, sha=phase.sha,
            Path=type('CapturedPath', (type(self.config),), {'read_bytes': lambda p: phase.bytes(str(p))}),
            json=type('CapturedJSON', (), {'loads': staticmethod(phase.loads)}))
        self.assertIs(loader(self.config, self.pins[str(self.config)]),
                      loader(self.config, self.pins[str(self.config)]))
        self.assertIs(wiring.population.frozen.load_sealed, original)
        self.assertEqual(phase.parses, 1)


class FamilyTests(PhaseTests):
    def factory(self, owner):
        # This is an integration fixture, not the production identity adapter.
        parent = wiring.private_base_context(owner)

        class Fixture(parent):
            def check_config(self, config, output):
                self.calls.append(config)
                if self.reject:
                    raise EpochError('Fixture native gate rejects')

        context = Fixture(wiring.root732.ADMISSION, wiring.root732.SEAL, 732)
        context.calls, context.reject = [], False
        return context

    def family(self):
        data = json.dumps(dict(population=732, admission_manifest_sha256=wiring.root732.SEAL,
                               groups={'a': [1, True]}, pins={})).encode()
        self.config.write_bytes(data)
        self.pins[str(self.config)] = hashlib.sha256(data).hexdigest()
        class FixtureWiring(wiring.Wiring):
            def _check_context(self):
                # Scoped fixture only. Production Wiring rejects overridden
                # native/source check_config bodies below.
                pass
        return FixtureWiring(self.pins, [str(self.config)], [str(self.config)], self.factory)

    def test_actual_six_reader_reuses_json_and_calls_validator_each_time(self):
        family = self.family()
        _, first = family.read_six(self.root, self.pins[str(self.config)])
        _, second = family.read_six(self.root, self.pins[str(self.config)])
        self.assertIs(first, second)
        self.assertEqual(len(family.context.calls), 2)
        self.assertEqual(family.phase.parses, 1)
        family.context.reject = True
        with self.assertRaises(EpochError):
            family.read_six(self.root, self.pins[str(self.config)])

    def test_real_frozen_csv_eight_and_entry_function_bodies_bound(self):
        family = self.family()
        for private, original in ((family.eight.read_config, wiring.eight.read_config),
                                  (family.fixed.read_config, wiring.fixed.read_config),
                                  (family.runner.reviewed_entry, wiring.runner.reviewed_entry),
                                  (family.runner.run_reviewed, wiring.runner.run_reviewed)):
            self.assertIs(private.__code__, original.__code__)
        self.assertIs(family.runner.reviewed_entry.__globals__['generic'], family.fixed)
        self.assertIs(family.fixed.read_config.__globals__['eight'], family.eight)
        self.assertIs(family.eight.read_config.__globals__['six'], family.six)
        self.assertIs(family.runner.run_reviewed.__globals__['invoke_run'].__self__, family)

    def test_source_base_validator_body_preserved_not_stubbed(self):
        family = self.family()
        base = wiring.private_base_context(family)
        self.assertIs(base.check_config.__code__, wiring.population.Context.check_config.__code__)
        real = base(wiring.root732.ADMISSION, wiring.root732.SEAL, 732)
        with self.assertRaises((ValueError, KeyError)):
            real.check_config({'schema': 'ARBITRARY_PASS'}, self.root)

    def test_phase_order_fresh_reads_and_postrun_mutation(self):
        family = self.family()
        family.phase.sha(self.binary)
        previous = family.phase
        family.enter('live')
        self.assertIsNot(previous, family.phase)
        family.phase.sha(self.binary)
        family.enter('post')
        self.binary.write_bytes(b'changed-after-live')
        with self.assertRaises(EpochError):
            family.phase.sha(self.binary)
        with self.assertRaises(EpochError):
            family.enter('post')

    def test_boundary_keeps_tree_and_tool_checks(self):
        family = self.family()
        config = dict(pins=self.pins, plan=dict(input_membership={'root': ['a']}, tool_identity={'id': 1}))
        with patch.object(wiring.lifecycle.proof, 'tree_members', return_value=['a']) as tree, \
             patch.object(family.tool, 'revalidate') as tool:
            family.check_inputs(config, boundary='live')
            family.check_inputs(config, boundary='post')
        self.assertEqual(tree.call_count, 2)
        self.assertEqual(tool.call_count, 2)

    def test_boundary_member_change_rejected(self):
        family = self.family()
        config = dict(pins=self.pins, plan=dict(input_membership={'root': ['a']}, tool_identity={}))
        with patch.object(wiring.lifecycle.proof, 'tree_members', return_value=['a', 'extra']):
            with self.assertRaises(EpochError):
                family.check_inputs(config, boundary='live')

    def test_population729_not_relabelled(self):
        family = self.family()
        value = dict(population=729, admission_manifest_sha256=wiring.root732.SEAL)
        data = json.dumps(value).encode()
        self.config.write_bytes(data)
        pins = dict(self.pins, **{str(self.config): hashlib.sha256(data).hexdigest()})
        family = type(family)(pins, [str(self.config)], [str(self.config)], self.factory)
        with self.assertRaises(EpochError):
            family.read_six(self.root, pins[str(self.config)])

    def test_production_rejects_empty_or_overridden_source_validator(self):
        with self.assertRaises(EpochError):
            wiring.Wiring(self.pins, [str(self.config)], [str(self.config)], self.factory)

    def test_actual_default_identity_context_exact732_original_checker(self):
        family = wiring.Wiring(self.pins, [str(self.config)], [str(self.config)])
        self.assertEqual(family.context.population, 732)
        self.assertIs(family.context.check_config.__func__.__code__,
                      wiring.population.Context.check_config.__code__)
        with self.assertRaises((ValueError, KeyError)):
            family.context.check_config({'schema': 'ARBITRARY_PASS'}, self.root)

    def test_cc_extension_preserves_instructions_and_exact_ten_node_bounds(self):
        function = wiring.extended_cc_proof({})
        self.assertEqual(function.__code__.co_code, wiring.identity.cc_ancestry.__code__.co_code)
        self.assertIn(732, function.__code__.co_consts)
        self.assertIn(10, function.__code__.co_consts)
        self.assertNotIn(729, [c for c in function.__code__.co_consts if type(c) is int])

    def test_actual_tool_revalidation_preserves_body_private_seal_binding(self):
        family = self.family()
        self.assertIs(family.tool.revalidate.__code__, wiring.lifecycle.tool.revalidate.__code__)
        self.assertIs(family.tool.prepare.__code__, wiring.lifecycle.tool.prepare.__code__)
        self.assertIsNot(family.tool.seal_file, wiring.lifecycle.tool.seal_file)
        self.assertIs(wiring.lifecycle.tool.prepare.__globals__['seal_file'], wiring.lifecycle.tool.seal_file)

    def test_incomplete_generated_authority_cannot_launch(self):
        family = self.family()
        with patch.object(wiring.population, 'private') as execute:
            with self.assertRaisesRegex(EpochError, 'no launch'):
                family.invoke_run(self.root, {}, family.context, {})
        execute.assert_not_called()

    def test_real_reviewed_entry_reads_sealed_plan_and_calls_six_reader(self):
        family = self.family()
        config = dict(population=732, admission_manifest_sha256=wiring.root732.SEAL,
                      command=['fixture-not-a-launch'],
                      pins={str(self.binary): self.pins[str(self.binary)]})
        data = json.dumps(config).encode()
        self.config.write_bytes(data)
        self.pins[str(self.config)] = hashlib.sha256(data).hexdigest()
        plan_path = self.root / family.runner.PLAN
        plan = dict(schema='EIGHT_CSV_FIX_SINGLE_LAUNCH_V1', output=str(self.root),
                    targets=5892, protected=17774, audited=23666,
                    timeout_seconds=family.frozen.TIMEOUT, parent_review_required=True,
                    config_reprepared=False, automatic_retry=False, launch_approved=False,
                    application_approval=False, population=732,
                    admission_manifest_sha256=wiring.root732.SEAL,
                    config_sha256=self.pins[str(self.config)], command=config['command'],
                    pins=dict(self.pins))
        plan_path.write_bytes(json.dumps(plan).encode())
        plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        pins = dict(self.pins, **{str(plan_path): plan_sha})
        # Only entry orchestration is under test here. Native policy validation
        # uses the explicit fixture Context, not an aggregate approval.
        family = type(family)(pins, [str(self.config), str(plan_path)],
                              [str(self.config), str(plan_path)], self.factory)
        with patch.object(family.fixed, 'read_config', side_effect=family.read_six), \
             patch.dict(family.runner.reviewed_entry.__globals__,
                        output_path=lambda output: output, entry_dependencies=lambda output: ()):
            actual, context, captured = family.runner.reviewed_entry(self.root, plan_sha)
        self.assertEqual(actual['population'], 732)
        self.assertIs(context, family.context)
        self.assertEqual(len(context.calls), 1)
        self.assertEqual(captured['command'], ['fixture-not-a-launch'])
        self.assertEqual(family.phase.parses, 2)


if __name__ == '__main__':
    unittest.main()
