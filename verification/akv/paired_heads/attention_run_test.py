"""Synthetic host-only acceptance tests. No simulator or live gate inspection."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import attention_run as runner
from run_refill_overlap_probe import COUNTERS


def metric(tag, row):
    return tag+' '+' '.join(f'{k}={v}' for k, v in row.items())


def fixture():
    lines, rows = [runner.SUBSET], []
    for trial, paired in enumerate((0, 1, 1, 0)):
        lines.append(f'AKV_PAIR_TRIAL_BEGIN trial={trial} paired={paired}')
        schedule = []
        for _kv_head in range(2):
            for tile in range(2):
                schedule.append(4 if tile == 0 else 5)
                # Independent loop dimensions: two real query heads, D128, T64.
                schedule.extend([6] * (128//4 if paired else 2*128))
                schedule.extend([2] * (64 if paired else 2*64))
            schedule.append(3)
        for cmd in schedule:
            row = dict.fromkeys(runner.PERF_FIELDS, 0)
            row.update(seq=len(rows)+1, id=0, command=cmd, success=1,
                       context_ready=int(cmd != 3), busy_cycles=10)
            if cmd in (4, 5):
                row.update(v2_full=int(cmd == 4), v2_refill=int(cmd == 5),
                    q_external_bytes=512 if cmd == 4 else 0, kv_external_bytes=32768,
                    read_ranges=131 if cmd == 4 else 128,
                    read_payload_bytes=33344 if cmd == 4 else 32768,
                    ar=140, r_beats=2100, read_outstanding_max=2,
                    read_outstanding_occ_sum=60, read_outstanding_full_cycles=20)
            elif cmd == 2:
                row.update(load=1, v2_row_load=1, replay_bytes=256)
            elif cmd == 3:
                row.update(release=1)
            else:
                row.update(v2_column_load=1, v2_column_panel=paired,
                           v2_logical_column=4 if paired else 1,
                           v2_k_view_bank_cycles=8, replay_bytes=512 if paired else 128)
            rows.append(row)
            lines.append(metric('[AKV_PERF]', row))
        lines.append(f'AKV_PAIR_ATTENTION trial={trial} paired={paired} admitted_groups={2*paired} '
                     f'native=1 kv=128 outputs=512 cycles={100000-trial*100} fcsr=3 vcsr=5 '
                     'checksum=0123456789abcdef guardbytes=384 errors=0')
    lines += [runner.SUITE, runner.TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0']
    summary = {k: sum(r[k] for r in rows) for k in COUNTERS}
    summary['read_outstanding_max'] = 2
    summary.update(records=3864, success_records=3864, fault_records=0, validation_fault_records=0)
    lines.append(metric('[AKV_PERF_SUMMARY]', summary))
    return '\n'.join(lines)+'\n'


class LogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = fixture()
        cls.first = next(x for x in cls.text.splitlines() if x.startswith('[AKV_PERF] '))

    def test_complete_unknown_checksum_and_valid_flags(self):
        result = runner.check_log(self.text)
        self.assertEqual(result['state'], 'PASS')
        self.assertEqual([t['derived_hardware_totals']['records'] for t in result['trials']],
                         [1542, 390, 390, 1542])
        summary = result['raw_hardware_summary']
        for key, value in dict(records=3864, read_outstanding_max=2, v2_logical_column=3072,
                v2_k_view_bank_cycles=18432, v2_column_load=2304, v2_row_load=1536,
                read_payload_bytes=528896, replay_bytes=786432).items():
            self.assertEqual(summary[key], value, key)
        self.assertIn('NOT ordinary RVV', result['comparison'])
        for flags in (0, 31):
            runner.check_log(self.text.replace('fcsr=3 ', f'fcsr={flags} ').replace(
                '0123456789abcdef', 'fedcba9876543210'))

    def test_strict_prefix_and_fields(self):
        bad = [self.text.replace(self.first+'\n', '', 1), self.text+self.first+'\n',
               self.text.replace(self.first, self.first+' unknown=1', 1),
               self.text.replace(self.first, self.first+' seq=1', 1),
               self.text.replace(self.first, self.first.replace(' id=0', ''), 1)]
        for marker in ('[AKV_PERF]', '[AKV_PERF_SUMMARY]', 'AKV_PAIR_SUBSET',
                       'AKV_PAIR_TRIAL_BEGIN', 'AKV_PAIR_ATTENTION', 'AKV_PAIR_ABBA_PASS'):
            bad.extend([self.text.replace(marker, marker+'_BOGUS', 1),
                        self.text.replace(marker, 'embedded '+marker, 1),
                        self.text+marker+'_UNKNOWN x=1\n'])
        for i, text in enumerate(bad):
            with self.subTest(i=i), self.assertRaises(ValueError):
                runner.check_log(text)

    def test_wrong_work_flags_admission_guards(self):
        for old, new in [('command=4', 'command=5'), ('seq=1 ', 'seq=2 '),
            ('success=1', 'success=0'), ('fault=0', 'fault=1'), ('context_ready=1', 'context_ready=0'),
            ('q_external_bytes=512', 'q_external_bytes=511'), ('v2_k_view_bank_cycles=8', 'v2_k_view_bank_cycles=7'),
            ('v2_column_panel=1', 'v2_column_panel=0'), ('v2_logical_column=4', 'v2_logical_column=1'),
            ('replay_bytes=512', 'replay_bytes=128'), ('busy_cycles=10', 'busy_cycles=x'),
            ('paired=0', 'paired=1'), ('admitted_groups=0', 'admitted_groups=2'),
            ('admitted_groups=2', 'admitted_groups=0'), ('native=1', 'native=0'),
            ('outputs=512', 'outputs=511'), ('fcsr=3', 'fcsr=1'), ('fcsr=3', 'fcsr=32'),
            ('vcsr=5', 'vcsr=0'), ('checksum=0123456789abcdef', 'checksum=0000000000000000'),
            ('guardbytes=384', 'guardbytes=383'), ('errors=0', 'errors=1'),
            ('guards=1', 'guards=0'), ('bytewise_equal=1', 'bytewise_equal=0'),
            (runner.TERMINAL, ''), (runner.SUITE, ''), (runner.SUBSET, ''),
            ('UVM_ERROR : 0', 'UVM_ERROR : 1'), ('UVM_FATAL : 0', '')]:
            with self.subTest(old=old, new=new), self.assertRaises(ValueError):
                runner.check_log(self.text.replace(old, new, 1))
        for extra in (runner.SUITE, runner.SUBSET, runner.TERMINAL, 'UVM_ERROR : 0',
                      'UVM_ERROR @ 1: mismatch', '[QBS_PERF] seq=1', 'Fatal: failed'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                runner.check_log(self.text+extra+'\n')

    def test_summary_conservation_and_external_traffic(self):
        lines = self.text.splitlines()
        for key in runner.SUMMARY_FIELDS:
            row = runner.numeric_fields(lines[-1].split(' ', 1)[1], runner.SUMMARY_FIELDS)
            row[key] += 1
            with self.subTest(summary=key), self.assertRaises(ValueError):
                runner.check_log('\n'.join(lines[:-1]+[metric('[AKV_PERF_SUMMARY]', row)]))
        changed = list(lines)
        changed[2] = changed[2].replace(' ar=140 ', ' ar=141 ')
        row = runner.numeric_fields(changed[-1].split(' ', 1)[1], runner.SUMMARY_FIELDS)
        row['ar'] += 1
        changed[-1] = metric('[AKV_PERF_SUMMARY]', row)
        with self.assertRaisesRegex(ValueError, 'External traffic differs'):
            runner.check_log('\n'.join(changed))
        # Keep all aggregate counters and sequence numbers, but exchange QK/PV work.
        changed = list(lines)
        a = next(i for i, line in enumerate(changed) if 'command=6 ' in line)
        b = next(i for i, line in enumerate(changed) if 'command=2 ' in line)
        ra = runner.numeric_fields(changed[a].split(' ', 1)[1], runner.PERF_FIELDS)
        rb = runner.numeric_fields(changed[b].split(' ', 1)[1], runner.PERF_FIELDS)
        ra['seq'], rb['seq'] = rb['seq'], ra['seq']
        changed[a], changed[b] = metric('[AKV_PERF]', rb), metric('[AKV_PERF]', ra)
        with self.assertRaises(ValueError):
            runner.check_log('\n'.join(changed))


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, data):
        p = self.root/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))
        return p

    def test_build_schema_and_pins(self):
        elf = self.write('test.elf', 'ELF')
        source = self.write('source.c', 'source')
        pins = self.write('source-pins.json', runner.hashes([source]))
        report = dict(state='BUILT_NOT_EXECUTED', execution='NOT_RUN', post_pins_match=True,
            expected=runner.EXPECTED, source_heads=[0, 1, 6, 7], source_kv_heads=[0, 1],
            tolerance=dict(atol=.004, rtol=.002), elf=str(elf), elf_sha256=runner.digest(elf),
            artifact_sha256=runner.hashes([elf]), source_pins_sha256=runner.digest(pins))
        self.write('build.json', report)
        self.assertEqual(runner.checked_build(self.root)[0], report)
        for key, value in [('state', 'PASS'), ('execution', 'PASS'), ('post_pins_match', False),
                           ('source_heads', [0, 1, 2, 3]), ('expected', {}),
                           ('tolerance', dict(atol=.005, rtol=.002)), ('elf_sha256', '0'*64)]:
            self.write('build.json', dict(report, **{key: value}))
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.checked_build(self.root)
        self.write('build.json', report)
        source.write_text('drift')
        with self.assertRaises(ValueError):
            runner.checked_build(self.root)

    def prerequisite(self):
        elf, simv = self.write('test.elf', 'ELF'), self.write('simv', 'image')
        image = runner.hashes([simv])
        log, trace = self.write('work/run.vcs.log', 'log'), self.write('work/vector_trace.csv', 'trace')
        uvm = self.write('work/uvm_result.json', dict(status='PASS', issues=[],
            elf_sha256=runner.digest(elf), sim_image_sha256=image,
            log_sha256=runner.digest(log), vector_trace_sha256=runner.digest(trace)))
        pins = self.write('source-pins.json', runner.hashes([elf, simv]))
        status = dict(state='PASS', child_pid=None, elf=str(elf), simv=str(simv))
        result = dict(state='PASS', numeric=dict(state='PASS', pairs=3, runs=6, qk_outputs=512, pv_outputs=1152),
            hardware_totals=dict(records=1044, success_records=1044, fault_records=0, validation_fault_records=0,
                v2_full=6, release=6, v2_refill=0, v2_row_load=384, v2_column_load=648,
                v2_column_panel=72, v2_logical_column=864, q_external_bytes=2304,
                kv_external_bytes=147456, read_ranges=786, read_payload_bytes=150144, replay_bytes=196416),
            evidence_sha256=runner.hashes([log, trace, uvm, pins]))
        self.write('status.json', status)
        self.write('result.json', result)
        return status, result, image

    def test_prerequisite_terminal_work_and_evidence(self):
        status, result, image = self.prerequisite()
        runner.checked_prerequisite(self.root, image)
        for state, pid in [('RUNNING', 123), ('FAIL', None), ('PASS', 123)]:
            self.write('status.json', dict(status, state=state, child_pid=pid))
            with self.subTest(state=state, pid=pid), self.assertRaises(ValueError):
                runner.checked_prerequisite(self.root, image)
        self.write('status.json', status)
        for group, key, value in [('numeric', 'state', 'FAIL'), ('numeric', 'pairs', 2),
                ('numeric', 'runs', 5), ('hardware_totals', 'records', 1043),
                ('hardware_totals', 'replay_bytes', 0)]:
            bad = copy.deepcopy(result)
            bad[group][key] = value
            self.write('result.json', bad)
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.checked_prerequisite(self.root, image)
        bad = copy.deepcopy(result)
        del bad['evidence_sha256'][str(self.root/'work/uvm_result.json')]
        self.write('result.json', bad)
        with self.assertRaises(ValueError):
            runner.checked_prerequisite(self.root, image)
        self.write('result.json', result)
        with self.assertRaises(RuntimeError):
            runner.checked_prerequisite(self.root, {str(self.root/'simv'): '0'*64})
        (self.root/'work/run.vcs.log').write_text('drift')
        with self.assertRaises(ValueError):
            runner.checked_prerequisite(self.root, image)

    def test_prerequisite_uvm_identity_even_with_updated_receipt(self):
        _status, result, image = self.prerequisite()
        path = self.root/'work/uvm_result.json'
        good = runner.read_json(path)
        for key, value in [('status', 'FAIL'), ('issues', ['issue']), ('elf_sha256', '0'*64),
                           ('log_sha256', '0'*64), ('vector_trace_sha256', '0'*64)]:
            self.write('work/uvm_result.json', dict(good, **{key: value}))
            result['evidence_sha256'][str(path)] = runner.digest(path)
            self.write('result.json', result)
            with self.subTest(key=key), self.assertRaises((ValueError, RuntimeError)):
                runner.checked_prerequisite(self.root, image)

    def test_no_launch_on_failed_prerequisite(self):
        build, gate, prereq, integration = (self.root/n for n in ('build', 'gate', 'prereq', 'integration'))
        for p in (build, gate, prereq, integration/'build/sim'):
            p.mkdir(parents=True)
        simv = self.write('integration/build/sim/simv', 'image')
        image = runner.hashes([simv])
        argv = ['worker', '--build', str(build), '--output', str(self.root/'out'),
                '--gate', str(gate), '--prerequisite', str(prereq), '--integration', str(integration)]
        with patch.object(runner.sys, 'argv', argv), patch.object(runner.signal, 'signal'), \
             patch.object(runner, 'checked_build', return_value=(dict(simv=str(simv), accepted_image_pins=image), {})), \
             patch.object(runner, 'checked_image', return_value=(image, {})), \
             patch.object(runner, 'checked_prerequisite', side_effect=ValueError('not PASS')), \
             patch.object(runner, 'run_command') as launch:
            with self.assertRaisesRegex(ValueError, 'not PASS'):
                runner.main()
            launch.assert_not_called()
        self.assertEqual(runner.read_json(self.root/'out/status.json')['state'], 'FAIL')

    def test_duplicate_json_and_conflicting_pins(self):
        p = self.root/'duplicate.json'
        p.write_text('{"state":"FAIL","state":"PASS"}')
        with self.assertRaises(ValueError):
            runner.read_json(p)
        with self.assertRaises(ValueError):
            runner.merge_pins({'x': '1'*64}, {'x': '2'*64})


if __name__ == '__main__':
    unittest.main()
