"""Actual nested helper/PROOF/compiled reads, with immutable originals; no DVE."""
from pathlib import Path
import sys
from types import FunctionType
import unittest
from unittest.mock import patch

import eight_policy_epoch_735_report_v7 as r
import prepare_mask_store_snapshot_cond24 as mask


class Paths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = r.prior.source_plan()

    def fixture(self, proof_json=True):
        original = r.prior.base.population.snapshot
        frozen = r.prior.base.population.frozen
        names = [str(p) for p in (*r.COMPILED_READS, mask.PROOF, original.BUILD,
                                 original.SNAPSHOT, frozen.SCRIPT, frozen.TCL,
                                 Path(original.__file__).resolve())]
        pins, byte_paths, json_paths = r.prior.closure({}, [], [])
        for name in names:
            pins[name] = self.source['pins'][name]
        byte_paths.extend([str(mask.PROOF), str(original.BUILD)])
        json_paths.extend([str(original.BUILD)] + ([str(mask.PROOF)] if proof_json else []))
        return r.DiagnosticWiring(pins, byte_paths, json_paths)

    def test_real_facade_read_config_and_PROOF(self):
        owner = self.fixture()
        self.assertIs(owner.eight.mask.read_config.__globals__['json'], owner.json)
        config = owner.eight.mask.read_config(owner.Path(r.prior.CAPTURE), r.prior.CONFIG_SHA)
        proof = owner.eight.snapshot_binding.__globals__['json'].loads(owner.eight.mask.PROOF.read_bytes())
        self.assertEqual(config['schema'], 'MASK_STORE_COND24_PREPARED_V1')
        self.assertEqual(len(proof['pins']), 54)
        self.assertEqual(owner.phase.consumed[str(mask.PROOF)]['sha256'], mask.PROOF_SHA)
        self.assertEqual(owner.phase.consumed[str(r.prior.CONFIG)]['sha256'], r.prior.CONFIG_SHA)
        self.assertIn(str(mask.PROOF), owner.phase.parsed)
        # All97 config pins, including hash-only RTL/tool files, remain checked.
        self.assertTrue(set(config['pins']) <= owner.phase.visited)
        self.assertEqual(owner.phase.retained, 0)

    def test_actual_Design_class_reads_all_eight_XML_inputs(self):
        owner = self.fixture()
        original = mask.proof.context # Original imports remain unchanged.
        private_class = owner.eight.seven.proof.Design
        self.assertIs(private_class.__init__.__globals__['Path'], owner.Path)
        design = private_class(owner.Path(r.DESIGN_DB.parents[2]))
        self.assertTrue(design.hierarchy)
        expected = set(map(str, r.COMPILED_READS[:2])) | {
            str(r.DESIGN_DB / ('shape/%s.verilog.%s.xml' % (metric, kind)))
            for metric in ('line', 'branch', 'tgl') for kind in ('shape', 'info')}
        self.assertTrue(expected <= set(owner.phase.consumed))
        self.assertIs(private_class.__init__.__code__,
                      r.prior.base.eight.seven.proof.Design.__init__.__code__)
        self.assertIs(mask.proof.context, original)

    def test_imported_read_xml_function_is_controlled(self):
        owner = self.fixture()
        path = r.DESIGN_DB / 'shape/cond.verilog.shape.xml'
        node = owner.eight.mask.proof.read_xml(owner.Path(path))
        self.assertTrue(node.tag)
        self.assertIn(str(path), owner.phase.consumed)

    def test_missing_PROOF_json_role_rejected(self):
        owner = self.fixture(proof_json=False)
        with self.assertRaisesRegex(Exception, 'captured bytes'):
            owner.eight.snapshot_binding.__globals__['json'].loads(owner.eight.mask.PROOF.read_bytes())
        self.assertTrue(owner.phase.failed)

    def test_original_Path_bytes_cannot_bypass_PROOF_parser(self):
        owner = self.fixture()
        with self.assertRaisesRegex(Exception, 'captured bytes'):
            owner.json.loads(mask.PROOF.read_bytes())

    def test_foreign_nested_Path_read_rejected(self):
        owner = self.fixture()
        self.assertIs(owner.eight.mask.proof.context.Path, owner.Path)
        with self.assertRaisesRegex(Exception, 'Unknown/conflicting pin'):
            owner.eight.mask.proof.context.Path('/tmp/not-in-historical735-pins').read_bytes()

    def test_PROOF_fixed_hash_change_rejected(self):
        owner = self.fixture()
        owner.phase.pins[str(mask.PROOF)] = '0' * 64
        with self.assertRaises(Exception):
            owner.eight.mask.PROOF.read_bytes()

    def test_original_modules_functions_and_classes_not_mutated(self):
        originals = {name: dict(vars(module)) for name, module in tuple(sys.modules.items())
                     if r.local_file(getattr(module, '__file__', None))}
        owner = self.fixture()
        for name, values in originals.items():
            for key, value in values.items():
                self.assertIs(vars(sys.modules[name])[key], value, name + '.' + key)
        self.assertIsNot(owner.eight.mask, mask)
        self.assertIs(owner.eight.mask.read_config.__code__, mask.read_config.__code__)
        self.assertIsInstance(owner.eight.mask.PROOF, owner.Path)

    def test_private_context_snapshot_still_controlled(self):
        owner = self.fixture()
        original = r.prior.base.population.snapshot
        function = next(vars(cls)['source_binding'] for cls in type(owner.context).__mro__
            if 'source_binding' in vars(cls) and vars(cls)['source_binding'].__code__ is
            r.prior.base.population.Context.source_binding.__code__)
        result = function(owner.context, dict(owner.pins))
        self.assertEqual(result['sha256'], original.SNAPSHOT_SHA)
        self.assertIn(str(original.BUILD), owner.phase.parsed)

    def test_inventory_includes_nested_modules_and_class_method_namespaces(self):
        owner = self.fixture()
        names = {row['namespace'] for row in owner.path_closure_inventory}
        self.assertTrue({'prepare_mask_store_snapshot_cond24', 'prove_mask_store_snapshot_zero',
                         'audit_readonly', 'closure_point_inventory'} <= names)
        for row in owner.path_closure_inventory:
            self.assertTrue(all(Path(p['literal']).is_absolute() for p in row['paths']))
        self.assertTrue(any(c['module'] == 'audit_readonly' and c['name'] == 'Design'
                            for c in owner.path_closure_classes))

    def test_all_used_global_Path_constants_are_bound(self):
        owner = self.fixture()
        graph = r.PathClosure(owner)
        graph.install()
        for namespace in graph.namespaces.values():
            for value in namespace.values():
                if isinstance(value, Path):
                    self.assertIsInstance(value, owner.Path)

    def test_container_Path_constants_use_private_copies(self):
        owner = self.fixture()
        original = {'CHECKS': ([mask.PROOF], {mask.PROOF: mask.PROOF})}
        values = dict(__name__='path_fixture', __file__=str(r.SCRIPT), **original)
        graph = r.PathClosure(owner)
        bound = graph.namespace(values, 'fixture')
        self.assertIsInstance(bound['CHECKS'][0][0], owner.Path)
        self.assertIsInstance(next(iter(bound['CHECKS'][1])), owner.Path)
        self.assertEqual(len(owner.json.loads(bound['CHECKS'][0][0].read_bytes())['pins']), 54)
        self.assertIs(values['CHECKS'], original['CHECKS'])
        self.assertFalse(isinstance(values['CHECKS'][0][0], owner.Path))

    def test_read_roles_do_not_add_or_change_pins_or_native_targets(self):
        old = r.prior.source_plan()
        new = r.source_plan()
        self.assertEqual(old['pins'], new['pins'])
        self.assertEqual(old['json_paths'], new['json_paths'])
        self.assertEqual(set(new['byte_paths']) - set(old['byte_paths']), set(map(str, r.COMPILED_READS)))
        for key in ('targets', 'protected', 'audited', 'generated_paths', 'fixed_seal'):
            self.assertEqual(new[key], old[key])

    def test_compiled_role_requires_preexisting_historical_pin(self):
        with self.assertRaisesRegex(Exception, 'compiled read authority'):
            r.read_roles({}, [], [])

    def test_simple_SHA_hook_only_accepts_pure_expression(self):
        def digest(path):
            r.require(path, 'Additional guard must not be replaced')
            return mask.proof.digest(path)
        self.assertTrue(r.simple_sha(mask.proof.digest))
        self.assertFalse(r.simple_sha(digest))

    def test_integrity_phases_keep_nested_paths_bound_to_fresh_store(self):
        owner = self.fixture()
        for phase in ('pre', 'live', 'post'):
            if phase != 'pre':
                owner.enter(phase)
            proof = owner.json.loads(owner.eight.mask.PROOF.read_bytes())
            self.assertEqual(len(proof['pins']), 54)
            self.assertIn(str(mask.PROOF), owner.phase.parsed)


if __name__ == '__main__':
    unittest.main()
