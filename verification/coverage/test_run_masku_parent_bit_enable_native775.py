import copy
import inspect
import json
import unittest
from unittest.mock import patch

import run_masku_parent_bit_enable_native775 as m


class LauncherTests(unittest.TestCase):
    def terminal(self):
        return dict(returncode=0, timeout=False, actual_dve=[dict(pid=123, exe='/sealed/dve',
                                                                cwd=str(m.OUT), cgroup='owning-service')])

    def test_terminal_exact_types(self):
        c = dict(identity=dict(executable='/sealed/dve'))
        m.terminal_gate(self.terminal(), c)
        for key, values in [('returncode', [False, True, 0.0, '0', None, 1]),
                            ('timeout', [0, 'false', None, True])]:
            for value in values:
                t = self.terminal(); t[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError): m.terminal_gate(t, c)

    def test_actual_identity_negatives(self):
        c = dict(identity=dict(executable='/sealed/dve'))
        for key, value in [('pid', False), ('pid', 0), ('exe', '/other/dve'), ('cwd', '/tmp'), ('cgroup', '')]:
            t = self.terminal(); t['actual_dve'][0][key] = value
            with self.assertRaises(ValueError): m.terminal_gate(t, c)
        t = self.terminal(); t['actual_dve'] *= 2
        with self.assertRaises(ValueError): m.terminal_gate(t, c)

    def test_fixed_source_and_EL_anchors(self):
        c = m.life.read_bound(m.OUT / 'config.json', m.NATIVE_SHA)
        m.source_gate(c)
        for mutation in [lambda x: x.update(sample='/another/code.vdb'),
                         lambda x: x['population_evidence'].update(current_EL='/dynamic.el'),
                         lambda x: x['population_evidence'].update(current_EL_sha256='0'*64),
                         lambda x: x['pins'].update({str(m.qualification.FULL / 'config.json'): '0'*64}),
                         lambda x: x.update(initial_X_excluded=True),
                         lambda x: x['population_evidence'].update(target_observed_hit_slots=1)]:
            bad = copy.deepcopy(c); mutation(bad)
            with self.assertRaises(ValueError): m.source_gate(bad)

    def test_existing_sample_PASS_and_negatives(self):
        docs = [json.loads((m.ADMITTED / name).read_bytes()) for name in
                ('status.json', 'scalar-comparison.json', 'vector-comparison.json')]
        docs.append(json.loads((m.SAMPLE.parent / 'simulation-status.json').read_bytes()))
        m.sample_gate(*docs)
        for index, key, value in [(0, 'status', 'PREPARED'), (1, 'status', 'PASS'),
                                  (2, 'status', 'HOLD'), (2, 'skipped_unknown_bytes', 1),
                                  (3, 'returncode', False)]:
            bad = copy.deepcopy(docs); bad[index][key] = value
            with self.assertRaises(ValueError): m.sample_gate(*bad)

    def test_private_host_adapter_only_no_launch(self):
        run = m.worker(m.OUT / 'unused-manifest.json', 'STATIC_TEST')
        self.assertEqual(run.__globals__['ENTRY'], m.qualification.ENTRY)
        code = inspect.getsource(m.host.run)
        self.assertIn('Direct owning systemd service required', code)
        self.assertIn('process.wait(timeout=c[\'timeout_seconds\'])', code)
        self.assertIn('time.sleep(10)', code)
        self.assertIn('verify_live_executable', code)

    def test_no_authorization_no_worker(self):
        with patch.object(m, 'worker') as worker, self.assertRaises(ValueError):
            m.run(m.OUT / 'unused.json', 'seal', None)
        worker.assert_not_called()


if __name__ == '__main__': unittest.main()
