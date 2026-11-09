"""Synthetic host tests only. No prepare, systemd launch, or EDA execution."""
from collections import Counter
import csv
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import run_abba as r


class NumericalAndWork(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bits = [0x3f000000+i for i in range(256)]
        native, captured = self.root/'native.bin', self.root/'captured.bin'
        for path in (native, captured):
            path.write_bytes(struct.pack('<256I', *self.bits))
        self.memory = dict(query_hash=1, guard_hash=2, guard_bytes=5736, data_hash=3, data_bytes=135168)
        self.software = dict(golden=dict(native_tile64=str(native), native_tile64_sha256=r.sha(native),
            captured=str(captured), captured_sha256=r.sha(captured)), memory_expected=self.memory)

    def firmware(self):
        lines = ['AKV_PAIR_SHAPE d=128 qheads=2 kvheads=1 tokens=137 capacity=256 tile=64 vlenb=128']
        begin = 100
        for trial, (arm, issue, full) in enumerate(zip(r.ORDER, (100, 90, 95, 110), (120, 130, 140, 125))):
            lines += [f'AKV_PAIR_TRIAL trial={trial} arm={arm} begin={begin} returned={begin+issue} '
                f'end={begin+full} fcsr=3 vcsr=0 vstart=0 initial_fcsr=0 initial_vcsr=0 initial_vstart=0 groups=1 errors=0',
                f'AKV_PAIR_MEMORY trial={trial} query_hash=0000000000000001 guard_hash=0000000000000002 guard_bytes=5736']
            lines += [f'AKV_PAIR_OUT trial={trial} index={i} bits={v:08x}' for i, v in enumerate(self.bits)]
            begin += full+100
        return '\n'.join(lines+['AKV_PAIR_DATA data_hash=0000000000000003 data_bytes=135168 checks=1 errors=0',
            'AKV_PAIR_DONE trials=4 errors=0', 'Core Test *** SUCCESS *** (tohost = 0)', 'UVM_ERROR : 0', 'UVM_FATAL : 0'])

    def test_full_call_report_does_not_substitute_issue_latency(self):
        m = r.check_numerical(self.firmware(), self.software)
        self.assertEqual(m['host_native_bitwise_values'], 1024)
        self.assertEqual(m['issue_return_cycles'], [100, 90, 95, 110])
        self.assertEqual(m['final_drain_cycles'], [20, 40, 45, 15])
        self.assertEqual(m['complete_call_mean_cycles'], dict(strong_rotation=122.5, resident_pv=135))
        self.assertLess(m['complete_call_strong_rotation_over_resident_pv'], 1)
        self.assertFalse(m['performance_acceptance'])
        self.assertEqual(m['baseline_arm'], 'strong rotating RVV')

    def test_bitwise_rejects_tolerance_only_pass(self):
        text = self.firmware().replace('index=0 bits=3f000000', 'index=0 bits=3f000001')
        _, original = r.e.contract.sealed_modules()
        raw = Path(self.software['golden']['native_tile64']).read_bytes()
        original.check_log(text, raw, raw, self.memory)
        with self.assertRaisesRegex(ValueError, 'host-native bitwise'):
            r.check_numerical(text, self.software)

    def test_original_csr_guard_record_checks_remain_required(self):
        for old, new in (('fcsr=3', 'fcsr=1'), ('guard_bytes=5736', 'guard_bytes=0'),
            ('AKV_PAIR_DONE trials=4 errors=0', 'AKV_PAIR_DONE trials=4 errors=1'),
            ('trial=0 index=0', 'trial=0 index=1')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                r.check_numerical(self.firmware().replace(old, new), self.software)
        path = Path(self.software['golden']['captured'])
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'reference identity'):
            r.check_numerical(self.firmware(), self.software)

    def performance(self):
        _, original = r.e.contract.sealed_modules()
        totals, rows = Counter(), []
        for seq, values in enumerate(r.expected_akv(), 1):
            row = dict.fromkeys(original.PERF_FIELDS, 0)
            row.update(values, seq=seq, id=1, success=1, busy_cycles=2,
                       context_ready=int(values['command'] != 3), read_outstanding_max=1)
            row['read_payload_bytes'] = row['q_external_bytes']+row['kv_external_bytes']+64*row['v2_full']
            for k in original.SUMMARY_FIELDS-{'records', 'success_records', 'fault_records', 'validation_fault_records'}:
                totals[k] = max(totals[k], row[k]) if k == 'read_outstanding_max' else totals[k]+row[k]
            rows.append(row)
        summary = dict(totals, records=674, success_records=674, fault_records=0, validation_fault_records=0)
        def fields(prefix, row):
            return prefix+' '+' '.join(f'{k}={v}' for k, v in sorted(row.items()))
        return [fields('[AKV_PERF]', row) for row in rows]+[fields('[AKV_PERF_SUMMARY]', summary)]

    def test_legacy_counts_arm_order_and_summary(self):
        expected = r.expected_akv()
        self.assertEqual(len(expected), 674)
        self.assertEqual(sum(row['command'] == 2 for row in expected), 274)
        lines = self.performance()
        answer = r.check_akv('\n'.join(lines))
        self.assertEqual(answer['per_call_commands'], [237, 100, 100, 237])
        for changed in (lines[:-1], lines+[lines[-1]], [lines[-1]]+lines[:-1], lines[:237]+lines[238:],
            [lines[0].replace('success=1', 'success=0')]+lines[1:],
            [lines[0].replace('fault=0', 'fault=1')]+lines[1:]):
            with self.subTest(length=len(changed)), self.assertRaises(ValueError):
                r.check_akv('\n'.join(changed))

    def vector(self, signatures):
        path = self.root/'vector.csv'
        with path.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(('cycle', 'event', 'insn', 'nr_lanes', 'vlen_bits'))
            writer.writerow((0, 'config', '00000000', 4, 1024))
            for cycle, insn in enumerate(signatures, 1):
                writer.writerow((cycle, 'alloc', f'{insn:08x}', 4, 1024))
        return path

    def test_vector_exact_rotation_and_six_pv_commands(self):
        expected = r.expected_signatures()
        self.assertEqual((len(expected), expected.count(0x0485705b), expected.count(0x0205355b)), (664, 6, 136))
        self.assertEqual(r.check_vectors(self.vector(expected))['baseline_v_rows'], 274)
        for changed in (expected[:-1], expected+[0x0485705b],
            [0x0205345b if v == 0x0205355b else v for v in expected],
            [0x0205345b if v == 0x0485705b else v for v in expected]):
            with self.subTest(length=len(changed)), self.assertRaises(ValueError):
                r.check_vectors(self.vector(changed))

    def test_same_simulation_flags_and_direct_worker_command(self):
        socdir, build = self.root/'soc', self.root/'build'
        for directory in (socdir, build):
            directory.mkdir()
            (directory/'build.json').write_text('{}')
        soc, software = dict(simv='/fake/simv'), dict(elf='/fake/abba.elf')
        selected = r.selection(self.root, socdir, build, self.root/'smoke', soc, software, {}, {}, {}, '/usr/bin/python3')
        old = r.s.recipes(self.root, soc, software, '/usr/bin/python3')
        self.assertEqual(selected['commands']['protocol'], old['protocol'])
        self.assertEqual([v for v in selected['commands']['simulation'] if not v.startswith('+TESTCASE=')],
                         [v for v in old['simulation'] if not v.startswith('+TESTCASE=')])
        (self.root/'source-pins.json').write_text('{}')
        with patch.object(r, 'verify_prepared'):
            command = r.service_command(self.root, r.sha(self.root/'source-pins.json'))
        self.assertIn(str(self.root/'inputs/run_abba.py'), command)
        self.assertIn('--property=RuntimeMaxSec=4500', command)
        self.assertIn('--property=KillMode=control-group', command)


class SmokeAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.directory = root/'smoke'
        self.work = self.directory/'work'
        self.work.mkdir(parents=True)
        self.socdir = root/'soc03'
        self.socdir.mkdir()
        simv, library = self.socdir/'simv', self.socdir/'lib.so'
        simv.write_text('image')
        library.write_text('library')
        self.soc = dict(simv=str(simv), image_pins={str(p): r.sha(p) for p in (simv, library)}, configuration=dict(lanes=4))
        build = root/'smoke-build'
        build.mkdir()
        elf = build/'smoke.elf'
        elf.write_text('smoke ELF')
        self.software = dict(kind='smoke', elf=str(elf), elf_sha256=r.sha(elf))
        self.commands = r.s.recipes(self.directory, self.soc, self.software, '/usr/bin/python3')
        self.selected = dict(soc_build=str(self.socdir), build=str(build), commands=self.commands)
        source = root/'original.py'
        source.write_text('# pinned input\n')
        self.pins = {str(source): r.sha(source)}
        for name, value in (('source-pins.json', self.pins), ('selection.json', self.selected), ('prepared.json', {})):
            (self.directory/name).write_text(json.dumps(value))
        self.log, self.vector = self.work/'run.vcs.log', self.work/'vector_trace.csv'
        self.log.write_text('Core Test *** SUCCESS *** (tohost = 0)\n')
        self.vector.write_text('vector evidence\n')
        self.proof = dict(status='PASS', issues=[], elf_sha256=self.software['elf_sha256'],
            simv_sha256=r.sha(simv), sim_image_sha256=self.soc['image_pins'],
            log_sha256=r.sha(self.log), vector_trace_sha256=r.sha(self.vector), uvm_event_count=10)
        (self.work/'uvm_result.json').write_text(json.dumps(self.proof))
        for name, command, seconds in (('console', 'simulation', 3600), ('checker', 'protocol', 600)):
            (self.work/(name+'.command.json')).write_text(json.dumps(dict(argv=self.commands[command],
                cwd=str(self.work), timeout_seconds=seconds)))
        self.numeric, self.akv, self.vectors = dict(numerical_checked=True), dict(commands=100), dict(allocations=99)
        self.resident = dict(commands=3, numerical_checked=False, protocol_checked=False)
        self.result = dict(state='PASS', kind='smoke', numerical_checked=True, independent_protocol_checked=True,
            post_pins_match=True, post_image_match=True, soc_build=str(self.socdir), build=str(build),
            configuration=self.soc['configuration'], software_sha256=self.software['elf_sha256'],
            image_sha256=r.sha(simv), source_pins_sha256=r.sha(self.directory/'source-pins.json'),
            numerical=self.numeric, akv_work=self.akv, vector_work=self.vectors, resident_work=self.resident)
        self.write_result()
        protocol = {k: self.proof[k] for k in ('status', 'issues', 'log_sha256', 'vector_trace_sha256', 'uvm_event_count')}
        for patcher in (patch.object(r, 'SOC_BUILD', self.socdir), patch.object(r.s, 'output_path', side_effect=Path),
            patch.object(r.s, 'verify_prepared', return_value=(self.selected, self.pins, self.soc, self.software)),
            patch.object(r.s, 'check_numerical', return_value=self.numeric), patch.object(r.s, 'check_akv', return_value=self.akv),
            patch.object(r.s, 'check_vectors', return_value=self.vectors), patch.object(r.e, 'check_resident_work', return_value=self.resident),
            patch.object(r, 'recheck_protocol', return_value=protocol)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_result(self):
        self.result['artifacts'] = {str(p): r.sha(p) for p in self.directory.rglob('*') if p.is_file() and
            p.name not in ('result.json', 'status.json', 'service.stdout.log', 'service.stderr.log')}
        (self.directory/'result.json').write_text(json.dumps(self.result))

    def check(self):
        return r.checked_smoke(self.directory, self.socdir, self.soc)

    def test_pass_requires_reconstructed_evidence_and_returns_pins(self):
        admission, pins = self.check()
        self.assertTrue(admission['independent_recheck'])
        self.assertEqual(pins[str(self.directory/'result.json')], r.sha(self.directory/'result.json'))
        r.recheck_protocol.assert_called_once_with(self.log, self.vector)

    def test_running_missing_and_string_pass_are_not_admission(self):
        for field in ('numerical_checked', 'independent_protocol_checked', 'post_pins_match', 'post_image_match'):
            original = self.result[field]
            self.result[field] = False
            self.write_result()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check()
            self.result[field] = original
        self.result['state'] = 'RUNNING'
        self.write_result()
        with self.assertRaises(ValueError):
            self.check()
        (self.directory/'result.json').unlink()
        with self.assertRaises(FileNotFoundError):
            self.check()

    def test_same_soc03_and_smoke_software_identity_required(self):
        for change in (dict(soc_build=str(self.socdir)+'_other'), dict(software_sha256='0'*64),
                       dict(source_pins_sha256='0'*64)):
            original = dict(self.result)
            self.result.update(change)
            self.write_result()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check()
            self.result = original
        with self.assertRaises(ValueError):
            r.checked_smoke(self.directory, self.socdir.parent/'soc04', self.soc)

    def test_log_drift_rejected_even_with_resigned_artifact_list(self):
        self.log.write_text(self.log.read_text()+'changed\n')
        with self.assertRaisesRegex(ValueError, 'inventory drift'):
            self.check()
        self.write_result()
        with self.assertRaisesRegex(ValueError, 'protocol evidence'):
            self.check()

    def test_protocol_pass_string_cannot_replace_actual_protocol_recheck(self):
        with patch.object(r, 'recheck_protocol', return_value=dict(status='FAIL', issues=['AXI pending'])):
            with self.assertRaisesRegex(ValueError, 'protocol replay'):
                self.check()
        with patch.object(r, 'recheck_protocol', return_value=dict(status='PASS', issues=[], uvm_event_count=9)):
            with self.assertRaisesRegex(ValueError, 'protocol replay'):
                self.check()

    def test_numerical_report_and_protocol_flags_cannot_be_forged(self):
        self.result['numerical'] = dict(numerical_checked=True, forged=1)
        self.write_result()
        with self.assertRaisesRegex(ValueError, 'work/numerical'):
            self.check()
        self.result['numerical'] = self.numeric
        path = self.work/'checker.command.json'
        command = json.loads(path.read_text())
        command['argv'].remove('--require-axi-write')
        path.write_text(json.dumps(command))
        self.write_result()
        with self.assertRaisesRegex(ValueError, 'executed-command'):
            self.check()

    def test_live_status_and_service_logs_are_excluded(self):
        for name in ('status.json', 'service.stdout.log', 'service.stderr.log'):
            (self.directory/name).write_text('still closing')
        self.check()


if __name__ == '__main__':
    unittest.main()
