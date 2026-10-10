import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import run_masku_zero3_native796_v2 as m


class LauncherTests(unittest.TestCase):
    def fixture(self):
        p = dict(pid=123, exe='/sealed/dve', cwd=str(m.OUT), cgroup='0::' + m.CGROUP + '\n')
        w = dict(pid=123, executable='/sealed/dve', cwd=str(m.OUT), cgroup=p['cgroup'],
                 executable_verified=True, launch_pid=222, launch_starttime=10, starttime=11,
                 worker_pid=333, systemd_invocation='MODEL_ONLY')
        return (dict(returncode=0, timeout=False, actual_dve=[p]),
                dict(identity=dict(executable='/sealed/dve'), expected_cgroup=m.CGROUP),
                [p], [w], dict(systemd_invocation='MODEL_ONLY', automatic_retry=False, timeout_seconds=900))

    def test_terminal_exact_types(self):
        good = self.fixture()
        m.terminal_gate(*good)
        for key, values in [('returncode', [False, True, 0.0, '0', None, 1]),
                            ('timeout', [0, 'false', None, True])]:
            for value in values:
                bad = copy.deepcopy(good)
                bad[0][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError): m.terminal_gate(*bad)

    def test_actual_pid_exe_cwd_cgroup_and_cardinality(self):
        for key, value in [('pid', False), ('pid', 0), ('exe', '/other/dve'), ('cwd', '/tmp'),
                           ('cgroup', ''), ('cgroup', '0::' + m.CGROUP + '.extra\n')]:
            bad = copy.deepcopy(self.fixture())
            bad[0]['actual_dve'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.terminal_gate(*bad)
        for actual in ([], None, self.fixture()[0]['actual_dve'] * 2):
            bad = copy.deepcopy(self.fixture())
            bad[0]['actual_dve'] = actual
            with self.assertRaises(ValueError): m.terminal_gate(*bad)

    def test_witness_and_execution_negatives(self):
        for key, value in [('pid', False), ('executable_verified', 1), ('launch_pid', 123),
                           ('launch_pid', False), ('starttime', 9), ('launch_starttime', 0),
                           ('worker_pid', False), ('systemd_invocation', 'other')]:
            bad = copy.deepcopy(self.fixture())
            bad[3][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.terminal_gate(*bad)
        for key, value in [('systemd_invocation', 'other'), ('automatic_retry', True), ('timeout_seconds', 901)]:
            bad = copy.deepcopy(self.fixture())
            bad[4][key] = value
            with self.assertRaises(ValueError): m.terminal_gate(*bad)

    def test_cgroup_exact_not_substring(self):
        m.cgroup_gate('0::' + m.CGROUP + '\n', m.CGROUP)
        for value in ('', '0::' + m.CGROUP + '/child', '0::' + m.CGROUP + '.extra',
                      '0::' + m.CGROUP + '\n1::other', None):
            with self.assertRaises(ValueError): m.cgroup_gate(value, m.CGROUP)

    def test_owning_service_required_before_worker(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            m.owning_gate(m.OUT, dict(output=str(m.OUT), expected_cgroup=m.CGROUP))
        with patch.dict(os.environ, INVOCATION_ID='MODEL_ONLY'), patch.object(m, 'Path') as path:
            path.return_value.read_text.return_value = '0::wrong\n'
            with self.assertRaises(ValueError): m.owning_gate(m.OUT, dict(output=str(m.OUT), expected_cgroup=m.CGROUP))

    def test_no_authorization_no_worker(self):
        for reviewed in (None, '', 'other'):
            with patch.object(m, 'worker') as worker, patch.object(m, 'load_launch') as load:
                with self.assertRaises(ValueError): m.run(Path('/unused'), 'seal', reviewed)
                worker.assert_not_called()
                load.assert_not_called()

    def test_no_retry_existing_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            for name in ('launch-once.json', 'execution.json', 'terminal.json', 'native_before_0.tsv', 'first.el'):
                path = out / name
                path.write_text('PRESERVE')
                with patch.object(m, 'OUT', out), patch.object(m, 'load_launch', return_value={}), \
                     patch.object(m, 'owning_gate'), patch.object(m, 'worker') as worker:
                    with self.assertRaises(ValueError): m.run(Path('/unused'), 'seal', 'seal')
                    worker.assert_not_called()
                self.assertEqual(path.read_text(), 'PRESERVE')
                path.unlink()

    def test_real_pass_sample_and_negatives_no_eda(self):
        _, evidence = m.pass_evidence()
        self.assertEqual(evidence['vector_instructions'], 225)
        namespace = dict(need=m.need)
        exec(m.frozen_function(m.PARENT_RUN, m.PARENT_RUN_SHA, 'sample_gate'), namespace)
        docs = [json.loads((m.ADMITTED / n).read_bytes()) for n in
                ('status.json', 'scalar-comparison.json', 'vector-comparison.json')]
        docs.append(json.loads((m.SAMPLE.parent / 'simulation-status.json').read_bytes()))
        for index, key, value in [(0, 'status', 'PREPARED'), (2, 'skipped_unknown_bytes', 1),
                                  (2, 'status', 'HOLD'), (3, 'returncode', False)]:
            bad = copy.deepcopy(docs)
            bad[index][key] = value
            with self.assertRaises(ValueError): namespace['sample_gate'](*bad)

    def test_private_mature_worker_seal_entry_no_launch(self):
        run = m.worker(Path('/unused'), 'STATIC_ONLY')
        self.assertEqual(run.__globals__['ENTRY'], m.qualification.ENTRY)
        self.assertIn(('DVE_COVERAGE_OUTPUT', 'MASKU_ZERO3_SEAL'), run.__code__.co_consts)
        self.assertEqual(m.digest(m.HOST), m.HOST_SHA)
        self.assertEqual(m.digest(Path(m.tools.__file__)), m.TOOLS_SHA)

    def model_worker(self, reject_live=False):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            with patch.object(m, 'OUT', out):
                terminal, c, live, witnesses, _ = self.fixture()
                c.update(output=str(out), timeout_seconds=900)
                c['identity']['roles'] = dict(xvfb_run='/fake/xvfb', launcher='/fake/dve')
                p = MagicMock()
                p.name = '123'
                def member(name):
                    item = MagicMock()
                    item.resolve.return_value = Path('/sealed/dve') if name == 'exe' else out
                    item.read_text.return_value = '0::' + m.CGROUP + '\n'
                    return item
                p.__truediv__.side_effect = member
                process = SimpleNamespace(pid=222, returncode=0, wait=MagicMock())
                popen = MagicMock(return_value=process)
                clock = MagicMock(side_effect=[100, 125])
                run = m.worker(Path('/unused'), 'STATIC_ONLY')
                run.__globals__.update(load_launch=lambda *_: c, owning_gate=lambda *_: None,
                    Path=lambda path: SimpleNamespace(iterdir=lambda: [p]) if path == '/proc' else Path(path),
                    subprocess=SimpleNamespace(Popen=popen, STDOUT=subprocess_stdout(), TimeoutExpired=TimeoutError),
                    time=SimpleNamespace(monotonic=clock, sleep=lambda *_: None),
                    tools=SimpleNamespace(controlled_environment=lambda *_: {}, process_info=lambda _: dict(starttime=10)),
                    live_gate=MagicMock(side_effect=ValueError('BAD_WITNESS') if reject_live else None,
                                        return_value=witnesses[0]))
                def verify(o, seal):
                    m.terminal_gate(json.loads((o / 'terminal.json').read_bytes()), c,
                                    json.loads((o / 'live-identity.json').read_bytes()),
                                    json.loads((o / 'process-witness.json').read_bytes()),
                                    json.loads((o / 'execution.json').read_bytes()))
                run.__globals__['verify'] = verify
                with patch.dict(os.environ, INVOCATION_ID='MODEL_ONLY'):
                    if reject_live:
                        with self.assertRaises(ValueError): run(out, m.NATIVE_SHA)
                        self.assertTrue((out / 'qualification-reject.json').exists())
                        self.assertTrue((out / 'process-validation-error.json').exists())
                    else:
                        run(out, m.NATIVE_SHA)
                        self.assertEqual(process.wait.call_args.kwargs['timeout'], 875)
                        self.assertEqual(popen.call_args.kwargs['env']['MASKU_ZERO3_SEAL'], m.NATIVE_SHA)
                        self.assertTrue(popen.call_args.kwargs['start_new_session'])
                        self.assertEqual(popen.call_args.kwargs['cwd'], out)
                    self.assertFalse((out / 'capture-result.json').exists())

    def test_worker_model_total900s_env_and_proc_witness(self): self.model_worker()
    def test_worker_model_bad_witness_preserves_terminal_reject(self): self.model_worker(True)

    def test_prepare_invalid_directory_never_calls_tool_or_popen(self):
        with patch.object(m.tools, 'prepare') as prepare, patch.object(m.subprocess, 'Popen') as popen:
            with self.assertRaises(ValueError): m.prepare(Path('/tmp/foreign'))
            prepare.assert_not_called()
            popen.assert_not_called()


def subprocess_stdout():
    return -2


if __name__ == '__main__': unittest.main()
