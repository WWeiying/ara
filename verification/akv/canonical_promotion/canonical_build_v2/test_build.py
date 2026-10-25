"""Host-only successor tests; frozen modules are never patched."""
import argparse
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('build_v2_test_subject', Path(__file__).with_name('build.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BuildTests(unittest.TestCase):
    def test_clone_isolation_and_only_two_replacements(self):
        self.assertIs(b.run.__code__, b.original.run.__code__)
        self.assertIsNot(b.run.__globals__, b.original.run.__globals__)
        changed = {k for k, v in b.original.run.__globals__.items() if b.run.__globals__[k] is not v}
        self.assertEqual(changed, {'expected_graph', 'auxiliary_inputs'})
        self.assertIs(b.original.check_graph.__globals__, vars(b.original))
        self.assertIs(b.run.__globals__['check_graph'], b.original.check_graph)
        self.assertIsNot(b.original.expected_graph, b.graph.expected_graph)

    def test_frozen_helper_identity(self):
        self.assertEqual(b.original.digest(Path(b.original.__file__)), b.FROZEN_SHA)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'fake.py'
            path.write_text('raise AssertionError("must not import")')
            with self.assertRaisesRegex(ValueError, 'Frozen helper drift'):
                b.load('never_loaded', path, b.FROZEN_SHA)

    def test_explicit_new_pins_and_graph_pins(self):
        pins = b.source_inputs()
        self.assertTrue(b.graph.inputs().items() <= pins.items())
        self.assertEqual({p.name for p in b.FILES}, {'build.py', 'test_build.py', 'README.md'})
        for path in b.FILES:
            self.assertEqual(pins[str(path)], b.original.digest(path))
        b.original.verify(pins)

    def test_auxiliary_merge_retains_original_and_rejects_conflict(self):
        private = SimpleNamespace(**vars(b.original))
        private.auxiliary_inputs = lambda tools: {'inherited': 'a' * 64}
        merged = b.clone(b.auxiliary_inputs, {'original': private})({})
        self.assertEqual(merged['inherited'], 'a' * 64)
        self.assertTrue(b.source_inputs().items() <= merged.items())
        private.auxiliary_inputs = lambda tools: {str(b.FILES[0]): 'bad'}
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            b.clone(b.auxiliary_inputs, {'original': private})({})

    def test_bad_graph_pin_rejected(self):
        private_graph = SimpleNamespace(inputs=lambda: {str(b.FILES[0]): '0' * 64})
        with self.assertRaisesRegex(ValueError, 'Input drift'):
            b.clone(b.source_inputs, {'graph': private_graph})()

    def test_current_graph_accepted_by_original_exact_checker(self):
        expected = b.graph.expected_graph(b.original.OLD_LIST.read_text())
        self.assertEqual(expected, b.original.tokens(b.graph.TEMPLATE.read_text()))
        self.assertEqual(len(expected), 977)
        common = b.original.load_common()
        b.original.check_graph(b.graph.TEMPLATE.read_text(), expected, common.SOC_REPEAT_HASHES)
        for bad in (expected[::-1], expected[1:], expected + [expected[-1]]):
            with self.assertRaisesRegex(ValueError, 'graph/order'):
                b.original.check_graph('\n'.join(bad), expected, common.SOC_REPEAT_HASHES)

    def test_original_rendering_is_not_exact_new_rendering(self):
        old = b.original.OLD_LIST.read_text()
        expected = b.graph.expected_graph(old)
        with self.assertRaisesRegex(ValueError, 'graph/order'):
            b.original.check_graph('\n'.join(b.original.expected_graph(old)), expected, {})

    def test_graph_errors_propagate_before_output(self):
        with tempfile.TemporaryDirectory() as d:
            args = argparse.Namespace(timeout=1, output=Path(d) / 'out', execute=False)
            def reject(text):
                raise ValueError('graph rejection')
            run = b.clone(b.run, dict(guard=lambda: {}, tool_paths=lambda: {},
                                    make_command=lambda *a: [], expected_graph=reject))
            with self.assertRaisesRegex(ValueError, 'graph rejection'):
                run(args)
            self.assertFalse(args.output.exists())

    def test_guard_precedes_tool_discovery(self):
        def reject():
            raise ValueError('promotion denied')
        def tools():
            raise AssertionError('tools must not run')
        run = b.clone(b.run, dict(guard=reject, tool_paths=tools))
        with self.assertRaisesRegex(ValueError, 'promotion denied'):
            run(argparse.Namespace(timeout=1))
        for timeout in (0, 7201, True):
            with self.assertRaisesRegex(ValueError, 'Compile bound'):
                b.run(argparse.Namespace(timeout=timeout))


if __name__ == '__main__':
    unittest.main()
