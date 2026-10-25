"""Bounded host-only coordinator identity, event, rejection and launch tests."""
from argparse import Namespace
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split import coordinate as c


def fixture(root=c.HERE / 'out' / 'synthetic-coordinator'):
    entries = []
    for index, (kind, visible) in enumerate((('q4', 5), ('q4', 33), ('q8', 5), ('q8', 33))):
        build = root / f'build-{kind}-{visible}'
        output = root / f'run-{kind}-{visible}'
        worker = ['/usr/bin/python3', '-B', str(c.HERE / 'run.py'), '--build', str(build),
                  '--prerequisite', str(root / 'model'), '--output', str(output), '--timeout', '7200']
        entries.append(dict(kind=kind, visible=visible, worker_pid=1000 + index,
            simulator_pid=2000 + index, unit=f'synthetic-tail-{index}.service', output=str(output),
            elf_sha256='a' * 64, argv=['systemd-run', *worker],
            confirmation='ACTUAL_SIMV_PROCESS_CONFIRMED_ONCE',
            actual_cmdline=['/synthetic/simv', '+PRELOAD=' + str(build / 'tail_attention.elf'), '+QBS_PERF']))
    return dict(state='FOUR_ACTUAL_SIMULATORS_CONFIRMED_NO_FURTHER_POLLS', entries=entries)


def status(row, terminal=False):
    argv = c.worker_argv(row)
    return dict(pid=row['worker_pid'], build=argv[4], prerequisite=argv[6], kind=row['kind'] + '_0',
                visible=row['visible'], simulator_pid=row['simulator_pid'], simv=row['actual_cmdline'][0],
                elf=str(Path(argv[4]) / 'tail_attention.elf'), state='PASS' if terminal else 'RUNNING',
                child_pid=None if terminal else row['simulator_pid'])


