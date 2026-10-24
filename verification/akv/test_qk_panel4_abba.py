"""Host-only synthetic failure tests; never launch a simulator."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_qk_panel4_abba as runner


def metric(tag, row):
    return tag + ' ' + ' '.join(f'{k}={v}' for k, v in row.items())


def fixture():
    lines, rows = [], []
    for trial, panel in enumerate((0, 1, 1, 0)):
        lines.append(f'AKV_QK_TRIAL_BEGIN trial={trial} panel4={panel}')
        schedule = []
        for _head in range(2):
            for tile in range(2):
                schedule += [4 if tile == 0 else 5]
                schedule += [6] * (32 if panel else 128)
                schedule += [2] * 64
            schedule += [3]
        for cmd in schedule:
            row = dict.fromkeys(runner.PERF_FIELDS, 0)
            row.update(seq=len(rows)+1, id=0, command=cmd, success=1,
                       context_ready=int(cmd != 3), busy_cycles=10)
            if cmd in (4, 5):
                row.update(v2_full=int(cmd == 4), v2_refill=int(cmd == 5),
                    q_external_bytes=1536 if cmd == 4 else 0, kv_external_bytes=32768,
                    read_ranges=135 if cmd == 4 else 128,
                    read_payload_bytes=34368 if cmd == 4 else 32768,
                    ar=140, r_beats=2100, read_outstanding_max=2,
                    read_outstanding_occ_sum=60, read_outstanding_full_cycles=20)
            elif cmd == 2:
                row.update(load=1, v2_row_load=1, replay_bytes=256)
            elif cmd == 3:
                row.update(release=1)
            else:
                row.update(v2_column_load=1, v2_column_panel=panel,
                           v2_logical_column=4 if panel else 1,
                           v2_k_view_bank_cycles=8, replay_bytes=512 if panel else 128)
            rows.append(row)
            lines.append(metric('[AKV_PERF]', row))
        lines.append(f'AKV_QK_ATTENTION trial={trial} panel4={panel} native=1 kv=128 outputs=1536 '
                     f'cycles={100000-trial*100} fcsr=3 vcsr=5 checksum=a7bc111334389dea errors=0')
    lines += [runner.SUITE, runner.TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0']
    summary = {k: sum(r[k] for r in rows) for k in runner.COUNTERS}
    summary['read_outstanding_max'] = 2
    summary.update(records=2328, success_records=2328, fault_records=0, validation_fault_records=0)
    lines.append(metric('[AKV_PERF_SUMMARY]', summary))
    return '\n'.join(lines)+'\n'


class LogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = fixture()
        cls.first = next(x for x in cls.text.splitlines() if x.startswith('[AKV_PERF] '))

    def test_complete(self):
        r = runner.check_log(self.text)
        self.assertEqual(r['state'], 'PASS')
        self.assertEqual([t['derived_hardware_totals']['records'] for t in r['trials']], [774, 390, 390, 774])
        self.assertEqual(r['raw_hardware_summary']['read_outstanding_max'], 2)
        self.assertEqual(r['raw_hardware_summary']['v2_logical_column'], 2048)
        self.assertEqual(r['raw_hardware_summary']['v2_k_view_bank_cycles'], 10240)
        self.assertEqual(r['raw_hardware_summary']['read_payload_bytes'], 537088)
        self.assertEqual(r['sums'], {'0': 199700, '1': 199700})

    def test_prefixes_missing_extra_unknown(self):
        bad = [self.text.replace(self.first+'\n', '', 1), self.text+self.first+'\n',
               self.text.replace(self.first, self.first+' unknown=1', 1),
               self.text.replace(self.first, self.first+' seq=1', 1),
               self.text.replace(self.first, self.first.replace(' id=0', ''), 1)]
        for marker in ('[AKV_PERF]', '[AKV_PERF_SUMMARY]', 'AKV_QK_TRIAL_BEGIN',
                       'AKV_QK_ATTENTION', 'AKV_QK_ABBA_PASS'):
            bad += [self.text.replace(marker, marker+'_BOGUS', 1),
                    self.text.replace(marker, 'embedded '+marker, 1),
                    self.text+'\n'+marker+'_UNKNOWN x=1\n']
        for i, text in enumerate(bad):
            with self.subTest(i=i), self.assertRaises(ValueError):
                runner.check_log(text)

    def test_work_flags_guards_order_terminal(self):
        replacements = [('command=4', 'command=5'), ('seq=1 ', 'seq=2 '),
            ('success=1', 'success=0'), ('fault=0', 'fault=1'), ('context_ready=1', 'context_ready=0'),
            ('q_external_bytes=1536', 'q_external_bytes=1535'), ('v2_k_view_bank_cycles=8', 'v2_k_view_bank_cycles=7'),
            ('v2_column_panel=1', 'v2_column_panel=0'), ('v2_logical_column=4', 'v2_logical_column=1'),
            ('replay_bytes=512', 'replay_bytes=128'), ('busy_cycles=10', 'busy_cycles=x'),
            ('panel4=0', 'panel4=1'), ('fcsr=3', 'fcsr=1'), ('vcsr=5', 'vcsr=0'),
            ('checksum=a7bc111334389dea', 'checksum=0000000000000000'), ('errors=0', 'errors=1'),
            ('guards=1', 'guards=0'), ('bytewise_equal=1', 'bytewise_equal=0'),
            (runner.TERMINAL, runner.TERMINAL+'_BOGUS'), (runner.TERMINAL, ''),
            ('UVM_ERROR : 0', 'UVM_ERROR : 1'), ('UVM_FATAL : 0', 'UVM_FATAL : 1')]
        for old, new in replacements:
            with self.subTest(old=old), self.assertRaises(ValueError):
                runner.check_log(self.text.replace(old, new, 1))
        for extra in (runner.SUITE, runner.TERMINAL, 'UVM_ERROR : 0',
                      'UVM_ERROR @ 1: mismatch', '[QBS_PERF] seq=1', 'Fatal: failed'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                runner.check_log(self.text+extra+'\n')

    def test_summary_and_equal_traffic(self):
        lines = self.text.splitlines()
        for key in runner.SUMMARY_FIELDS:
            row = runner.numeric_fields(lines[-1].split(' ', 1)[1], runner.SUMMARY_FIELDS)
            row[key] += 1
            with self.subTest(summary=key), self.assertRaises(ValueError):
                runner.check_log('\n'.join(lines[:-1]+[metric('[AKV_PERF_SUMMARY]', row)]))
        # Preserve raw-summary conservation while changing only one trial's AR.
        changed = list(lines)
        changed[1] = changed[1].replace(' ar=140 ', ' ar=141 ')
        row = runner.numeric_fields(changed[-1].split(' ', 1)[1], runner.SUMMARY_FIELDS)
        row['ar'] += 1
        changed[-1] = metric('[AKV_PERF_SUMMARY]', row)
        with self.assertRaisesRegex(ValueError, 'traffic changed'):
            runner.check_log('\n'.join(changed))
        # Correct per-command shape is mandatory even if aggregate fields agree.
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

    def test_build_actual_schema_and_drift(self):
        elf = self.root/'test.elf'
        elf.write_bytes(b'test')
        manifest = self.write('manifest.json', {})
        artifacts = self.write('artifacts.json', runner.hashes([elf]))
        report = dict(state='BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=runner.digest(elf),
            manifest_sha256=runner.digest(manifest), artifacts_sha256=runner.digest(artifacts),
            effective_kv=128, outputs=1536, head_dim=128, q_heads=12, kv_heads=2, refill_overlap=False)
        self.write('build.json', report)
        self.assertEqual(runner.checked_build(self.root)[0], report)
        for key, value in [('state', 'READY'), ('refill_overlap', True), ('q_heads', 6),
                           ('manifest_sha256', '0'*64), ('artifacts_sha256', '0'*64)]:
            bad = dict(report, **{key: value})
            self.write('build.json', bad)
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.checked_build(self.root)
        self.write('build.json', report)
        elf.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            runner.checked_build(self.root)

    def test_prerequisite_terminal_and_provenance(self):
        artifact = self.root/'focused-source.c'
        artifact.write_text('sealed')
        pins = runner.hashes([artifact])
        before = self.write('pins-before.json', pins)
        after = self.write('pins-after.json', pins)
        image = {'/image/simv': '1'*64}
        result = dict(state='PASS', numeric=dict(state='PASS', pairs=8, runs=16, outputs=3240, tailwords=2904),
                      sim_image_sha256=image, evidence_sha256=runner.hashes([before, after]))
        self.write('status.json', dict(state='PASS', child_pid=None))
        self.write('result.json', result)
        runner.checked_prerequisite(self.root, image)
        for state in ('RUNNING', 'FAIL', 'CHECKED_PENDING_PINS'):
            self.write('status.json', dict(state=state, child_pid=123))
            with self.subTest(state=state), self.assertRaises(ValueError):
                runner.checked_prerequisite(self.root, image)
        self.write('status.json', dict(state='PASS', child_pid=None))
        bad = copy.deepcopy(result)
        bad['numeric']['outputs'] = 1
        self.write('result.json', bad)
        with self.assertRaises(ValueError):
            runner.checked_prerequisite(self.root, image)
        self.write('result.json', result)
        with self.assertRaises(ValueError):
            runner.checked_prerequisite(self.root, {'/image/simv': '2'*64})
        artifact.write_text('drift')
        with self.assertRaises(ValueError):
            runner.checked_prerequisite(self.root, image)

    def test_new_acceptance_not_old_image_status(self):
        simv = self.root/'simv'
        simv.write_bytes(b'image')
        source = self.root/'rtl.sv'
        source.write_text('sealed')
        manifest = self.write('vcs_source_manifest.json', dict(schema_version=1, repo_root=str(runner.ROOT),
            files=[dict(path=str(source), sha256=runner.digest(source))]))
        image = runner.hashes([simv, manifest])
        gate = self.root/'acceptance'
        image_pin = self.write('acceptance/image-pins.json', image)
        self.write('acceptance/status.json', dict(state='PASS', child_pid=None, simv=str(simv)))
        self.write('acceptance/result.json', dict(state='PASS', neighbors=2, probe=dict(state='PASS', commands=13),
                                                evidence_sha256=runner.hashes([image_pin])))
        # Historical build status may be FAIL; only the explicit acceptance is used.
        self.write('status.json', dict(state='FAIL'))
        with patch.object(runner, 'image_files', return_value=[simv, manifest]):
            self.assertEqual(runner.checked_image(gate, simv)[0], image)
            source.write_text('source drift')
            with self.assertRaises(ValueError):
                runner.checked_image(gate, simv)

    def test_duplicate_json_and_conflicting_pins(self):
        p = self.root/'duplicate.json'
        p.write_text('{"state":"FAIL","state":"PASS"}')
        with self.assertRaises(ValueError):
            runner.read_json(p)
        with self.assertRaises(ValueError):
            runner.merge_pins({'x': '1'*64}, {'x': '2'*64})


if __name__ == '__main__':
    unittest.main()
