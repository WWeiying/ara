"""Host-only target-comparator and compact-log mutation tests; never RTL evidence."""
import json
import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import q4_m4_compact as q


def manifest(mode):
    suffix = q.PARENTS[mode][0]
    directory = q.OUT / ('operator_qbs_prepare_20261115_q4_m4_%s_01' % suffix)
    m = json.loads((directory / 'build.json').read_text())
    m.update(mode=mode, golden_checks=q.golden_checks(directory))
    return m


def emit(prefix, values):
    return prefix + ' ' + ' '.join('%s=%s' % item for item in values.items())


def synthetic_log(m):
    native = m['mode'] == 'native'
    lines = []
    if native:
        for seq in range(1, 5):
            p = dict.fromkeys(sorted(q.PERF_FIELDS), 0)
            p.update(seq=seq, m=4, n=32, vlen=1024, lanes=4, success=1,
                busy_cycles=8200, phase_setup_cycles=8, phase_compute_cycles=8192,
                tiles=64, weight_bytes=36864, activation_bytes=9344, useful_pairs=262144,
                pair_capacity=262144, dot_active_cycles=8192, commit_groups=16, payload_bytes=46224)
            lines.append(emit('[QBS_PERF]', p))
    lines.append(emit('OPQ_META', dict(id=m['build_id'], m=4, n=64, k=2048, profile=1,
                                      rvv=int(not native), trials=2)))
    for t in range(2):
        start = 100 + t*100000
        r = dict(trial=t, status=0, commands=2 if native else 0, context=0, eligible=0, coop=0,
                 **{'t%d' % i: start+delta for i, delta in enumerate((0, 100, 200, 300, 40300, 40310))},
                 quant_fcsr=1, fcsr=(m['plan']['flags'] if native else 0) | m['flag_seeds'][t],
                 vcsr=2, vstart=0)
        lines.append(emit('OPQ_TRIAL', r))
        for kind in q.KINDS:
            g = m['golden_checks'][kind]
            lines.append(emit('OPQC_CHECK', dict(trial=t, kind=kind, **g, mismatches=0,
                first=0xffffffff, actual_hash=g['expected_hash'], raw_differences=0,
                first_actual=0, first_expected=0)))
        if m.get('power_records') == 2:
            lines.append(emit('OPQC_POWER', dict(trial=t, count=256, finite=256,
                mismatches=0, first=0xffffffff, max_abs_bits=0, max_ratio_bits=0)))
    return '\n'.join(lines + ['OPQ_DONE errors=0', 'Core Test *** SUCCESS *** (tohost = 0)']) + '\n'


def changed(text, prefix, field, value, occurrence=0):
    lines = text.splitlines()
    matches = [i for i, line in enumerate(lines) if line.startswith(prefix + ' ')]
    i = matches[occurrence]
    values = dict(pair.split('=') for pair in lines[i].split()[1:])
    if value is None:
        values.pop(field)
    else:
        values[field] = value
    lines[i] = emit(prefix, values)
    return '\n'.join(lines) + '\n'


