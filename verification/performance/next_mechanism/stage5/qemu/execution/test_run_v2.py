#!/usr/bin/env python3
"""Original host suite plus exact scoped correction and remaining-job mutations."""
import argparse
import copy
import json
from pathlib import Path
import signal
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_v2 as v
import test_run as original


class SuccessorTests(original.ExecutionTests):
    def real_events(self):
        bound = v.c.binding('qbs')
        events, cancelled = v.c.trace_events((v.ORIGIN / 'work/qbs/trace.log').read_text(), set(bound['points']))
        return bound, events, cancelled

    def test_real_qbs_log_all190_all69_source_exact_replay(self):
        bound, events, cancelled = self.real_events()
        proof = v.q.check(v.ORIGIN / 'work/qbs/guest.log', v.ORIGIN / 'work/qbs/trace.log')
        self.assertEqual(proof['work']['native_instructions'], 190)
        self.assertEqual(proof['work']['trap_layers'], {'helper': 46, 'decode': 3, 'access': 20})
        self.assertEqual(proof['work']['traps'], {'2': 49, '5': 20})
        self.assertEqual(v.q.architecture(events, bound), proof['work'])
        self.assertEqual(cancelled, 0)

    def test_old_checker_and_original_failure_remain_unchanged(self):
        bound, events, _ = self.real_events()
        with self.assertRaises(ValueError):
            v.c.qbs_architecture(events, bound)
        self.assertEqual(v.sha(v.ORIGIN / 'result.json'), v.ORIGIN_SHA)
        self.assertEqual(v.read(v.ORIGIN / 'result.json')['state'], 'FAIL')
        self.assertEqual(v.sha(v.HERE / 'check.py'), v.q.BASE_SHA)
        self.assertEqual(v.sha(v.HERE / 'run.py'), v.BASE_SHA)

    def test_every_backend_zero_and_front_opcode_is_exact_not_union(self):
        bound, events, _ = self.real_events()
        native = -1
        for index, (tag, row) in enumerate(events):
            if tag == 'exec':
                native += 1
            elif tag == 'trap' and row['cause'] == 2:
                changed = copy.deepcopy(events)
                changed[index][1]['tval'] = 0 if native in v.q.FRONT else v.q.schedule()[native][0]
                with self.subTest(native=native), self.assertRaises(ValueError):
                    v.q.architecture(changed, bound)

    def test_every_access_address_pc_and_cause_stay_exact(self):
        bound, events, _ = self.real_events()
        for index, (tag, row) in enumerate(events):
            if tag != 'trap':
                continue
            keys = ('pc', 'cause', 'tval') if row['cause'] == 5 else ('pc', 'cause')
            for key in keys:
                changed = copy.deepcopy(events)
                changed[index][1][key] ^= 1
                with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                    v.q.architecture(changed, bound)

    def test_only_two_unexecuted_immutable_elfs_in_successor(self):
        old = v.read(v.ORIGIN / 'selection.json')
        path = v.OUT / 'stage5_qemu_qbs_correction_host_fixture'
        s = v.selection(v.OUT / 'stage5_qemu_execution_host_fixture', dict(qemu=old['qemu']), path, 'a' * 64)
        self.assertEqual([j['kind'] for j in s['commands']], ['perf', 'functional'])
        for got, original_job in zip(s['commands'], old['commands'][1:]):
            self.assertEqual(got['elf'], original_job['elf'])
            self.assertEqual(got['elf_sha256'], original_job['elf_sha256'])
            self.assertEqual(got['guest'][0], original_job['guest'][0])
            self.assertTrue(got['checker'][2].endswith('/inputs/check.py'))
        args = v.service_argv(v.OUT / 'stage5_qemu_execution_host_fixture', s, 'b' * 64)
        self.assertIn(str(v.OUT / 'stage5_qemu_execution_host_fixture/inputs/run_v2.py'), args)
        self.assertIn('--property=Type=exec', args)

    def test_original_guest_exit0_receipt_and_mutations(self):
        work = v.ORIGIN / 'work/qbs'
        receipt = v.read(work / 'guest.command.json')
        argv = v.read(v.ORIGIN / 'selection.json')['commands'][0]['guest']
        v.command(receipt, argv, work, work / 'guest.log', v.b.GUEST_SECONDS)
        for key, value in (('returncode', 1), ('cwd', '/wrong'), ('timeout_seconds', 301),
                           ('log_sha256', '0' * 64), ('pid', 0), ('state', 'RUNNING')):
            row = copy.deepcopy(receipt)
            row[key] = value
            with self.assertRaises(ValueError):
                v.command(row, argv, work, work / 'guest.log', v.b.GUEST_SECONDS)

    def test_actual_original_run_closed_artifact_and_owner_contract(self):
        s, report, own, guest, failed = v.origin(v.b.shared())
        self.assertEqual(report['state'], 'FAIL')
        self.assertEqual(guest['returncode'], 0)
        self.assertEqual(failed['returncode'], 1)
        self.assertEqual(own['main_pid'], 90464)
        self.assertEqual(s['qemu']['executable_sha256'], v.b.BINARY_SHA)

    def test_aggregate_requires_scoped_same_image_and_actual_rom(self):
        image = v.read(v.ORIGIN / 'selection.json')['qemu']
        fields = v.image_fields(dict(qemu=image))
        two = dict(fields, state='NATIVE_QEMU_REMAINING_TWO_GATES_CHECKED')
        native = dict(fields, state='DIRECTED_NATIVE_AKV_CHECKED',
                      rom_probe=dict(state='PASS', checked=dict(state='ROM_RAM_ONLY_FAULT_CHECKED')))
        self.assertEqual(v.combined(two, native, dict(qemu=image)), fields)
        for changed in (dict(native, executable_sha256='wrong'), dict(native, state='FAIL'),
                        dict(native, rom_probe=dict(state='FAIL'))):
            with self.assertRaises(ValueError):
                v.combined(two, changed, dict(qemu=image))
        with self.assertRaises(ValueError):
            v.combined(two, native, dict(qemu=dict(image, executable_sha256='wrong')))


def host(output):
    output = Path(output).absolute()
    v.require(output.parent == v.OUT and output.name.startswith('stage5_qemu_execution_v2_host_') and
              not output.exists(), 'Fresh owned successor host output required')
    output.mkdir()
    pins = {str(v.HERE / n): v.sha(v.HERE / n) for n in (*v.OWN, *v.b.OWN)}
    report = dict(state='FAIL', guest_executed=False, existing_qbs_trace_replayed=True,
                  original_execution_remains_fail=True, pins=pins)
    def expired(sig, frame):
        raise TimeoutError('180-second successor host bound')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        with (output / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(SuccessorTests))
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        v.require(result.wasSuccessful(), 'Successor host tests failed')
        v.require(pins == {str(v.HERE / n): v.sha(v.HERE / n) for n in (*v.OWN, *v.b.OWN)}, 'Successor source drift')
        report['state'] = 'SCOPED_SUCCESSOR_HOST_PASS_NOT_EXECUTED'
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
