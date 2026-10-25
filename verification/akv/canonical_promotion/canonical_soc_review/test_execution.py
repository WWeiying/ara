"""Exercise build receipt finalization without invoking any external tool."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    'reviewed_canonical_builder', HERE.parent / 'canonical_soc/build.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def save(path, data):
    Path(path).write_text(json.dumps(data, sort_keys=True))


def hashes(paths):
    return {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='canonical-execution-review-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'output'
        self.source = self.root / 'source.sv'
        self.source.write_text('module source; endmodule\n')
        self.old = self.root / 'old.f'
        self.old.write_text(str(self.source) + '\n')
        self.prior = self.root / 'prior/comp.vcs.log'
        self.prior.parent.mkdir()
        self.prior.write_text('old compile admission')
        (self.prior.parent / 'vcs_source_manifest.json').write_text('{}')
        self.executions = []
        self.mode = 'success'

    def collect(self, filelist, root, extras):
        paths = [self.source, filelist, *extras]
        if self.mode == 'unplanned_source' and filelist.name == 'bender_script_default':
            paths.append(self.root / 'unplanned.sv')
        return [dict(path=str(p), sha256=b.digest(p)) for p in paths]

    def image_files(self, simv):
        return [simv, simv.parent / 'simulator.conf',
                simv.parent / 'vcs_source_manifest.json']

    def common(self):
        test = self

        class Execution:
            def __init__(self, output):
                self.output, self.state, self.env = output, {}, {}

            def save(self):
                save(self.output / 'status.json', self.state)

            def execute(self, command, log, timeout, phase):
                test.executions.append((command, timeout, phase))
                self.state['compile_exit_code'] = 0
                save(log.with_suffix('.command.json'), dict(argv=command))
                log.write_text('mock make output')
                if test.mode == 'compile_failure':
                    self.state['compile_exit_code'] = 2
                    raise RuntimeError('compiler failed')
                sim = self.output / 'sim'
                work = self.output / 'hardware-build/work-dpi'
                vcs = self.output / 'hardware-build/vcs'
                for directory in (sim, work, vcs):
                    directory.mkdir(parents=True)
                filelist = vcs / 'bender_script_default'
                filelist.write_text(test.old.read_text())
                dpi = work / 'elfloader.o'
                dpi.write_bytes(b'generated object')
                (work / 'ara_dpi.so').write_bytes(b'generated library')
                (sim / 'simv').write_bytes(b'generated image, never executed')
                (sim / 'simulator.conf').write_text('test configuration')
                (sim / 'comp.vcs.log').write_text('test compiler log')
                if test.mode == 'unplanned_source':
                    (test.root / 'unplanned.sv').write_text('unplanned compilation input')
                save(sim / 'vcs_source_manifest.json', dict(
                    schema_version=1,
                    repo_root='/wrong/root' if test.mode == 'wrong_manifest' else str(b.ROOT),
                    filelist=str(filelist),
                    extra_sources=[str(dpi)], files=test.collect(filelist, b.ROOT, [dpi])))
                if test.mode == 'source_drift':
                    test.source.write_text('changed during compilation')
                if test.mode == 'missing_image':
                    (sim / 'simv').unlink()

        return SimpleNamespace(
            save=save, hand=SimpleNamespace(Execution=Execution), SOC_REPEAT_HASHES={},
            SOC_COMPILE_PRIOR=self.prior,
            latency=SimpleNamespace(tools=SimpleNamespace(collect=self.collect)),
            s=SimpleNamespace(hashes=hashes, image_files=self.image_files),
            check_soc_compile=lambda *args: dict(command_argv=args[2]))

    def execute(self, execute=True):
        tools = {'make': Path('/usr/bin/make'), 'g++': Path('/usr/bin/g++'),
                 'vcs': Path('/test/vcs')}
        with patch.multiple(b, OLD_LIST=self.old, OLD_LIST_SHA=b.digest(self.old), UVM=(),
                            guard=lambda: dict(files=[]), tool_paths=lambda: tools,
                            expected_graph=lambda text: b.tokens(text),
                            check_graph=lambda *args: None,
                            auxiliary_inputs=lambda _: hashes([self.source]),
                            load_common=self.common,
                            check_config=lambda _: dict(test=True)):
            b.run(argparse.Namespace(timeout=7200, output=self.output, execute=execute))

    def test_success_compiles_once_and_never_runs_simulator(self):
        self.execute()
        result = json.loads((self.output / 'result.json').read_text())
        status = json.loads((self.output / 'status.json').read_text())
        self.assertEqual(result['state'], 'CANONICAL_SOC_BUILT_NOT_EXECUTED')
        self.assertEqual(status['state'], result['state'])
        self.assertIsNone(status['child_pid'])
        self.assertEqual(result['simulations_launched'], 0)
        self.assertEqual(result['execution'], 'NOT_RUN')
        self.assertTrue(result['post_pins_match'])
        self.assertEqual(len(self.executions), 1)
        command, timeout, phase = self.executions[0]
        self.assertEqual((timeout, phase), (7200, 'COMPILE'))
        self.assertIn('compile', command)
        self.assertEqual(Path(command[0]).name, 'make')
        b.verify(result['artifact_pins'])

    def test_preflight_does_not_compile_or_run(self):
        self.execute(execute=False)
        result = json.loads((self.output / 'result.json').read_text())
        self.assertEqual(result['state'], 'CANONICAL_SOC_PREFLIGHT_NOT_COMPILED')
        self.assertEqual(self.executions, [])

    def test_compile_failure_never_produces_built_receipt(self):
        self.mode = 'compile_failure'
        with self.assertRaisesRegex(RuntimeError, 'compiler failed'):
            self.execute()
        self.assertEqual(json.loads((self.output / 'result.json').read_text())['state'], 'FAIL')
        self.assertIsNone(json.loads((self.output / 'status.json').read_text())['child_pid'])

    def test_source_drift_never_produces_built_receipt(self):
        self.mode = 'source_drift'
        with self.assertRaisesRegex(ValueError, 'Input drift'):
            self.execute()
        self.assertEqual(json.loads((self.output / 'result.json').read_text())['state'], 'FAIL')

    def test_missing_image_never_produces_built_receipt(self):
        self.mode = 'missing_image'
        with self.assertRaisesRegex(ValueError, 'did not produce simv'):
            self.execute()
        self.assertEqual(json.loads((self.output / 'result.json').read_text())['state'], 'FAIL')

    def test_wrong_manifest_never_produces_built_receipt(self):
        self.mode = 'wrong_manifest'
        with self.assertRaisesRegex(ValueError, 'generated source manifest'):
            self.execute()
        self.assertEqual(json.loads((self.output / 'result.json').read_text())['state'], 'FAIL')

    def test_unplanned_compilation_input_never_produces_built_receipt(self):
        self.mode = 'unplanned_source'
        with self.assertRaisesRegex(ValueError, 'not pinned before make'):
            self.execute()
        self.assertEqual(json.loads((self.output / 'result.json').read_text())['state'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