class CompactTest(unittest.TestCase):
    def test_records_both_paths(self):
        for mode in q.PARENTS:
            m = manifest(mode)
            text = synthetic_log(m)
            self.assertLess(len(text), 12000)
            r = q.parse_log(text, m)
            self.assertEqual(r['output_values_checked'], 512)
            self.assertTrue(r['exhaustive_target_comparisons'])
            self.assertFalse(r['hash_only_validation'])
            self.assertFalse(r['original_worker_reclassified'])

    def test_comparison_corruption(self):
        for mode in q.PARENTS:
            m = manifest(mode)
            text = synthetic_log(m)
            for record in range(8):
                for field, value in (('count', 0), ('mismatches', 1), ('first', 255),
                                     ('expected_hash', 0), ('first_actual', 1), ('first_expected', 1),
                                     ('actual_hash', 0), ('raw_differences', 99999), ('mismatches', None)):
                    with self.subTest(mode=mode, record=record, field=field), self.assertRaises(ValueError):
                        q.parse_log(changed(text, 'OPQC_CHECK', field, value, record), m)
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if line.startswith(('OPQ_', 'OPQC_')):
                    with self.subTest(missing=line[:40]), self.assertRaises(ValueError):
                        q.parse_log('\n'.join(lines[:i]+lines[i+1:]), m)

    def test_flags_status_times_perf(self):
        for mode in q.PARENTS:
            m = manifest(mode)
            text = synthetic_log(m)
            for t in range(2):
                for field, value in (('fcsr', 16), ('fcsr', 0), ('quant_fcsr', 8),
                        ('vcsr', 0), ('vcsr', 3), ('vstart', 1), ('status', 1),
                        ('commands', 9), ('context', 1), ('eligible', 1), ('t4', 0)):
                    if field == 'fcsr' and value == 0 and mode == 'rvv' and t == 0:
                        continue
                    with self.subTest(mode=mode, trial=t, field=field, value=value), self.assertRaises(ValueError):
                        q.parse_log(changed(text, 'OPQ_TRIAL', field, value, t), m)
            for extra in ('\nTIMEOUT', '\nError: bad', '\nUVM_FATAL : 1',
                          '\nOPQ_DONE errors=0', '\nOPQ_Q8 trial=0 block=0 hex=00', '\n' + text):
                with self.subTest(extra=extra[:30]), self.assertRaises(ValueError):
                    q.parse_log(text+extra, m)
            with self.assertRaises(ValueError):
                q.parse_log(text.replace('tohost = 0', 'tohost = 1'), m)
            with self.assertRaises(ValueError):
                q.parse_log(text.replace('Core Test *** SUCCESS *** (tohost = 0)', ''), m)
            if mode == 'native':
                for field, value in (('seq', 7), ('fault', 1), ('phase_compute_cycles', 1),
                        ('weight_bytes', 1), ('activation_access', 1), ('pair_capacity', 1),
                        ('dot_active_cycles', 1), ('busy_cycles', 0), ('probe_fp_slot_blocked_cycles', None)):
                    with self.subTest(perf=field), self.assertRaises(ValueError):
                        q.parse_log(changed(text, '[QBS_PERF]', field, value), m)

    def test_rvv_tolerant_summary_is_not_hash_only(self):
        m = manifest('rvv')
        text = synthetic_log(m)
        text = changed(text, 'OPQC_CHECK', 'raw_differences', 1, 3)
        text = changed(text, 'OPQC_CHECK', 'actual_hash', 0, 3)
        self.assertEqual(q.parse_log(text, m)['state'], 'PASS')
        with self.assertRaises(ValueError):
            q.parse_log(changed(text, 'OPQC_CHECK', 'mismatches', 1, 3), m)

    def test_source_and_layout_identity(self):
        original = (q.QBS / 'main.c').read_text()
        compact = q.compact_main(original)
        self.assertEqual(q.trial_source(compact).encode(), q.trial_source(original).encode())
        self.assertEqual(compact[compact.index('int main(void)'):compact.index('  printf("OPQ_META')],
                         original[original.index('int main(void)'):original.index('  printf("OPQ_META')])
        self.assertNotIn('OPQ_PACK trial=', compact)
        self.assertIn('format_compare(actual[j], expected[j], count[j]', compact)
        a, b = manifest('native'), manifest('rvv')
        self.assertEqual(a['golden_checks'], b['golden_checks'])

    def test_shared_c_comparator_exhaustive(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / 'compare-test'
            proc = subprocess.run(['/usr/bin/gcc', '-std=c11', '-O2', '-fno-fast-math',
                '-ffp-contract=off', '-I'+str(q.COMPARE), str(q.COMPARE/'compare_test.c'),
                '-lm', '-o', str(exe)], capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            proc = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout+proc.stderr)
            self.assertIn('256 output mutations', proc.stdout)

    def test_scoped_power_eligibility_keeps_strict_failure(self):
        for mode in q.PARENTS:
            m = manifest(mode)
            m.update(power_records=2, eval_trial_object_bytes_identical=True, softdiv_used=False,
                     hot_path_entries={
                         'eval_trial': dict(pc=0x80000000, insn=0x13, expected_calls=2),
                         'quantize_row_q8_K': dict(pc=0x80000010, insn=0x13, expected_calls=8),
                         'matmul': dict(pc=0x80000020, insn=0x13, expected_calls=4)})
            text = synthetic_log(m)
            for field, value in (('mismatches', 1), ('raw_differences', 1), ('first', 7),
                                 ('first_actual', 42), ('first_expected', 43), ('actual_hash', 0)):
                text = changed(text, 'OPQC_CHECK', field, value, 1)
            text = text.replace('OPQ_DONE errors=0', 'OPQ_DONE errors=1').replace(
                'Core Test *** SUCCESS *** (tohost = 0)', 'Core Test *** FAILED *** (tohost = 1)')
            with self.assertRaises(ValueError):
                q.parse_log(text, m)
            with tempfile.TemporaryDirectory() as tmp:
                commit = Path(tmp)/'commit.csv'
                rows = []
                for entry in m['hot_path_entries'].values():
                    rows += [dict(event='retire', pc=format(entry['pc'], 'x'), insn=format(entry['insn'], 'x'), trap=0)
                             for _ in range(entry['expected_calls'])]
                rows += [dict(event='retire', pc='80000030', insn='c0002073', trap=0) for _ in range(4)]

                def write_rows():
                    with commit.open('w', newline='') as stream:
                        writer = csv.DictWriter(stream, fieldnames=('cycle','event','order','pc','insn','trap'))
                        writer.writeheader()
                        for i, row in enumerate(rows):
                            writer.writerow(dict(cycle=i+1, order=i, **row))

                write_rows()
                result = q.eligibility(text, m, commit)
                self.assertEqual(result['state'], 'POWER_ELIGIBLE')
                self.assertEqual(result['strict_numerical_state'], 'FAIL')
                self.assertFalse(result['original_numerical_result_reclassified'])
                self.assertTrue(result['execution_path_checked'])
                for prefix, field, value in (
                    ('OPQC_POWER', 'finite', 255), ('OPQC_POWER', 'mismatches', 1),
                    ('OPQC_POWER', 'max_ratio_bits', 1073741824),
                    ('OPQC_POWER', 'max_abs_bits', 2139095040),
                    ('OPQ_TRIAL', 'vcsr', 0), ('OPQ_TRIAL', 'quant_fcsr', 8),
                    ('OPQ_DONE', 'errors', 0), ('OPQC_CHECK', 'mismatches', 1)):
                    with self.subTest(mode=mode, prefix=prefix, field=field), self.assertRaises(ValueError):
                        q.eligibility(changed(text, prefix, field, value), m, commit)
                rows[0]['trap'] = 1
                write_rows()
                with self.assertRaises(ValueError):
                    q.eligibility(text, m, commit)
                rows[0]['trap'] = 0
                rows.pop(0)
                write_rows()
                with self.assertRaises(ValueError):
                    q.eligibility(text, m, commit)

    def test_built_firmware_and_cli(self):
        paths = [q.OUT / ('power_q4_m4_compact_20261117_%s_02' % mode) for mode in q.PARENTS]
        if not all((path/'build.json').exists() for path in paths):
            self.skipTest('Both firmwares not built yet')
        reports = []
        for path in paths:
            m = q.receipt(path)
            reports.append(m)
            self.assertEqual(q.elf_check(path/'operator.elf'), m['load_segments'])
            self.assertFalse(m['softdiv_used'])
            self.assertTrue(m['eval_trial_object_bytes_identical'])
            self.assertEqual(q.object_section(path/'main.o', '.text.eval_trial'),
                             q.object_section(Path(m['parent']['path'])/'main.o', '.text.eval_trial'))
            with tempfile.TemporaryDirectory() as tmp:
                log, output = Path(tmp)/'synthetic.log', Path(tmp)/'result.json'
                log.write_text(synthetic_log(m))
                proc = subprocess.run([sys.executable, '-B', str(q.HERE/'q4_m4_compact.py'), 'check',
                    '--build', str(path), '--log', str(log), '--output', str(output)],
                    capture_output=True, text=True, timeout=120)
                self.assertEqual(proc.returncode, 0, proc.stdout+proc.stderr)
                self.assertEqual(json.loads(output.read_text())['state'], 'PASS')
                commit, power = Path(tmp)/'commit.csv', Path(tmp)/'power.json'
                with commit.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=('cycle','event','order','pc','insn','trap'))
                    writer.writeheader()
                    instructions = [(e['pc'], e['insn']) for e in m['hot_path_entries'].values()
                                    for _ in range(e['expected_calls'])] + [(0x80000030, 0xc0002073)]*4
                    for i, (pc, word) in enumerate(instructions):
                        writer.writerow(dict(cycle=i+1, event='retire', order=i,
                                             pc=format(pc, 'x'), insn=format(word, 'x'), trap=0))
                proc = subprocess.run([sys.executable, '-B', str(q.HERE/'q4_m4_compact.py'), 'eligibility',
                    '--build', str(path), '--log', str(log), '--commit', str(commit), '--output', str(power)],
                    capture_output=True, text=True, timeout=120)
                self.assertEqual(proc.returncode, 0, proc.stdout+proc.stderr)
                self.assertEqual(json.loads(power.read_text())['state'], 'POWER_ELIGIBLE')
        self.assertEqual(reports[0]['data_identity'], reports[1]['data_identity'])


if __name__ == '__main__':
    unittest.main()
