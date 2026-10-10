"""Actual snapshot reads and all private constant namespaces; no DVE."""
import hashlib
from pathlib import Path
from types import FunctionType
import unittest

import eight_policy_epoch_735_report_v5 as r


class Bridge(unittest.TestCase):
    def fixture(self, diagnostic=False, json_role=True):
        original = r.prior.base.population.snapshot
        frozen = r.prior.base.population.frozen
        paths = (original.BUILD, original.SNAPSHOT, frozen.SCRIPT, frozen.TCL,
                 Path(original.__file__).resolve())
        pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        self.assertEqual(pins[str(original.BUILD)], original.BUILD_SHA)
        self.assertEqual(pins[str(original.SNAPSHOT)], original.SNAPSHOT_SHA)
        cls = r.DiagnosticWiring if diagnostic else r.Wiring
        owner = cls(pins, list(pins), [str(original.BUILD)] if json_role else [])
        function = next(vars(c)['source_binding'] for c in type(owner.context).__mro__
            if 'source_binding' in vars(c) and vars(c)['source_binding'].__code__ is
               r.prior.base.population.Context.source_binding.__code__)
        return owner, function, original, pins

    def test_real_unmodified_source_binding_reads_build_snapshot(self):
        owner, function, original, pins = self.fixture()
        result = function(owner.context, pins)
        self.assertEqual(result['sha256'], original.SNAPSHOT_SHA)
        self.assertEqual(result['build_manifest_sha256'], original.BUILD_SHA)
        self.assertFalse(result['current_dispatcher_read'])
        self.assertIsInstance(function.__globals__['snapshot'].BUILD, owner.Path)
        self.assertIn(str(original.BUILD), owner.phase.visited)
        self.assertIn(str(original.BUILD), owner.phase.parsed)
        self.assertEqual(owner.phase.finish()['verified_literal_paths'], len(pins))

    def test_real_diagnostic_snapshot_BUILD_read_bytes_captured_json(self):
        owner, function, original, _ = self.fixture(diagnostic=True)
        namespace = function.__globals__
        raw = namespace['snapshot'].BUILD.read_bytes()
        build = namespace['json'].loads(raw)
        self.assertEqual(build[str(original.HARDWARE_PATH)], original.SNAPSHOT_SHA)
        self.assertEqual(owner.phase.consumed[str(original.BUILD)]['sha256'], original.BUILD_SHA)
        self.assertEqual(owner.phase.retained, 0)

    def test_real_parser_still_rejects_ordinary_Path_bypass(self):
        owner, function, original, _ = self.fixture(diagnostic=True)
        raw = original.BUILD.read_bytes()
        with self.assertRaisesRegex(Exception, 'captured bytes'):
            function.__globals__['json'].loads(raw)
        self.assertTrue(owner.phase.failed)

    def test_real_build_read_without_json_capability_rejected(self):
        owner, function, original, _ = self.fixture(json_role=False)
        with self.assertRaisesRegex(Exception, 'captured bytes'):
            function.__globals__['json'].loads(function.__globals__['snapshot'].BUILD.read_bytes())
        self.assertTrue(owner.phase.failed)

    def test_original_snapshot_paths_and_method_globals_unchanged(self):
        original = r.prior.base.population.snapshot
        build, qualified = original.BUILD, r.prior.base.population.frozen.QUALIFIED707
        owner, function, _, _ = self.fixture()
        self.assertIs(original.BUILD, build)
        self.assertIs(r.prior.base.population.frozen.QUALIFIED707, qualified)
        self.assertNotIsInstance(original.BUILD, owner.Path)
        self.assertIs(function.__globals__['snapshot'].bind_snapshot.__globals__, vars(original))
        self.assertIs(original.bind_snapshot.__globals__['BUILD'], build)
        self.assertIs(owner.context.check_config.__func__.__code__,
                      r.prior.base.population.Context.check_config.__code__)

    def test_all_private_MRO_and_family_Path_constants_bound(self):
        owner, _, _, _ = self.fixture()
        rows, methods = r.constant_inventory(owner, owner.context)
        self.assertTrue(rows)
        self.assertIn('snapshot.BUILD', {p['constant'] for p in rows})
        self.assertIn('QUALIFIED707', {p['constant'] for p in rows})
        for function in methods:
            namespace = function.__globals__
            if namespace.get('Path') is owner.Path:
                for value in namespace.values():
                    if isinstance(value, Path): self.assertIsInstance(value, owner.Path)
                if 'snapshot' in namespace:
                    for value in vars(namespace['snapshot']).values():
                        if isinstance(value, Path): self.assertIsInstance(value, owner.Path)

    def test_formal_reader_original_capture_and_diagnostic_separate(self):
        owner, _, _, _ = self.fixture()
        self.assertIs(type(owner.phase), r.prior.base.CapturePhase)
        diagnostic, _, _, _ = self.fixture(diagnostic=True)
        self.assertIs(type(diagnostic.phase), r.prior.DiagnosticPhase)
        self.assertIs(r.report.check.__code__, r.prior.report.check.__code__)
        self.assertIs(r.report.check.__globals__['wiring'].Wiring, r.Wiring)
        self.assertEqual(r.local.PLAN, 'epoch-readiness-735-v5-plan.json')
        self.assertEqual(r.prior.PLAN, 'epoch-readiness-735-v4-plan.json')
        self.assertEqual(owner.max_bytes, 805306368)

    def test_diagnostic_audit_uses_bridged_factory_without_foreign_globals_loss(self):
        globals_ = r.local.audit.__globals__
        self.assertIs(globals_['DiagnosticWiring'], r.DiagnosticWiring)
        self.assertIs(globals_['report'], r.report)
        self.assertIs(globals_['prior'], r.prior.prior)
        self.assertIn(r.SCRIPT, r.dependencies())
        self.assertIn(Path(r.bridge.__file__).resolve(), r.dependencies())


if __name__ == '__main__':
    unittest.main()