class CoordinatorTests(unittest.TestCase):
    def test_exact_four_launch_identity(self):
        receipt = fixture()
        self.assertEqual(len(c.launch_entries(receipt)), 4)
        mutations = []
        for key, value in (('worker_pid', True), ('visible', True), ('kind', 'q6'),
                           ('unit', '../bad.service'), ('confirmation', 'PREPARING')):
            changed = copy.deepcopy(receipt)
            changed['entries'][0][key] = value
            mutations.append(changed)
        changed = copy.deepcopy(receipt)
        changed['entries'][1] = copy.deepcopy(changed['entries'][0])
        mutations.append(changed)
        changed = copy.deepcopy(receipt)
        changed['entries'][0]['argv'][-1] = '10800'
        mutations.append(changed)
        changed = copy.deepcopy(receipt)
        changed['entries'][0]['argv'][3] = '/wrong/run.py'
        mutations.append(changed)
        for bad in mutations:
            with self.assertRaises(ValueError):
                c.launch_entries(bad)

    def test_status_ids_and_terminal_are_strict(self):
        row = fixture()['entries'][0]
        good = status(row, True)
        c.status_identity(row, good, True)
        for key, value in (('pid', 123), ('simulator_pid', 123), ('kind', 'q8_0'),
                           ('visible', 33), ('build', '/wrong'), ('child_pid', 42), ('state', 'TIMEOUT')):
            changed = dict(good, **{key: value})
            with self.assertRaises(ValueError):
                c.status_identity(row, changed, True)

    def test_terminal_requires_result_and_pins(self):
        row = fixture()['entries'][0]
        result = dict(state='PASS', post_pins_match=True, independent_protocol_checked=True,
                      simulator_exit_code=0, elf_sha256=row['elf_sha256'], source_pins_sha256='b' * 64)
        for key, value in ((None, None), ('state', 'TIMEOUT'), ('simulator_exit_code', False),
                           ('independent_protocol_checked', False), ('source_pins_sha256', 'c' * 64)):
            changed = dict(result)
            if key:
                changed[key] = value
            with patch.object(c.s, 'read_json', side_effect=[status(row, True), changed]), \
                 patch.object(c.s, 'digest', return_value='b' * 64):
                if key:
                    with self.assertRaises(ValueError):
                        c.terminal_pass(row)
                else:
                    c.terminal_pass(row)

    def test_attach_wrong_process_closes_pidfd(self):
        row = fixture()['entries'][0]
        with patch.object(c.s, 'read_json', return_value=status(row)), \
             patch.object(c.os, 'pidfd_open', return_value=1234), \
             patch.object(c.os, 'close') as close, \
             patch.object(c.select, 'select', return_value=([], [], [])), \
             patch.object(c, 'process_identity', side_effect=ValueError('wrong script/cwd')):
            with self.assertRaises(ValueError):
                c.attach(row)
            close.assert_called_once_with(1234)

    def test_dead_owner_needs_terminal_pass(self):
        row = fixture()['entries'][0]
        with patch.object(c.s, 'read_json', return_value=status(row)), \
             patch.object(c.os, 'pidfd_open', side_effect=ProcessLookupError), \
             patch.object(c, 'terminal_pass', side_effect=ValueError('missing result')):
            with self.assertRaises(ValueError):
                c.attach(row)

    def test_real_pidfd_exit_events_no_simulation(self):
        children, handles = [], []
        try:
            for row in fixture()['entries'][:2]:
                child = subprocess.Popen(['/bin/cat'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
                children.append(child)
                handles.append((os.pidfd_open(child.pid), row))
            for child in children:
                child.stdin.close()
            completed = []
            with patch.object(c, 'terminal_pass') as terminal:
                c.wait_all(handles, 5, completed.append)
            self.assertEqual(terminal.call_count, 2)
            self.assertEqual(len(completed), 2)
        finally:
            for fd, _row in handles:
                os.close(fd)
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=5)

    def test_failure_event_stops_before_other_gate(self):
        selector = Mock()
        row = fixture()['entries'][0]
        selector.get_map.return_value = {1: object()}
        selector.select.return_value = [(Namespace(data=row, fd=1), 1)]
        with patch.object(c.selectors, 'DefaultSelector') as factory, \
             patch.object(c, 'terminal_pass', side_effect=ValueError('TIMEOUT')):
            factory.return_value.__enter__.return_value = selector
            done = Mock()
            with self.assertRaises(ValueError):
                c.wait_all([(1, row)], 5, done)
            done.assert_not_called()
            selector.select.assert_called_once()

    def test_prerequisite_error_never_starts_services(self):
        with tempfile.TemporaryDirectory(dir=c.HERE / 'out', prefix='test-coordinate-') as temp:
            root = Path(temp)
            launch = root / 'launch.json'
            launch.write_text(json.dumps(fixture(root)))
            args = Namespace(launch=launch, output=root / 'coordinator', unit_prefix='test-units',
                             wait_timeout=10, inspect_only=False)
            for kind in ('q4', 'q8'):
                for suffix in ('_build', '_prerequisite'):
                    path = root / (kind + suffix)
                    path.mkdir()
                    setattr(args, kind + suffix, path)
            with patch.object(c, 'attach', side_effect=ValueError('Owner identity invalid')), \
                 patch.object(c, 'start_services') as start:
                with self.assertRaises(ValueError):
                    c.run(args)
                start.assert_not_called()
            report = json.loads((args.output / 'result.json').read_text())
            self.assertEqual(report['state'], 'STOPPED_NO_DOWNSTREAM_ACCEPTANCE')

    def test_direct_launch_arguments_and_partial_failure_record(self):
        with tempfile.TemporaryDirectory(dir=c.HERE / 'out', prefix='test-coordinate-') as temp:
            out = Path(temp)
            targets = [dict(kind=k, build='/build-' + k, prerequisite='/strided-' + k) for k in ('q4', 'q8')]
            owner = Mock()
            owner.execute.side_effect = [None, RuntimeError('Second launch failed')]
            attempted = []
            with patch.object(c.subprocess, 'run', return_value=Namespace(stdout='not-found')), \
                 patch.object(c, 'systemctl', return_value='999'), \
                 patch.object(c, 'process_identity', return_value={'pid': 999}):
                with self.assertRaises(RuntimeError):
                    c.start_services(owner, targets, out / 'combined', out, 'test-prefix', Mock(), attempted)
            self.assertEqual(attempted, ['test-prefix-q4.service', 'test-prefix-q8.service'])
            command = owner.execute.call_args_list[0].args[0]
            self.assertIn('--service-type=exec', command)
            self.assertIn('--property=KillMode=control-group', command)
            self.assertEqual(command[command.index('/usr/bin/python3') + 2], str(c.HERE / 'threeway.py'))
            self.assertEqual(command[-2:], ['--timeout', '10800'])
            self.assertNotIn('sh', command)

    def test_cli_is_clean_and_default_builds_are_correct(self):
        result = subprocess.run([sys.executable, '-B', str(c.HERE / 'coordinate.py'), '--help'],
                                cwd='/', text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--inspect-only', result.stdout)
        self.assertIn('--q4-build', result.stdout)


if __name__ == '__main__':
    unittest.main()
