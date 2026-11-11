#!/usr/bin/env python3
"""Retained execution mutations plus exact single-/multi-group INFO census."""
import argparse
import copy
import json
from pathlib import Path
import signal
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_v4 as v
import test_run_v3 as previous

previous.v = v.v3
previous.original.r, previous.original.c = v.b, v.b.c


class InfoCensusTests(previous.FinalImageTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for kind, (bound, events) in cls.events.items():
            fixture = cls.data[kind][3]
            expanded, trial, index = [], -1, 0
            while index < len(events):
                tag, row = events[index]
                if tag == 'exec' and row['pc'] == bound['entries']['feature_full_call']['pc']:
                    trial += 1
                if tag == 'exec' and index + 1 < len(events) and events[index + 1][0] == 'info':
                    for _ in range(v.check.info_per_index(fixture, trial)):
                        expanded.extend(copy.deepcopy(events[index:index + 2]))
                    index += 2
                else:
                    expanded.append(copy.deepcopy(events[index]))
                    index += 1
            cls.events[kind] = bound, expanded

    def architecture(self, kind, events=None):
        _, _, frozen, fixture, _, groups, flags, _ = self.data[kind]
        bound, original = self.events[kind]
        return v.check.c.stage4_architecture(original if events is None else events, fixture, frozen,
                                             bound, groups, dict(fcsr=flags))

    def test_direct_service_limits_environment_and_frozen_worker(self):
        out = v.v3.OUT / 'stage5_qemu_execution_host_recipe'
        args = v.service_argv(out, self.recipe(out), 'a' * 64)
        for token in ('--property=Type=exec', '--property=MemoryMax=8G', '--property=RuntimeMaxSec=3000'):
            self.assertIn(token, args)
        self.assertIn(str(out / 'inputs/run_v4.py'), args)
        self.assertNotIn(str(out / 'inputs/run_v3.py'), args)

    def test_three_new_guests_no_historical_audit_credit(self):
        selected = self.recipe(v.v3.OUT / 'stage5_qemu_execution_host_recipe')
        self.assertEqual([job['kind'] for job in selected['commands']], ['qbs', 'perf', 'functional'])
        self.assertFalse(selected['historical_qbs_audit_used'])
        self.assertNotIn('qbs_audit', selected)
        self.assertEqual(selected['schema'], 'stage5-qemu-unchanged-execution-v4')
        for job in selected['commands']:
            self.assertEqual(job['guest'][0], str(v.v3.BUILD / 'qemu-system-riscv64'))
            self.assertTrue(job['checker'][2].endswith('/inputs/check_v4.py'))
            self.assertIn('tcg,one-insn-per-tb=on', job['guest'])

    def test_exact_frozen_shape_census_perf32_functional152(self):
        for kind, expected in (('perf', [2] * 4), ('functional', [2] * 14 + [3, 3, 2, 2])):
            fixture = self.data[kind][3]
            self.assertEqual([v.check.info_per_index(fixture, t) for t in range(len(fixture['trials']))], expected)
            self.assertEqual(v.check.info_total(kind), 4 * sum(expected))
            self.assertEqual(self.architecture(kind)['info_records'], 4 * sum(expected))
            v.b.checked_gate(self.proof(kind), kind)

    def test_source_branches_single_head_multigroup_and_dimension_exclusion(self):
        reaches = v.check.candidate_reaches_query
        for rows, dimension, expected in ((1, 64, False), (0, 128, False), (9, 64, False),
                (2, 256, False), (6, 128, False), (6, 64, True), (6, 96, True),
                (2, 128, True), (3, 64, True), (8, 96, True)):
            self.assertIs(reaches(rows, dimension), expected)
        fixture = copy.deepcopy(self.data['functional'][3])
        case = fixture['oracle']['cases'][fixture['trials'][14]['case']]['case']
        case.update(heads=2, rows=1, dimension=64)
        self.assertEqual(v.check.info_per_index(fixture, 14), 1)
        case.update(heads=12, rows=6, dimension=128)
        self.assertEqual(v.check.info_per_index(fixture, 14), 1)
        case['dimension'] = 96
        self.assertEqual(v.check.info_per_index(fixture, 14), 3)

    def test_missing_extra_each_index_single_and_two_group_rejected(self):
        for kind, selected in (('perf', (0, 1, 2, 3)), ('functional', (0, 14, 15, 17))):
            bound, events = self.events[kind]
            indexes, trial = {}, -1
            for i, (tag, row) in enumerate(events):
                if tag == 'exec' and row['pc'] == bound['entries']['feature_full_call']['pc']:
                    trial += 1
                if tag == 'info':
                    indexes.setdefault((trial, row['index']), i)
            for trial in selected:
                for info in range(4):
                    index = indexes[trial, info]
                    for extra in (False, True):
                        changed = copy.deepcopy(events)
                        if extra:
                            changed[index - 1:index - 1] = copy.deepcopy(changed[index - 1:index + 1])
                        else:
                            del changed[index - 1:index + 1]
                        with self.subTest(kind=kind, trial=trial, info=info, extra=extra), self.assertRaises(ValueError):
                            self.architecture(kind, changed)

    def test_wrong_per_index_distribution_cannot_hide_in_total(self):
        changed = copy.deepcopy(self.events['perf'][1])
        row = next(row for tag, row in changed if tag == 'info' and row['index'] == 0)
        row.update(index=1, result=v.check.c.INFO[1])
        with self.assertRaises(ValueError):
            self.architecture('perf', changed)
        proof = self.proof('functional')
        proof['work']['info_records'] -= 8
        with self.assertRaises(ValueError):
            v.b.checked_gate(proof, 'functional')

    def test_actual_perf_offline_all_original_numerical_and_work_checks(self):
        origin = v.v3.OUT / 'stage5_qemu_execution_20261110_02'
        work = origin / 'work/perf'
        proof = v.check.check('perf', work / 'guest.log', work / 'trace.log')
        v.b.checked_gate(proof, 'perf')
        self.assertEqual(proof['numerical']['fcsr'], [3, 11, 3, 11])
        self.assertEqual(proof['numerical']['output_values'], 1024)
        self.assertEqual(proof['work']['legacy_commands'], 482)
        self.assertEqual(proof['work']['resident_commands'], 12)
        self.assertEqual(proof['work']['info_records'], 32)
        self.assertEqual(v.v3.sha(origin / 'result.json'),
                         'e0330acc921dd503a2586b80e89accdf9e21c56dd5e88833391ba3828be26135')
        self.assertEqual(v.v3.read(origin / 'result.json')['state'], 'FAIL')

    def test_pinned_query_sources_both_firmwares_unchanged(self):
        for kind in ('perf', 'functional'):
            for name, digest in v.check.QUERY_SOURCES.items():
                self.assertEqual(v.v3.sha(v.v3.OUT / v.check.c.FIRMWARE[kind][0] / 'inputs' / name), digest)


def host(output):
    output = Path(output).absolute()
    v.v3.require(output.parent == v.v3.OUT and output.name.startswith('stage5_qemu_execution_v4_host_') and
                 not output.exists(), 'Fresh owned host output required')
    output.mkdir()
    pins = {str(v.HERE / n): v.v3.sha(v.HERE / n) for n in v.OWN}
    report = dict(state='FAIL', guest_executed=False, synthetic_host_only=True, pins=pins,
                  historical_trace_unit_replay=True, original_execution02_remains_fail=True)
    def expired(sig, frame):
        raise TimeoutError('180-second V4 host bound')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        with (output / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(InfoCensusTests))
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        v.v3.require(result.wasSuccessful(), 'V4 host checks failed')
        v.v3.require(pins == {str(v.HERE / n): v.v3.sha(v.HERE / n) for n in v.OWN}, 'Host source drift')
        report['state'] = 'INFO_CENSUS_HOST_PASS_NOT_EXECUTED'
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        signal.alarm(0)
        report['log_sha256'] = v.v3.sha(output / 'host.log')
        with (output / 'result.json').open('x') as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    if '--output' in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument('--output', required=True)
        host(parser.parse_args().output)
    else:
        unittest.main()
