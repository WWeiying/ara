"""Private receipt fixtures and mock finalization, never EDA evidence."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('runtime_v2_test_subject', Path(__file__).with_name('run.py'))
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
s = w.original.s


class RuntimeTests(unittest.TestCase):
    def test_clone_isolation(self):
        for new, old, keys in ((w.checked_soc, w.original.checked_soc, {'builder', 'build_dependencies'}),
                               (w.run, w.original.run, {'checked_soc', 'own_pins'})):
            self.assertIs(new.__code__, old.__code__)
            self.assertIsNot(new.__globals__, old.__globals__)
            self.assertEqual({k for k, v in old.__globals__.items() if new.__globals__[k] is not v}, keys)
        self.assertIsNot(w.builder, w.original.builder)
        self.assertIs(w.builder.expected_graph, w.build.graph.expected_graph)
        self.assertIsNot(w.original.builder.expected_graph, w.builder.expected_graph)
        self.assertIs(w.original.checked_soc.__globals__, vars(w.original))
        self.assertEqual(s.digest(Path(w.original.__file__)), w.FROZEN_SHA)

    def test_mandatory_build_and_runtime_pins(self):
        common = w.builder.load_common()
        paths = set(w.build_dependencies(common))
        self.assertTrue(set(w.original.build_dependencies(common)) <= paths)
        self.assertTrue(set(map(Path, w.build.graph.inputs())) <= paths)
        self.assertTrue(set(w.build.FILES) <= paths)
        pins = w.own_pins()
        for path in (*w.FILES, *w.build.FILES, *map(Path, w.build.graph.inputs())):
            self.assertEqual(pins[str(path)], s.digest(path))
        s.verify_pins(pins)

    def fixture(self, directory):
        root, build = directory / 'root', directory / 'build'
        root.mkdir(); build.mkdir()
        def put(path, text='fixture'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            return path
        sim = build / 'sim'
        image_paths = [put(sim / n) for n in ('simv', 'simulator.conf', 'vcs_source_manifest.json')]
        filelist = put(build / 'hardware-build/vcs/bender_script_default')
        dpi = put(build / 'hardware-build/work-dpi/elfloader.o')
        put(build / 'hardware-build/work-dpi/ara_dpi.so')
        expected = put(build / 'expected-sources.f')
        old_list = put(root / 'old-list')
        source = put(root / 'hardware/source.sv')
        vcs = put(root / 'vcs')
        put(sim / 'comp.vcs.log'); put(build / 'make.log')
        s.atomic_json(build / 'planned-command.json', ['make', 'compile'])
        s.atomic_json(build / 'make.command.json', {'argv': ['make', 'compile']})
        def collect(path, root, extras):
            return [dict(path=str(p), sha256=s.digest(p)) for p in (path, source, *extras)]
        s.atomic_json(sim / 'vcs_source_manifest.json', dict(schema_version=1, repo_root=str(root),
                      filelist=str(filelist), extra_sources=[str(dpi)], files=collect(filelist, root, [dpi])))
        image = s.hashes(image_paths)
        s.atomic_json(build / 'image-pins.json', image)
        pins = s.hashes([expected, source, vcs, *map(Path, w.build.source_inputs())])
        report = dict(state=w.original.STATE, schema='canonical_soc_v1', canonical=True, source_root=str(root),
                      plan_sha256=w.builder.PLAN_SHA, post_pins_match=True, compiler_exit_code=0,
                      execution='NOT_RUN', simulations_launched=0, performance_measured=False,
                      simv=str(sim / 'simv'), image_pins=image, config={'fixture': True},
                      lint={'command_argv': [str(vcs)]})
        status = dict(state=w.original.STATE, child_pid=None, canonical=True, source_root=str(root),
                      execution='NOT_RUN', compile_exit_code=0)
        common = SimpleNamespace(latency=SimpleNamespace(tools=SimpleNamespace(collect=collect)),
                                 SOC_REPEAT_HASHES={}, check_soc_compile=lambda *a: report['lint'])
        private_builder = SimpleNamespace(**vars(w.builder))
        private_builder.guard = lambda: {'files': []}
        private_builder.LOCKED = {}
        private_builder.OLD_LIST = old_list
        private_builder.OLD_LIST_SHA = s.digest(old_list)
        private_builder.UVM = []
        private_builder.load_common = lambda: common
        private_builder.expected_graph = lambda text: ['fixture']
        private_builder.check_graph = lambda *a: None
        private_builder.check_config = lambda path: {'fixture': True}
        private_s = SimpleNamespace(**vars(s))
        private_s.image_files = lambda simv: image_paths
        fields = w.build.clone(w.original.require_fields, {'ROOT': root})
        dependencies = w.build.clone(w.build_dependencies, {'original': SimpleNamespace(build_dependencies=lambda c: [])})
        checked = w.build.clone(w.checked_soc, dict(ROOT=root, builder=private_builder, s=private_s,
                               require_fields=fields, build_dependencies=dependencies))
        def seal():
            s.atomic_json(build / 'source-pins.json', pins)
            report['source_pins_sha256'] = s.digest(build / 'source-pins.json')
            files = [build / n for n in ('source-pins.json', 'image-pins.json', 'planned-command.json',
                     'make.log', 'make.command.json', 'hardware-build/work-dpi/ara_dpi.so')]
            report['artifact_pins'] = s.hashes([*files, filelist, dpi, sim / 'comp.vcs.log', *image_paths])
            s.atomic_json(build / 'result.json', report)
            s.atomic_json(build / 'status.json', status)
            return s.digest(build / 'result.json')
        return checked, seal, pins, report, status, build

    def test_receipt_acceptance_and_each_new_pin_mandatory(self):
        with tempfile.TemporaryDirectory() as d:
            checked, seal, pins, report, status, build = self.fixture(Path(d))
            self.assertEqual(checked(build, seal())[0]['schema'], 'canonical_soc_v1')
            for path in w.build.source_inputs():
                sha = pins.pop(path)
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'helper/tool'):
                    checked(build, seal())
                pins[path] = sha
            self.assertEqual(checked(build, seal())[0]['state'], w.original.STATE)

    def test_receipt_rejects_old_state_types_review_and_image_drift(self):
        with tempfile.TemporaryDirectory() as d:
            checked, seal, pins, report, status, build = self.fixture(Path(d))
            for key, value in (('state', 'FAIL'), ('schema', 'overlay'), ('canonical', 1),
                               ('compiler_exit_code', False), ('simulations_launched', False)):
                before = report[key]; report[key] = value
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'type/state'):
                    checked(build, seal())
                report[key] = before
            sha = seal()
            with self.assertRaisesRegex(ValueError, 'Reviewed'):
                checked(build, '0' * 64)
            (build / 'sim/simv').write_text('drift')
            with self.assertRaisesRegex(ValueError, 'image inventory'):
                checked(build, sha)

    def exercise(self, directory, preflight=False, failure=None, comparison='PASS'):
        build = directory / 'build'; build.mkdir()
        output = directory / 'out'
        args = argparse.Namespace(soc_build=build, output=output, timeout=1,
                                  expected_soc_sha256='a' * 64, preflight_only=preflight)
        calls = []
        class Owner:
            def __init__(self, path):
                self.state = {}; self.path = path
            def save(self):
                s.atomic_json(self.path / 'status.json', self.state)
            def execute(self, argv, log, timeout, phase):
                calls.append(phase)
                if phase == 'RUNNING' and failure is not None:
                    raise failure
                log.write_text('mock phase')
                s.atomic_json(log.with_suffix('.command.json'), {'argv': list(map(str, argv))})
                if phase == 'RUNNING':
                    for name in ('run.vcs.log', 'vector_trace.csv', 'commit_trace.csv'):
                        (output / 'work' / name).write_text('mock raw')
                if phase == 'CHECKING':
                    (output / 'work/uvm_result.json').write_text('mock protocol')
        report = dict(elf=str(directory / 'frozen.elf'), elf_sha256='b' * 64)
        baseline = SimpleNamespace(Consumer=lambda: SimpleNamespace(
            checked_baseline=lambda: (report, {'old': True}, [], {})))
        contract = SimpleNamespace(**vars(w.original.contract))
        contract.raw = lambda path: ({'new': True}, [])
        contract.protocol = lambda *a: calls.append('PROTOCOL')
        contract.compare = lambda *a: {'state': comparison}
        run = w.build.clone(w.run, dict(Execution=Owner, baseline=baseline, contract=contract,
            checked_soc=lambda *a: ({'simv': str(build / 'sim/simv')}, {}, {}),
            own_pins=lambda: {}, verify_current=lambda *a: None))
        if failure is None:
            result = run(args)
        else:
            with self.assertRaises(type(failure)):
                run(args)
            result = s.read_json(output / 'result.json')
        return result, calls, s.read_json(output / 'status.json')

    def test_mock_finalization_and_preflight(self):
        for preflight, comparison in ((True, 'PASS'), (False, 'PASS'), (False, 'FAIL')):
            with self.subTest(preflight=preflight, comparison=comparison), tempfile.TemporaryDirectory() as d:
                result, calls, status = self.exercise(Path(d), preflight=preflight, comparison=comparison)
                self.assertIsNone(status['child_pid'])
                self.assertEqual(status['state'], result['state'])
                self.assertIn('finished', status)
                if preflight:
                    self.assertEqual(calls, [])
                    self.assertEqual(result['simulations_launched'], 0)
                else:
                    self.assertEqual(result['state'], comparison)
                    self.assertEqual(calls, ['MANIFEST_BEFORE', 'IMAGE_CONTRACT', 'RUNNING',
                                             'CHECKING', 'PROTOCOL', 'MANIFEST_AFTER'])
                    s.verify_pins(result['evidence_sha256'])

    def test_mock_timeout_interrupt_and_failure_finalization(self):
        for exc, state in ((subprocess.TimeoutExpired('mock', 1), 'TIMEOUT'),
                           (InterruptedError('mock'), 'INTERRUPTED'), (ValueError('mock'), 'FAIL')):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as d:
                result, calls, status = self.exercise(Path(d), failure=exc)
                self.assertEqual(result['state'], state)
                self.assertEqual(status['state'], state)
                self.assertIsNone(status['child_pid'])
                self.assertNotIn('CHECKING', calls)


if __name__ == '__main__':
    unittest.main()
