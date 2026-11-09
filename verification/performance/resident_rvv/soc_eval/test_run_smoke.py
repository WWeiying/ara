"""Synthetic host checks only: no compiler, systemd launch, or simulator."""
from collections import Counter
import csv
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import run_smoke as r


class SmokeChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        golden = self.root/'native_tile64.bin'
        self.bits = [0x3f000000+i for i in range(256)]
        golden.write_bytes(struct.pack('<256I', *self.bits))
        self.software = dict(golden=dict(native_tile64=str(golden), native_tile64_sha256=r.sha(golden)),
            memory_expected=dict(query_hash=1, guard_hash=2, data_hash=3, data_bytes=1024))
        self.lines = [
            'SMOKE_META d=128 heads=2 tokens=137 tile=64 arm=1 vlenb=128 status=0 groups=1 '
            'begin=100 returned=200 end=210 initial_fcsr=0 initial_vcsr=0 initial_vstart=0 fcsr=3 vcsr=0 vstart=0',
            'SMOKE_MEMORY query_hash=0000000000000001 guard_hash=0000000000000002 '
            'data_hash=0000000000000003 data_bytes=1024',
            *[f'SMOKE_OUT index={i} bits={b:08x} expected=00000000' for i, b in enumerate(self.bits)],
            'SMOKE_DONE calls=1 errors=0']

    def test_numeric_uses_host_golden_not_target_expected(self):
        answer = r.check_numerical('\n'.join(self.lines), self.software)
        self.assertTrue(answer['numerical_checked'])
        self.assertEqual((answer['bitwise_outputs'], answer['full_call_cycles']), (256, 110))
        self.lines[2] = 'SMOKE_OUT index=0 bits=deadbeef expected=deadbeef'
        with self.assertRaisesRegex(ValueError, 'bitwise output'):
            r.check_numerical('\n'.join(self.lines), self.software)

    def test_numeric_rejects_csr_memory_meta_terminal_mutations(self):
        for old, new in (('fcsr=3', 'fcsr=1'), ('initial_fcsr=0', 'initial_fcsr=3'),
            ('vstart=0', 'vstart=1'), ('heads=2', 'heads=1'), ('groups=1', 'groups=2'),
            ('returned=200', 'returned=210'), ('data_bytes=1024', 'data_bytes=1023'),
            ('guard_hash=0000000000000002', 'guard_hash=0000000000000000'),
            ('calls=1 errors=0', 'calls=1 errors=1')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                r.check_numerical('\n'.join(self.lines).replace(old, new), self.software)

    def test_numeric_duplicate_missing_unknown_and_reordered_records(self):
        cases = [self.lines[:-1], self.lines+[self.lines[-1]], self.lines[:2]+self.lines[3:],
                 self.lines[:3]+[self.lines[2]]+self.lines[3:], ['SMOKE_FAIL x=1']+self.lines,
                 [self.lines[1], self.lines[0]]+self.lines[2:]]
        for lines in cases:
            with self.subTest(lines=len(lines)), self.assertRaises(ValueError):
                r.check_numerical('\n'.join(lines), self.software)
        for old, new in (('index=0 ', 'index=1 '), ('d=128 ', 'd=128 d=128 '),
                         ('bits=3f000000', 'bits=xxxxxxxx')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                r.check_numerical('\n'.join(self.lines).replace(old, new), self.software)

    def test_golden_size_and_identity_are_required(self):
        golden = Path(self.software['golden']['native_tile64'])
        golden.write_bytes(golden.read_bytes()[:-4])
        with self.assertRaisesRegex(ValueError, 'golden drift'):
            r.check_numerical('\n'.join(self.lines), self.software)
        self.software['golden']['native_tile64_sha256'] = r.sha(golden)
        with self.assertRaisesRegex(ValueError, 'exactly 256'):
            r.check_numerical('\n'.join(self.lines), self.software)

    def vector(self, signatures, event='alloc'):
        path = self.root/'vector.csv'
        with path.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(('cycle', 'event', 'insn', 'nr_lanes', 'vlen_bits'))
            writer.writerow((0, 'config', '00000000', 4, 1024))
            for cycle, insn in enumerate(signatures, 1):
                writer.writerow((cycle, event, f'{insn:08x}', 4, 1024))
        return path

    def test_exact_vector_order_and_tail(self):
        expected = r.expected_signatures()
        self.assertEqual((len(expected), expected.count(0x0485705b)), (99, 3))
        self.assertEqual(r.check_vectors(self.vector(expected))['allocations'], 99)
        for seq in (expected[:-1], expected+[expected[-1]],
            [0x0205345b if x == 0x0485705b else x for x in expected],
            [expected[-1]]+expected[:-1]):
            with self.subTest(length=len(seq)), self.assertRaises(ValueError):
                r.check_vectors(self.vector(seq))

    def test_vector_reset_and_configuration_fail_closed(self):
        for event in ('reset', 'unknown'):
            with self.subTest(event=event), self.assertRaises(ValueError):
                r.check_vectors(self.vector(r.expected_signatures(), event))
        path = self.vector(r.expected_signatures())
        path.write_text(path.read_text().replace(',4,1024', ',8,1024'))
        with self.assertRaises(ValueError):
            r.check_vectors(path)

    def perf(self):
        _, original = r.e.contract.sealed_modules()
        expected = [v for v in original.expected_commands()[1046:1283] if v['command'] != 2]
        rows, totals = [], Counter()
        for seq, values in enumerate(expected, 1):
            row = dict.fromkeys(original.PERF_FIELDS, 0)
            row.update(values, seq=seq, id=1, success=1, busy_cycles=2,
                       context_ready=int(values['command'] != 3), read_outstanding_max=1)
            row['read_payload_bytes'] = row['q_external_bytes']+row['kv_external_bytes']+64*row['v2_full']
            for k in original.SUMMARY_FIELDS-{'records', 'success_records', 'fault_records', 'validation_fault_records'}:
                totals[k] = max(totals[k], row[k]) if k == 'read_outstanding_max' else totals[k]+row[k]
            rows.append(row)
        summary = dict(totals, records=100, success_records=100, fault_records=0, validation_fault_records=0)
        def line(prefix, row):
            return prefix+' '+' '.join(f'{k}={v}' for k, v in sorted(row.items()))
        return [line('[AKV_PERF]', row) for row in rows]+[line('[AKV_PERF_SUMMARY]', summary)]

    def test_exact_akv_work_and_summary(self):
        lines = self.perf()
        self.assertEqual(r.check_akv('\n'.join(lines))['commands'], 100)
        for changed in (lines[:-1], lines+[lines[-1]], lines[:99]+lines[100:],
            [lines[-1]]+lines[:-1],
            [lines[0].replace('success=1', 'success=0')]+lines[1:],
            [lines[0].replace('fault=0', 'fault=1')]+lines[1:],
            lines[:-1]+[lines[-1].replace('records=100', 'records=99')]):
            with self.subTest(length=len(changed)), self.assertRaises(ValueError):
                r.check_akv('\n'.join(changed))

    def test_simulation_and_protocol_recipe(self):
        commands = r.recipes(self.root, dict(simv='/fake/simv'), dict(elf='/fake/smoke.elf'), '/usr/bin/python3')
        self.assertEqual(set(commands), {'image_contract', 'simulation', 'protocol'})
        self.assertTrue({'+AKV_PERF', '+AKV_SUMMARY', '+RESIDENT_PV_PERF', '+RESIDENT_PV_WATCHDOG'} <=
                        set(commands['simulation']))
        self.assertTrue({'--require-events', '--require-backend', '--require-axi', '--require-axi-write'} <=
                        set(commands['protocol']))
        self.assertEqual((r.SIM_SECONDS, r.PROTOCOL_SECONDS, r.SERVICE_SECONDS), (3600, 600, 4500))

    def test_abba_build_rejected_before_collecting_inputs(self):
        with patch.object(r.e, 'checked_soc', return_value=(dict(image_contract={}), {})), \
             patch.object(r.e, 'verify_build', return_value=dict(kind='abba', image_contract={})):
            with self.assertRaisesRegex(ValueError, 'no ABBA'):
                r.collect(self.root, self.root)
        with patch('sys.stderr'), self.assertRaises(SystemExit):
            r.main(['prepare', '--kind', 'abba'])

    def test_direct_service_owner(self):
        unit = 'resident-pv-soc-smoke-test.service'
        r.direct_owner('/user.slice/'+unit, unit, 42, 42)
        for cgroup, pid in (('/wrong.service', 42), ('/user.slice/'+unit, 41)):
            with self.assertRaises(ValueError):
                r.direct_owner(cgroup, unit, pid, 42)

    def test_protocol_pass_binds_all_evidence(self):
        simv, library, log, vector = (self.root/n for n in ('simv', 'lib.so', 'run.log', 'vector.csv'))
        for path in (simv, library, log, vector):
            path.write_text(path.name)
        image = {str(p): r.sha(p) for p in (simv, library)}
        soc = dict(simv=str(simv), image_pins=image)
        software = dict(elf_sha256='a'*64)
        proof = dict(status='PASS', issues=[], elf_sha256='a'*64, simv_sha256=r.sha(simv),
            sim_image_sha256=image, log_sha256=r.sha(log), vector_trace_sha256=r.sha(vector))
        r.check_protocol(proof, soc, software, log, vector)
        for changed in (dict(status='FAIL'), dict(issues=['fault']), dict(elf_sha256='b'*64),
                        dict(sim_image_sha256={}), dict(vector_trace_sha256='c'*64)):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                r.check_protocol(dict(proof, **changed), soc, software, log, vector)

    def test_prepare_failure_is_preserved_without_execution(self):
        out = self.root/'attempt'
        with patch.object(r, '__file__', str(r.EVAL/'run_smoke.py')), \
             patch.object(r, 'output_path', return_value=out), \
             patch.object(r, 'collect', side_effect=ValueError('unfinished SoC')), \
             patch.object(r, 'execute', side_effect=AssertionError('No execution')):
            with self.assertRaisesRegex(ValueError, 'retained'):
                r.prepare(self.root, self.root, out)
            self.assertEqual(json.loads((out/'prepare-report.json').read_text())['state'], 'FAIL')
            self.assertFalse((out/'prepared.json').exists())
            with self.assertRaisesRegex(ValueError, 'Preserve previous'):
                r.prepare(self.root, self.root, out)


class FrozenBundle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.out = root/'soc_smoke_vcs_test'
        self.sources = root/'original'
        self.checkers = root/'ara_verify'
        self.sources.mkdir()
        self.checkers.mkdir()
        (self.out/'inputs').mkdir(parents=True)
        (self.out/'work').mkdir()
        pins = {}
        for name in r.OWN:
            for path in (self.sources/name, self.out/'inputs'/name):
                path.write_text(name+'\n')
                pins[str(path)] = r.sha(path)
        (self.checkers/'uvm_dut.py').write_text('# fixture\n')
        inventory = {str(self.checkers/'uvm_dut.py'): r.sha(self.checkers/'uvm_dut.py')}
        pins.update(inventory)
        socdir, build = root/'soc03', root/'smoke01'
        for directory in (socdir, build):
            directory.mkdir()
            (directory/'build.json').write_text('{}\n')
        soc, software = dict(simv='/fake/simv'), dict(elf='/fake/smoke.elf')
        env = r.environment()
        python = str(Path(r.sys.executable).resolve())
        s = r.selection(self.out, socdir, build, soc, software, inventory, env, python)
        (self.out/'selection.json').write_text(json.dumps(s))
        for name in ('selection.json', 'host-tests.log', 'host-tests.command.json',
                     'image-contract.log', 'image-contract.command.json'):
            path = self.out/name
            if not path.exists():
                path.write_text('fixture\n')
            pins[str(path)] = r.sha(path)
        (self.out/'source-pins.json').write_text(json.dumps(pins))
        (self.out/'prepared.json').write_text(json.dumps(r.frozen_receipt(self.out)))
        for patcher in (patch.object(r, 'OUT', root), patch.object(r, 'EVAL', self.sources),
            patch.object(r, 'ARA_VERIFY', self.checkers),
            patch.object(r, 'collect', return_value=(soc, software, dict(pins), inventory))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_frozen_bundle_has_original_and_snapshot_pins(self):
        _, pins, _, _ = r.verify_prepared(self.out)
        self.assertIn(str(self.sources/'RUN.md'), pins)
        self.assertIn(str(self.out/'inputs/RUN.md'), pins)

    def test_document_drift_rejected(self):
        (self.sources/'RUN.md').write_text('changed documentation\n')
        with self.assertRaises(ValueError):
            r.verify_prepared(self.out)

    def test_new_checker_module_rejected(self):
        (self.checkers/'extra.py').write_text('# unreviewed\n')
        with self.assertRaisesRegex(ValueError, 'inventory drift'):
            r.verify_prepared(self.out)

    def test_service_command_is_direct_and_never_launched(self):
        command = r.service_command(self.out, r.sha(self.out/'source-pins.json'))
        self.assertEqual(command[0], '/usr/bin/systemd-run')
        self.assertIn('--property=RuntimeMaxSec=4500', command)
        self.assertIn('--property=KillMode=control-group', command)
        python = str(Path(r.sys.executable).resolve())
        self.assertEqual(command[command.index(python)+1:command.index('run')],
                         ['-B', '-u', str(self.out/'inputs/run_smoke.py')])
        self.assertIn('--parent-reviewed', command)
        with self.assertRaises(ValueError):
            r.service_command(self.out, '0'*64)

    def test_run_cannot_use_live_runner_or_missing_review(self):
        for reviewed in (False, True):
            with self.subTest(reviewed=reviewed), self.assertRaises(ValueError):
                r.run(self.out, reviewed, r.sha(self.out/'source-pins.json'))
        self.assertFalse((self.out/'result.json').exists())

    def test_worker_rejects_review_inventory_drift_after_protocol(self):
        review = r.sha(self.out/'source-pins.json')

        def fake_execute(argv, cwd, log, seconds, status, status_path, phase):
            log.write_text('synthetic host-only execution\n')
            if phase == 'RUNNING':
                (self.out/'work/run.vcs.log').write_text('Core Test *** SUCCESS ***\n')
                (self.out/'work/vector_trace.csv').write_text('fixture\n')
            if phase == 'PROTOCOL_CHECK':
                (self.out/'work/uvm_result.json').write_text('{}\n')
                path = self.out/'source-pins.json'
                path.write_text(path.read_text()+' ')

        with patch.object(r, '__file__', str(self.out/'inputs/run_smoke.py')), \
             patch.object(r, 'direct_owner'), patch.object(r, 'execute', side_effect=fake_execute), \
             patch.object(r.subprocess, 'check_output', return_value=str(os.getpid())), \
             patch.object(r, 'check_numerical', return_value={}), patch.object(r, 'check_akv', return_value={}), \
             patch.object(r, 'check_vectors', return_value={}), patch.object(r, 'check_protocol'), \
             patch.object(r.e, 'check_resident_work', return_value=dict(commands=3,
                 numerical_checked=False, protocol_checked=False)), patch.dict(os.environ):
            result = r.run(self.out, True, review)
        self.assertEqual(result['state'], 'FAIL')
        self.assertIn('Reviewed run inventory drift', result['error'])
        self.assertFalse(result['independent_protocol_checked'])


if __name__ == '__main__':
    unittest.main()
