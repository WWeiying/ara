import copy
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

import run_ptw_sfence_boundary_simulation as r


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = r.life.read_bound(r.PRE / 'preflight-manifest.json', r.PRE_SEAL)
        cls.target = json.loads((r.PRE / 'target-before.json').read_bytes())

    def test_actual_sealed_inputs(self):
        pins = r.validate(self.pre)
        r.life.check(pins)
        r.validate_targets(self.target)

    def test_missing_output_pin(self):
        pre = copy.deepcopy(self.pre)
        del pre['output_pins'][str(r.PRE / 'control-window-contract.json')]
        with self.assertRaises(ValueError): r.validate(pre)

    def test_wrong_elf(self):
        pre = copy.deepcopy(self.pre)
        pre['output_pins'][str(r.ELF)] = '0' * 64
        with self.assertRaises(ValueError): r.validate(pre)

    def test_original_authorization_not_relabelled(self):
        pre = copy.deepcopy(self.pre)
        pre['VCS_authorized'] = True
        with self.assertRaises(ValueError): r.validate(pre)
        self.assertIs(self.pre['VCS_authorized'], False)

    def test_boolean_not_population(self):
        pre = copy.deepcopy(self.pre)
        pre['baseline_tests'] = True
        with self.assertRaises(ValueError): r.validate(pre)

    def test_duplicate_or_extra_targets(self):
        for rows in ([self.target['targets'][0]] * 2, self.target['targets'] * 2):
            with self.assertRaises(ValueError):
                r.validate_targets(dict(baseline_tests=737, targets=rows))

    def test_wrong_checksum_or_predicate(self):
        for field, value in [('checksum', '0'), ('scope', 'injected.scope'),
                             ('predicate', 'flush_tlb_i'), ('hit_before', True), ('width', True)]:
            target = copy.deepcopy(self.target)
            target['targets'][0][field] = value
            with self.assertRaises(ValueError): r.validate_targets(target)

    def test_exact_command(self):
        out = r.life.OUT / 'ptw-command-only-test'
        command = r.command(out)
        self.assertEqual(command[0], str(r.life.IMAGE))
        self.assertEqual(command.count('+NO_FSDB'), 1)
        self.assertIn('+PRELOAD=' + str(r.ELF), command)
        self.assertIn('+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), command)
        self.assertIn('+VECTOR_TRACE=' + str(out / 'vector_trace.csv'), command)
        self.assertEqual(command[command.index('-cm') + 1], 'line+cond+fsm+tgl+branch')
        self.assertEqual(command[command.index('-cm_dir') + 1], str(out / 'code.vdb'))
        self.assertFalse(any('FSDB_FILE' in a or 'PROBE' in a for a in command))

    def test_real_reference_terminal_not_spin_tail(self):
        commits = r.oracle.shared.parse_spike_commits(Path(self.pre['input_spike_trace']))
        counts = r.reference_counts(commits, 0x80000000, self.pre['symbols']['tohost'])
        self.assertLess(counts['matched_instructions'], len(commits))
        self.assertGreater(counts['matched_scalar_memory_accesses'], 0)
        self.assertEqual(counts['expected_trap_events'], 2)
        self.assertTrue(counts['compressed_memory_must_be_audited'])

    def test_incomplete_reference_rejected(self):
        c = SimpleNamespace(pc=0x80000000, memory_accesses=(), vector_writes={}, gpr_writes={})
        with self.assertRaises(ValueError): r.reference_counts([c], 0x80000000, 0x80001000)

    def test_lifecycle_private_no_global_mutation(self):
        old = (r.frozen.BUDGET, r.frozen.PRE, r.frozen.command, r.frozen.preflight)
        ns = r.lifecycle_namespace()
        self.assertEqual(ns['BUDGET'], 300)
        self.assertEqual(ns['PRE'], r.PRE)
        self.assertIs(ns['command'], r.command)
        self.assertEqual(old, (r.frozen.BUDGET, r.frozen.PRE, r.frozen.command, r.frozen.preflight))

    def test_unreviewed_run_rejected(self):
        with self.assertRaises(ValueError):
            r.main(['run', '--output', str(r.life.OUT / 'test-no-launch'), '--prepared-seal', '0' * 64])

    def test_prepared_drift(self):
        with patch.object(r, 'manifest', return_value=dict(timeout_s=300)):
            with self.assertRaises(ValueError):
                r.verify_prepared(r.life.OUT / 'test-no-launch', dict(timeout_s=600))

    def test_actual_compiled_FSM_mapping(self):
        shape = r.life.OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml'
        tree = r.inventory.read_xml(shape)
        result = r.compiled_targets(tree)
        self.assertEqual(result['21']['source'], 'WAIT_GRANT')
        self.assertEqual(result['25']['source'], 'WAIT_RVALID')
        bad = copy.deepcopy(tree)
        definition = next(n for n in bad.iter('fsmdef') if n.get('chksum') == '3345966803')
        transition = next(n for n in definition.iter('transition') if n.get('fromid') == '5' and n.get('toid') == '1')
        transition.set('toid', '0')
        with self.assertRaises(ValueError): r.compiled_targets(bad)

    def test_unknown_compiled_scope(self):
        with self.assertRaises(ValueError): r.compiled_targets(ET.fromstring('<root/>'))


class LifecycleTests(unittest.TestCase):
    def run_mock(self, timeout=False):
        ns = r.lifecycle_namespace()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            ns['life'] = SimpleNamespace(OUT=Path(tmp), IMAGE=r.life.IMAGE,
                                         check=Mock(), save=r.life.save)
            process = Mock(pid=987654321, returncode=-9 if timeout else 0)
            process.poll.return_value = None
            process.wait.side_effect = [subprocess.TimeoutExpired('simv', 300), -9] if timeout else [0]
            record = dict(timeout_s=300, command=r.command(out), output=str(out), pins={'fixture': '0' * 64})
            with patch.object(ns['subprocess'], 'Popen', return_value=process) as launch, \
                 patch.object(ns['os'], 'killpg') as kill:
                if timeout:
                    with self.assertRaises(subprocess.TimeoutExpired): ns['run'](out, record)
                else:
                    ns['run'](out, record)
                state = json.loads((out / 'simulation-status.json').read_bytes())
                started = json.loads((out / 'started.json').read_bytes())
                self.assertEqual(started['budget_s'], 300)
                self.assertEqual(started['input_elf'], str(r.ELF))
                self.assertEqual(launch.call_count, 1)
                self.assertTrue(launch.call_args.kwargs['start_new_session'])
                self.assertIs(state['terminal_oracle_verified'], False)
                self.assertIs(state['coverage_admitted'], False)
                self.assertEqual(process.wait.call_args_list[0].kwargs, dict(timeout=300))
                if timeout:
                    kill.assert_called_once_with(process.pid, ns['signal'].SIGKILL)
                    self.assertTrue(state['process_group_cleanup'])
                    self.assertTrue(state['timeout'])
                    self.assertEqual(process.wait.call_count, 2)
                else:
                    kill.assert_not_called()
                    self.assertEqual(process.wait.call_count, 1)
                    self.assertEqual(state['status'], 'SIMULATION_EXITED_NOT_ADMITTED')

    def test_exit_zero_is_not_architecture_pass(self):
        self.run_mock()

    def test_fixed300_timeout_cleanup_no_retry(self):
        self.run_mock(timeout=True)


if __name__ == '__main__':
    unittest.main()
