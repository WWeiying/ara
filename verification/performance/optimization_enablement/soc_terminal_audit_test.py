"""Fail-closed terminal, artifact, replay and process-exit event contracts."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import soc_terminal_audit as a


class TerminalTests(unittest.TestCase):
    def fixture(self):
        return dict(state='SOC_COMBINATION_CHECKED', post_pins_match=True,
            source_pins_sha256=a.CAMPAIGN_PINS, automatic_retry=False,
            whole_model=False, performance_acceptance=False,
            completed=[dict(arm=m, case=n, state='PASS', log_sha256='a'*64) for m, n in a.RUNS])

    def test_exact_terminal(self):
        self.assertEqual(len(a.terminal(self.fixture(), a.CAMPAIGN_PINS)), 7)

    def test_nonterminal_failed_partial_duplicate_and_scope_rejected(self):
        good = self.fixture()
        bad = [dict(good, state=s) for s in ('PASS', 'FAIL', 'PREPARED_NOT_EXECUTED',
                                            'ENABLEMENT_SOC_BUILT_NOT_EXECUTED')]
        bad += [dict(good, completed=good['completed'][:-1]),
                dict(good, completed=good['completed'] + good['completed'][:1]),
                dict(good, completed=list(reversed(good['completed']))),
                dict(good, error='retained failure'), dict(good, post_pins_match=False),
                dict(good, source_pins_sha256='b'*64), dict(good, whole_model=True),
                dict(good, performance_acceptance=True), dict(good, automatic_retry=True)]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                a.terminal(value, a.CAMPAIGN_PINS)

    def test_exact_json_types_not_python_bool_integer_equivalence(self):
        with self.assertRaises(ValueError): a.equal(dict(passed=True), dict(passed=1), 'type drift')
        with self.assertRaises(ValueError): a.equal([1, 2], [2, 1], 'order drift')

    def test_duplicate_json_and_identity_conflicts(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)/'bad.json'; p.write_text('{"state":1,"state":2}')
            with self.assertRaises(ValueError): a.read(p)
        with self.assertRaises(ValueError): a.merge({'file': 'a'*64}, {'file': 'b'*64})

    def test_every_artifact_missing_or_mutated_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            d = Path(root)
            for name in a.FILES: (d/name).write_text('original')
            pins = a.snapshot(d, a.FILES)
            a.verify(pins)
            for name in a.FILES:
                with self.subTest(name=name):
                    (d/name).write_text('changed')
                    with self.assertRaises(ValueError): a.verify(pins)
                    (d/name).write_text('original')
                    (d/name).unlink()
                    with self.assertRaises(OSError): a.snapshot(d, a.FILES)
                    (d/name).write_text('original')


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.program = dict(elf=str(self.work/'program.elf'))
        Path(self.program['elf']).write_bytes(b'ELF')
        self.program['elf_sha256'] = a.sha(self.program['elf'])
        self.hw = dict(simv=str(self.work/'simv'), configuration=dict(shared_fma=1))
        Path(self.hw['simv']).write_bytes(b'image')
        self.plan = dict(programs={'resident_sdk': self.program}, python='/usr/bin/python3.11',
                         simulation_seconds=5400, protocol_seconds=1200)
        for name in a.FILES: (self.work/name).write_text('raw data')
        self.proof = dict(actual_entries=dict(akv_decode_execute=6,
            akv_experimental_attention_execute_v2_native=4), numerical=dict(bitexact=True))
        (self.work/'numerical.json').write_text(json.dumps(self.proof))
        self.base = dict(status='PASS', issues=[], log_sha256=a.sha(self.work/'run.vcs.log'),
            vector_trace_sha256=a.sha(self.work/'vector.csv'),
            contract_counts=dict(exceptions=0, protocol_errors=0, outstanding=0))
        self.protocol = SimpleNamespace(check_real_uvm_log=Mock(side_effect=lambda *args, **kw: copy.deepcopy(self.base)),
            simulation_image=lambda path: {str(path): a.sha(path)})
        self.stored = dict(self.base, elf_sha256=self.program['elf_sha256'],
            simv_sha256=a.sha(self.hw['simv']), sim_image_sha256={self.hw['simv']: a.sha(self.hw['simv'])})
        (self.work/'protocol.json').write_text(json.dumps(self.stored))
        self.row = dict(arm='candidate', case='resident_sdk', state='PASS',
                        log_sha256=a.sha(self.work/'run.vcs.log'))
        self.c = SimpleNamespace(check_case=Mock(side_effect=lambda *args: copy.deepcopy(self.proof)))

    def test_protocol_replay_rechecks_strong_requirements(self):
        a.protocol_check(self.protocol, self.work, self.program, self.hw)
        _, kwargs = self.protocol.check_real_uvm_log.call_args
        self.assertTrue(all(kwargs[k] is True for k in
            ('require_events', 'require_backend', 'require_axi', 'require_axi_write')))
        self.assertEqual(kwargs['vector_trace'], self.work/'vector.csv')

    def test_protocol_failure_and_incomplete_retirement_rejected(self):
        for key, value in (('status', 'FAIL'), ('issues', ['bad']),
                           ('contract_counts', dict(exceptions=0, protocol_errors=0, outstanding=1))):
            with self.subTest(key=key):
                original = copy.deepcopy(self.base)
                self.base[key] = value
                with self.assertRaises(ValueError):
                    a.protocol_check(self.protocol, self.work, self.program, self.hw)
                self.base = original

    def test_stored_protocol_identity_or_counts_changes_rejected(self):
        for key, value in (('elf_sha256', 'a'*64), ('simv_sha256', 'a'*64),
                           ('log_sha256', 'a'*64), ('vector_trace_sha256', 'a'*64),
                           ('sim_image_sha256', {}), ('contract_counts', {})):
            with self.subTest(key=key):
                (self.work/'protocol.json').write_text(json.dumps(dict(self.stored, **{key: value})))
                with self.assertRaises(ValueError):
                    a.protocol_check(self.protocol, self.work, self.program, self.hw)

    def test_recomputed_numerical_entry_and_snapshot_contracts(self):
        with patch.object(a, 'check_commands'):
            proof, record = a.case_check(self.c, self.protocol, self.work, self.work,
                                         self.row, self.plan, self.hw)
            self.assertEqual(proof, self.proof)
            self.assertEqual(len(record['artifacts']), len(a.FILES))
            (self.work/'numerical.json').write_text('{}')
            with self.assertRaises(ValueError):
                a.case_check(self.c, self.protocol, self.work, self.work, self.row, self.plan, self.hw)

    def test_changed_original_log_hash_rejected_before_replay(self):
        (self.work/'run.vcs.log').write_text('changed')
        with self.assertRaises(ValueError):
            a.case_check(self.c, self.protocol, self.work, self.work, self.row, self.plan, self.hw)
        self.c.check_case.assert_not_called()

    def test_numerical_entry_changes_and_mid_audit_drift_rejected(self):
        with patch.object(a, 'check_commands'):
            self.proof['actual_entries']['akv_decode_execute'] = 5
            (self.work/'numerical.json').write_text(json.dumps(self.proof))
            with self.assertRaisesRegex(ValueError, 'entry count'):
                a.case_check(self.c, self.protocol, self.work, self.work, self.row, self.plan, self.hw)
            self.proof['actual_entries']['akv_decode_execute'] = 6
            (self.work/'numerical.json').write_text(json.dumps(self.proof))
            def change(*args, **kwargs):
                (self.work/'commit.csv').write_text('mutated during audit')
                return copy.deepcopy(self.base)
            self.protocol.check_real_uvm_log.side_effect = change
            with self.assertRaisesRegex(ValueError, 'Evidence drift'):
                a.case_check(self.c, self.protocol, self.work, self.work, self.row, self.plan, self.hw)

    def test_command_path_and_required_protocol_flags_are_not_optional(self):
        (self.work/'console.command.json').write_text('{}')
        with self.assertRaises(ValueError):
            a.check_commands(self.work, self.plan, self.program, self.hw, 'resident_sdk')


class ExitEventTests(unittest.TestCase):
    def test_worker_pidfd_exit_event_no_sleep_or_progress_poll(self):
        owner = dict(unit='original.service', owner_pid=123, main_pid=123)
        poll = Mock(); poll.poll.return_value = [(99, 1)]
        with patch.object(a, 'read', return_value=owner), \
             patch.object(a.subprocess, 'check_output', return_value='123\n'), \
             patch.object(a.os, 'pidfd_open', return_value=99) as opened, \
             patch.object(a.os, 'close') as closed, patch.object(a.select, 'poll', return_value=poll):
            a.wait_worker(Path('/unused'), 'original.service', 60)
            opened.assert_called_once_with(123)
            poll.poll.assert_called_once_with(60000)
            closed.assert_called_once_with(99)

    def test_pid_reuse_and_deadline_rejected(self):
        owner = dict(unit='original.service', owner_pid=123, main_pid=123)
        with patch.object(a, 'read', return_value=owner), \
             patch.object(a.subprocess, 'check_output', return_value='999\n'):
            with self.assertRaises(ValueError): a.wait_worker(Path('/unused'), 'original.service', 1)
        poll = Mock(); poll.poll.return_value = []
        with patch.object(a, 'read', return_value=owner), \
             patch.object(a.subprocess, 'check_output', return_value='123\n'), \
             patch.object(a.os, 'pidfd_open', return_value=99), patch.object(a.os, 'close'), \
             patch.object(a.select, 'poll', return_value=poll):
            with self.assertRaises(ValueError): a.wait_worker(Path('/unused'), 'original.service', 1)


class PairTests(unittest.TestCase):
    def fixture(self):
        return dict(schema='enablement-soc-qbs-pair-v1', state='QBS_FMA_PAIR_CHECKED',
            source_pins_sha256='r'*64, post_pins_match=True, post_artifacts_match=True,
            main_result_sha256='m'*64, artifact_pins_sha256='a'*64, automatic_retry=False,
            performance_acceptance=False, whole_model=False,
            completed=[dict(arm='baseline', case=n, state='PASS') for n in ('qbs_m4', 'qbs_m8')])

    def test_pair_requires_complete_terminal_and_all_hash_bindings(self):
        good = self.fixture()
        a.pair_terminal(good, 'r'*64, 'm'*64, 'a'*64)
        bad = [dict(good, **{k: value}) for k, value in (
            ('state', 'FAIL'), ('schema', 'other'), ('source_pins_sha256', 'wrong'),
            ('post_pins_match', False), ('post_artifacts_match', False),
            ('main_result_sha256', 'wrong'), ('artifact_pins_sha256', 'wrong'),
            ('automatic_retry', True), ('performance_acceptance', True), ('whole_model', True),
            ('completed', good['completed'][:1]), ('completed', list(reversed(good['completed']))))]
        for report in bad:
            with self.subTest(report=report), self.assertRaises(ValueError):
                a.pair_terminal(report, 'r'*64, 'm'*64, 'a'*64)

    def test_frozen_pair_denominators_do_not_cross_modes_or_flags(self):
        pair = a.OUT/'enablement_soc_qbs_pair_20261111_01'
        module = a.load(pair/'inputs/soc_qbs_pair.py',
            'de5ec0d9be81ffbb1a18c164b41288074244031a46f47d82a98ac862cf97fdaf', 'auditor_test_pair')
        for case, mode in (('qbs_m4', 4), ('qbs_m8', 8)):
            baseline = dict(state='PASS', outputs_bit_exact=1024, command_count=8,
                trials=[dict(id=i, mode=mode, status=0, commands=4, context=0, flags=8*i,
                    expected_flags=8*i, q8_bad=0, output_bad=0, guards_bad=0, total=100+i) for i in range(2)])
            candidate = copy.deepcopy(baseline)
            candidate['trials'][0]['total'] = 101
            rows = module.compare_trials(case, baseline, candidate)
            self.assertTrue(rows[0]['regression'])
            self.assertEqual([r['mode'] for r in rows], [mode, mode])
            for key, value in (('mode', 8 if mode == 4 else 4), ('flags', 16), ('commands', 3),
                               ('total', 0), ('id', 1)):
                bad = copy.deepcopy(candidate); bad['trials'][0][key] = value
                with self.subTest(case=case, key=key), self.assertRaises(ValueError):
                    module.compare_trials(case, baseline, bad)


if __name__ == '__main__':
    unittest.main()
