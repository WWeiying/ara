#!/usr/bin/env python3
"""Original work/numerical mutations on the final-image bindings; no guests."""
import argparse
import copy
import json
from pathlib import Path
import signal
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_v3 as v
import test_run as original

# Exercise the inherited suite against the new worker bindings in memory;
# every original test source and numerical implementation remains sealed.
original.r, original.c = v.b, v.b.c


class FinalImageTests(original.ExecutionTests):
    def recipe(self, out):
        qemu = dict(build=str(v.BUILD), build_sha256=v.BUILD_SHA,
                    executable=str(v.BUILD / 'qemu-system-riscv64'), executable_sha256=v.BINARY_SHA,
                    prepared=str(v.PREPARE), prepare_sha256=v.PREPARE_SHA)
        return v.selection(out, qemu, {k: row[1] for k, row in self.data.items()},
                           v.shared(), '/usr/bin/python3.11')

    def qbs_events(self, bound):
        points = {word: pc for pc, word in bound['custom'].items()}
        events = []
        for word, cause, tval in v.check.q.schedule():
            events.append(('exec', dict(pc=points[word], tb='0x1')))
            if cause:
                events.append(('trap', dict(pc=points[word], cause=cause, tval=tval)))
        return events

    def proof(self, kind):
        if kind != 'qbs':
            return super().proof(kind)
        bound = v.c.binding('qbs')
        return dict(state='NATIVE_ELF_ARCHITECTURE_CHECKED', kind=kind, elf_sha256=v.c.QBS_SHA,
                    work=v.check.q.architecture(self.qbs_events(bound), bound),
                    rtl_timing=False, rtl_protocol_checked=False, performance_acceptance=False,
                    qemu_image_checked=False, service_owner_checked=False,
                    correction='qemu10.2-exact-helper-decode-tval', checker_rebind='v10-same-image-qbs',
                    qemu_source=str(v.check.SOURCE), trap_sources_sha256=v.check.q.SOURCES)

    def test_native_qbs_exact_sequence_and_fault_counts(self):
        proof = self.proof('qbs')
        v.checked_gate(proof, 'qbs')
        self.assertEqual(proof['work']['native_instructions'], 190)
        self.assertEqual(proof['work']['traps'], {'2': 49, '5': 20})
        self.assertEqual(proof['work']['trap_layers'], {'helper': 46, 'decode': 3, 'access': 20})

    def test_native_qbs_missing_wrong_fault_and_extra_instruction_rejected(self):
        bound = v.c.binding('qbs')
        events = self.qbs_events(bound)
        for mutation in ('cause', 'tval', 'pc', 'missing', 'extra'):
            changed = copy.deepcopy(events)
            if mutation == 'missing':
                changed.pop()
            elif mutation == 'extra':
                changed += changed[-1:]
            else:
                next(row for tag, row in changed if tag == 'trap')[mutation] ^= 1
            with self.assertRaises(ValueError):
                v.check.q.architecture(changed, bound)

    def test_direct_service_limits_environment_and_frozen_worker(self):
        out = v.OUT / 'stage5_qemu_execution_host_recipe'
        args = v.service_argv(out, self.recipe(out), 'a' * 64)
        for option in ('--property=Type=exec', '--property=MemoryMax=8G', '--property=RuntimeMaxSec=3000'):
            self.assertIn(option, args)
        self.assertIn(str(out / 'inputs/run_v3.py'), args)
        self.assertNotIn(str(out / 'inputs/run.py'), args)
        self.assertEqual(self.recipe(out)['environment']['PYTHONDONTWRITEBYTECODE'], '1')

    def test_shared_final_reader_and_validator_closure(self):
        g = v.shared()
        self.assertEqual(v.sha(g.__file__), v.GATE_SHA)
        validator = g.validator()
        self.assertEqual(len(validator.OWN), 21)
        self.assertIn('build_v10.py', validator.OWN)
        layout = v.b.layout(g, validator)
        for name in v.OWN:
            self.assertEqual(layout[name], v.ORIGINAL / name)
        self.assertIn('shared/validator/build_v10.py', layout)
        self.assertTrue(any(name.startswith('shared/rom_probe/') for name in layout))

    def test_three_new_guests_no_historical_audit_credit(self):
        s = self.recipe(v.OUT / 'stage5_qemu_execution_host_recipe')
        self.assertEqual([j['kind'] for j in s['commands']], ['qbs', 'perf', 'functional'])
        self.assertFalse(s['historical_qbs_audit_used'])
        self.assertNotIn('qbs_audit', s)
        for row in s['commands']:
            self.assertEqual(row['guest'][0], str(v.BUILD / 'qemu-system-riscv64'))
            self.assertTrue(row['checker'][2].endswith('/inputs/check_v3.py'))
        self.assertEqual(s['commands'][0]['elf_sha256'], v.c.QBS_SHA)

    def test_old_build06_and_wrong_source_variant_rejected(self):
        out = v.OUT / 'stage5_qemu_execution_host_recipe'
        s = self.recipe(out)
        wrongs = [('build', str(v.OUT / 'stage5_qemu_build_20261110_06')),
                  ('build_sha256', '93506639dda6fc22dc66733ca2160c5ba7b799787e8fb8f5e4d067ed37d3c3d6'),
                  ('executable_sha256', '1deb41c75cc507030994765971d5a3d91f17e958c195bf60b4fb5563eb880a6f'),
                  ('prepared', str(v.OUT / 'stage5_qemu_prepare_variant_20261110_03')),
                  ('prepare_sha256', '0' * 64)]
        for key, value in wrongs:
            qemu = dict(s['qemu'], **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                v.selection(out, qemu, {}, v.shared(), s['python'])

    def test_every_qbs_layer_exact_not_zero_or_opcode_union(self):
        bound = v.c.binding('qbs')
        events = self.qbs_events(bound)
        native = -1
        for index, (tag, row) in enumerate(events):
            if tag == 'exec':
                native += 1
                continue
            keys = ('pc', 'cause', 'tval')
            for key in keys:
                changed = copy.deepcopy(events)
                if key == 'tval' and row['cause'] == 2:
                    changed[index][1][key] = 0 if native in v.check.q.FRONT else v.check.q.schedule()[native][0]
                else:
                    changed[index][1][key] ^= 1
                with self.subTest(native=native, key=key), self.assertRaises(ValueError):
                    v.check.q.architecture(changed, bound)

    def test_historical_log_offline_replay_is_not_new_guest_acceptance(self):
        work = v.OUT / 'stage5_qemu_execution_20261110_01/work/qbs'
        proof = v.check.check('qbs', work / 'guest.log', work / 'trace.log')
        v.checked_gate(proof, 'qbs')
        self.assertFalse(proof['qemu_image_checked'])
        self.assertFalse(proof['service_owner_checked'])
        self.assertEqual(v.read(work.parent.parent / 'result.json')['state'], 'FAIL')
        self.assertEqual(v.sha(v.HERE / 'run.py'), v.BASE_SHA)
        self.assertEqual(v.sha(v.HERE / 'check_v2.py'), v.check.QBS_CHECK_SHA)

    def test_source_contract_is_identical_in_new_copy(self):
        self.assertEqual(v.check.SOURCE, v.PREPARE / 'qemu-10.2.0')
        for name, digest in v.check.q.SOURCES.items():
            self.assertEqual(v.sha(v.check.SOURCE / name), digest)

    def test_qbs_incomplete_or_old_source_proof_rejected(self):
        for key, value in (('checker_rebind', 'wrong'), ('qemu_source', 'old-source'),
                           ('trap_sources_sha256', {}), ('correction', '0-or-opcode')):
            proof = self.proof('qbs')
            proof[key] = value
            with self.assertRaises(ValueError):
                v.checked_gate(proof, 'qbs')
        proof = self.proof('qbs')
        proof['work']['trap_layers'] = {'helper': 45, 'decode': 4, 'access': 20}
        with self.assertRaises(ValueError):
            v.checked_gate(proof, 'qbs')


def host(output):
    output = Path(output).absolute()
    v.require(output.parent == v.OUT and output.name.startswith('stage5_qemu_execution_v3_host_') and
              not output.exists(), 'Fresh owned host output required')
    output.mkdir()
    pins = {str(v.HERE / n): v.sha(v.HERE / n) for n in v.OWN}
    report = dict(state='FAIL', guest_executed=False, synthetic_host_only=True,
                  historical_trace_unit_replay=True, pins=pins)
    def expired(sig, frame):
        raise TimeoutError('180-second host bound')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        with (output / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(FinalImageTests))
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        v.require(result.wasSuccessful(), 'Final-image host tests failed')
        v.require(pins == {str(v.HERE / n): v.sha(v.HERE / n) for n in v.OWN}, 'Source drift')
        report['state'] = 'FINAL_IMAGE_HOST_PASS_NOT_EXECUTED'
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        signal.alarm(0)
        report['log_sha256'] = v.sha(output / 'host.log')
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
