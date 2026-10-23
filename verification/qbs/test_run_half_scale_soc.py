"""No-EDA checks for the half-scale SoC orchestration and identity gate."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_half_scale_soc as runner


class HalfScaleSocTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.elfs = self.root / 'current-elfs'
        self.elfs.mkdir()
        self.simv = self.root / 'sim/simv'
        self.simv.parent.mkdir()
        self.simv.write_bytes(b'vcs image')
        self.simv.chmod(0o755)
        libraries = Path(str(self.simv) + '.daidir')
        libraries.mkdir()
        (libraries / 'design.so').write_bytes(b'RTL')
        (self.simv.parent / 'simulator.conf').write_text('qbs=1\n')
        (self.simv.parent / 'vcs_source_manifest.json').write_text('{}\n')
        self.script = self.root / 'helper.py'
        self.script.write_text('# frozen helper\n')
        self.output = self.root / 'output'
        self.commands = []
        self.behavior = 'pass'
        self.cases = list(runner.CASES[:2])
        for case in self.cases:
            (self.elfs / case).write_bytes(b'current ABI ' + case.encode())

    def report(self, elf):
        image = runner.hashes(runner.image_files(self.simv))
        return dict(status='PASS', issues=[], elf_sha256=runner.digest(elf),
                    sim_image_sha256={path: value for path, value in image.items()
                                      if Path(path).name not in
                                      ('simulator.conf', 'vcs_source_manifest.json')})

    def fake_run(self, command, log, timeout, env, started):
        self.commands.append(command)
        started(12345)
        log.write_text('mock only\n')
        self.assertEqual(env['ARA_VCS_CODE_COVERAGE'], '0')
        if command[0] != 'bash':
            return 1 if self.behavior == 'manifest-failure' else 0
        if self.behavior == 'timeout':
            raise subprocess.TimeoutExpired(command, timeout)
        if self.behavior == 'exit-failure':
            return 1
        elf = Path(command[3])
        out = Path(command[5])
        (out / 'work').mkdir(parents=True)
        (out / 'work/input.elf').write_bytes(elf.read_bytes())
        report = self.report(elf)
        if self.behavior == 'wrong-elf':
            report['elf_sha256'] = 'stale'
        if self.behavior == 'bad-report':
            report['status'] = 'FAIL'
        (out / 'uvm_result.json').write_text(json.dumps(report))
        if self.behavior == 'image-drift':
            self.simv.write_bytes(b'changed')
        if self.behavior == 'script-drift':
            self.script.write_text('# changed\n')
        return 0

    def invoke(self, reuse=True):
        argv = ['--output', str(self.output), '--tools-root', str(self.root),
                '--elf-dir', str(self.elfs), '--cases', *self.cases]
        if reuse:
            argv += ['--simv', str(self.simv)]
        with patch.object(runner, 'script_files', return_value=[self.script]), \
                patch.object(runner, 'run_command', side_effect=self.fake_run), \
                patch.object(runner.subprocess, 'check_output', return_value='revision\n'):
            code = runner.main(argv)
        return code, json.loads((self.output / 'status.json').read_text())

    def test_checker_image_excludes_configuration_and_manifest(self):
        record = self.root / 'result.json'
        elf = self.elfs / self.cases[0]
        report = self.report(elf)
        record.write_text(json.dumps(report))
        image = runner.hashes(runner.image_files(self.simv))
        runner.check_result(record, runner.digest(elf), image)
        for field, value in [('status', 'FAIL'), ('issues', ['failure']),
                             ('elf_sha256', 'stale'), ('sim_image_sha256', {})]:
            with self.subTest(field=field):
                record.write_text(json.dumps({**report, field: value}))
                with self.assertRaises(RuntimeError):
                    runner.check_result(record, runner.digest(elf), image)

    def test_reuse_passes_without_build_and_freezes_current_elfs(self):
        code, state = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(state['state'], 'passed')
        self.assertIsNone(state['child_pid'])
        self.assertFalse(any(command[0] == 'make' for command in self.commands))
        for case in self.cases:
            frozen = self.output / 'elf' / case
            self.assertEqual(frozen.read_bytes(), (self.elfs / case).read_bytes())
            self.assertEqual(frozen.stat().st_mode & 0o222, 0)
            self.assertEqual(state['cases'][case]['state'], 'passed')
        self.assertEqual(runner.digest(self.output / 'input-pins.json'),
                         state['input_pins_sha256'])
        self.assertFalse((self.output / 'status.json.partial').exists())

    def test_failure_and_drift_stop_dispatch(self):
        for behavior in ('wrong-elf', 'bad-report', 'image-drift', 'script-drift',
                         'exit-failure', 'timeout', 'manifest-failure'):
            with self.subTest(behavior=behavior):
                self.behavior = behavior
                self.output = self.root / behavior
                self.commands.clear()
                code, state = self.invoke()
                self.assertEqual(code, 1)
                self.assertEqual(state['state'], 'failed')
                self.assertEqual(state['cases'][self.cases[1]]['state'], 'not_run')
                self.assertLessEqual(sum(c[0] == 'bash' for c in self.commands), 1)
                self.assertIsNone(state['child_pid'])

    def test_missing_manifest_prevents_dispatch(self):
        (self.simv.parent / 'vcs_source_manifest.json').unlink()
        code, state = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(state['cases'][self.cases[0]]['state'], 'not_run')
        self.assertEqual(self.commands, [])

    def test_build_command_uses_signoff_sources_and_tools_only(self):
        command = runner.build_command(self.root / 'tools', self.root / 'build')
        self.assertIn(str(runner.ROOT / 'verification'), command)
        self.assertIn('real-ara-uvm-compile', command)
        self.assertIn(f'INSTALL_DIR={self.root}/tools/install', command)
        self.assertFalse(any('apps/bin' in value for value in command))
        self.assertNotIn('verilate', command)

    def test_invalid_arguments(self):
        base = ['--output', 'out', '--tools-root', 'tools', '--elf-dir', 'elfs']
        for tail in (['--timeout', '0'], ['--build-timeout', '-1'],
                     ['--cases', 'unknown'], ['--cases', runner.CASES[0], runner.CASES[0]]):
            with self.subTest(tail=tail), self.assertRaises(SystemExit):
                runner.parse_args(base + tail)


if __name__ == '__main__':
    unittest.main()
