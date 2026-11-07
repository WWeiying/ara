import csv
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location('chain_current_results', Path(__file__).with_name('current_results.py'))
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


class TestBoundaries(unittest.TestCase):
    def line(self, cycle, fire=0, terminal=0, akv_fire=0, akv_terminal=0):
        return ('[CHAIN_BOUNDARY] cycle=%d insn=00b5045b qbs_fire=%d qbs_terminal=%d '
                'akv_fire=%d akv_terminal=%d\n') % (cycle, fire, terminal, akv_fire, akv_terminal)

    def test_native_busy_is_lifetime_difference(self):
        text = self.line(4, fire=1) + self.line(14, terminal=1)
        self.assertEqual(reporter.boundaries(text, {'qbs': [10]})['qbs'][0]['cycles'], 10)
        with self.assertRaises(ValueError):
            reporter.boundaries(text, {'qbs': [11]})

    def test_incomplete_or_duplicate_work_rejected(self):
        cases = [self.line(4, fire=1), self.line(14, terminal=1),
                 self.line(4, fire=1)+self.line(5, fire=1),
                 self.line(4, fire=1)+self.line(4, terminal=1),
                 self.line(4, fire=1, terminal=1),
                 self.line(4, akv_fire=1)+self.line(5, akv_terminal=1)]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                reporter.boundaries(text, {'qbs': []})

    def test_window_unknown_and_truncation_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name)/'boundary.csv'
            keys = ['cycle', 'insn', 'qbs_busy', 'akv_busy', 'wait_weight', 'tile_start', 'tile_done',
                    'ar_valid', 'ar_ready', 'r_valid', 'r_ready', 'front_valid', 'front_ready']
            def write(count, unknown=False):
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=keys)
                    writer.writeheader()
                    for i in range(count):
                        row = dict.fromkeys(keys, '0')
                        row.update(cycle=15+i, insn='00b5045b', qbs_busy='1', r_valid='1', r_ready='1')
                        if unknown and i == 10: row['qbs_busy'] = 'x'
                        writer.writerow(row)
            write(1000)
            result = reporter.prefix(path)
            self.assertEqual(result['signal_counts']['r_transfer'], 1000)
            write(999)
            with self.assertRaises(ValueError): reporter.prefix(path)
            write(1000, True)
            with self.assertRaises(ValueError): reporter.prefix(path)

    def test_root_wait_transfer_subset_has_a_distinct_name(self):
        text = ''.join('[QBS_ROOT] c=%d wait=1 istart=0 idone=0 bfifo=2 '
                       'ar=1/1 r=1/1 data=1/1\n' % i for i in range(200))
        result = reporter.root_window(text)
        self.assertEqual(result['counts']['r_transfer'], 200)
        self.assertEqual(result['counts']['strict_wait_r_transfer'], 200)
        with self.assertRaises(ValueError): reporter.root_window(text+text)


class TestF16Accounting(unittest.TestCase):
    def fixture(self):
        return dict(scope='unit fixture', complete_calls=4, measured_total_cycles=[90, 100, 100, 90],
                    baseline_mean=90, profile_mean=100, probe_delta_cycles=10, probe_delta_fraction=1/9,
                    empty_interval_median=2,
                    phase=[dict(trial=t, issue_side_cycles=dict(qk=20, pv=30),
                                outside_spans=50, final_drain=10) for t in (1, 2)],
                    work=dict(call_busy_cycles=[30, 30, 30, 30]))

    def test_drain_not_double_counted_and_busy_not_added(self):
        result = reporter.f16_summary(self.fixture())
        self.assertEqual(sum(result['mean_issue_side_partition'].values()), 100)
        self.assertEqual(result['final_drain_mean_cycles'], 10)
        self.assertEqual(result['engine_busy_fraction_per_call'][1], 0.3)

    def test_inconsistent_partition_rejected(self):
        for key, value in (('outside_spans', 60), ('final_drain', 51)):
            data = self.fixture()
            data['phase'][0][key] = value
            with self.assertRaises(ValueError): reporter.f16_summary(data)

    def test_command_envelope_keeps_required_gap_work_separate(self):
        counters = (' ar=0 r_beats=0 read_payload_bytes=0 store_wait_cycles=0 read_backpressure_cycles=0'
                    ' replay_backpressure_cycles=0 v2_k_view_bank_cycles=0 v2_bank_conflict_cycles=0\n')
        text = ''.join('[AKV_PERF] seq=%d command=%d busy_cycles=10' % (i+1, c) + counters
                       for i, c in enumerate((4, 6, 3)))
        events = [dict(fire=i*15, terminal=i*15+10, cycles=10) for i in range(3)]
        row = reporter.f16_engine_work(text, events, calls=1, per_call=3)[0]
        self.assertEqual(row['first_fire_to_last_terminal_cycles'], 40)
        self.assertEqual(sum(row['busy_by_command_cycles'].values()), 30)
        self.assertEqual(row['intercommand_gap_cycles'], 10)
        events[1]['cycles'] += 1
        with self.assertRaises(ValueError): reporter.f16_engine_work(text, events, calls=1, per_call=3)

    def test_failed_receipt_cannot_be_reaudited_as_pass(self):
        with tempfile.TemporaryDirectory() as name:
            import json
            path = Path(name)
            (path/'result.json').write_text(json.dumps(dict(state='FAIL', kind='f16')))
            with self.assertRaises(ValueError): reporter.accepted(path, 'f16')


class TestQ6Accounting(unittest.TestCase):
    def fixture(self):
        keys = ('busy_cycles weight_prefetch_wait_cycles dot_active_cycles tiles useful_pairs pair_capacity '
                'weight_bytes activation_bytes activation_axi_bytes_saved payload_bytes r_beats '
                'probe_compute_without_dot_issue_cycles probe_read_ar_slot_blocked_cycles '
                'probe_read_ar_ready_blocked_cycles probe_read_response_idle_cycles '
                'probe_read_data_sink_blocked_cycles probe_read_translation_wait_cycles '
                'probe_context_start_blocked_cycles probe_fp_input_blocked_cycles '
                'probe_profile_result_blocked_cycles commit_backpressure_cycles').split()
        cmd = dict.fromkeys(keys, 0)
        cmd.update({'phase_'+k+'_cycles': 0 for k in reporter.PHASES})
        cmd.update({'probe_weight_wait_'+k+'_cycles': 0 for k in reporter.WAIT})
        cmd.update(busy_cycles=100, phase_setup_cycles=5, phase_activation_cycles=5,
                   phase_weight_cycles=30, phase_compute_cycles=40, phase_overlap_cycles=20,
                   weight_prefetch_wait_cycles=20, probe_weight_wait_r_transfer_cycles=18,
                   probe_weight_wait_r_blocked_cycles=2, dot_active_cycles=50,
                   probe_compute_without_dot_issue_cycles=10, tiles=2, useful_pairs=1600,
                   pair_capacity=1600, weight_bytes=600, activation_bytes=32,
                   payload_bytes=632, r_beats=40)
        trials = [dict(trial=t, timing=dict(total=300),
                       complete_slice_partition_cycles=dict(preparation=50, plan_admission=10,
                           native_engine_busy=200, sdk_execute_outside_engine=30, final_drain=10),
                       commands=[copy.deepcopy(cmd), copy.deepcopy(cmd)]) for t in range(2)]
        return dict(scope='unit fixture', trials=trials)

    def test_wait_is_subclassification_not_additional_call_phase(self):
        result = reporter.q6_summary(self.fixture())
        self.assertEqual(result['mean_total_cycles'], 300)
        row = result['trials'][0]
        self.assertEqual(sum(row['complete_call_partition'].values()), 300)
        self.assertEqual(row['strict_weight_wait_cycles'], 40)
        self.assertEqual(row['weight_only_ideal_bus_cycles'], 75)

    def test_corrupt_counter_partitions_rejected(self):
        for key in ('probe_weight_wait_no_outstanding_cycles', 'phase_weight_cycles',
                    'probe_compute_without_dot_issue_cycles'):
            data = self.fixture()
            data['trials'][0]['commands'][0][key] += 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                reporter.q6_summary(data)


class TestPublication(unittest.TestCase):
    def test_final_identity_failure_never_publishes_success(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            q6, f16, out = root/'q6', root/'f16', root/'report'
            for folder in (q6, f16):
                folder.mkdir()
                (folder/'result.json').write_text('{}')
            report = dict(image_sha256='same', configuration={}, artifacts={})
            q = dict(mean_complete_call_partition=dict(work=10), mean_total_cycles=10)
            f = dict(mean_issue_side_partition=dict(work=20), profile_mean_cycles=20)
            with mock.patch.object(reporter, 'OUT', root), \
                 mock.patch.object(reporter, 'accepted', return_value=(report, {}, {}, {})), \
                 mock.patch.object(reporter, 'q6_summary', return_value=q), \
                 mock.patch.object(reporter, 'f16_summary', return_value=f), \
                 mock.patch.object(reporter, 'verify', side_effect=ValueError('final pin drift')), \
                 mock.patch.object(sys, 'argv', ['current_results.py', '--q6-run', str(q6),
                                               '--f16-run', str(f16), '--output', str(out)]):
                with self.assertRaisesRegex(ValueError, 'final pin drift'):
                    reporter.main()
            self.assertTrue((out/'call_partition.csv').is_file())
            self.assertFalse((out/'result.json').exists())


class TestOriginalPayloadIntegrity(unittest.TestCase):
    def fixture(self, root):
        build = root/'build'
        data = build/'data'
        data.mkdir(parents=True)
        source = root/'q6_decode/input_integrity.c'
        source.parent.mkdir()
        source.write_text('unit-fixture-source')
        obj, config = build/'input_integrity.o', build/'integrity_config.h'
        obj.write_bytes(b'unit-fixture-object')
        config.write_text('unit-fixture-config')
        pins, payloads, lines = {}, {}, []
        for tag, filename, size, symbol in (
                ('activation', 'input_f32.bin', 8192, 'profile_input'),
                ('weight', 'weights_r4.bin', 107520, 'profile_weights')):
            path = data/filename
            path.write_bytes(bytes(range(256))*(size//256))
            payloads[tag] = dict(path=str(path), bytes=size, symbol=symbol,
                                 expected_hash=reporter.fnv1a64(path.read_bytes()))
            lines.append('CHAIN_Q6_INPUT_INTEGRITY tag=%s bytes=%d expected=%s actual=%s' %
                         (tag, size, payloads[tag]['expected_hash'], payloads[tag]['expected_hash']))
            pins[str(path)] = reporter.digest(path)
        wrapper = {}
        for key, path in (('source', source), ('object', obj), ('config', config)):
            wrapper[key] = str(path)
            wrapper[key+'_sha256'] = pins[str(path)] = reporter.digest(path)
        contract = dict(method='fnv1a64-after-both-timed-calls-v1', entrypoint='main -> q6_profile_body',
                        memory_checked_after_both_calls=True, payloads=payloads, wrapper=wrapper)
        (build/'build.json').write_text(json.dumps(dict(input_integrity=contract)))
        commands = [dict(label='compile-main', argv=['cc', '-Dmain=q6_profile_body', '-c', 'main.c']),
                    dict(label='compile-wrapper', argv=['cc', '-c', str(source), '-o', str(obj)]),
                    dict(label='link', argv=['cc', 'main.o', str(obj)])]
        commandfile = build/'commands.json'
        commandfile.write_text(json.dumps(commands))
        pins[str(commandfile)] = reporter.digest(commandfile)
        lines.append('CHAIN_Q6_INPUT_INTEGRITY_DONE errors=0')
        return build, pins, '\n'.join(lines)+'\n'

    def test_fnv_known_vectors(self):
        self.assertEqual(reporter.fnv1a64(b''), 'cbf29ce484222325')
        self.assertEqual(reporter.fnv1a64(b'hello'), 'a430d84680aabd0b')

    def test_original_payloads_and_exact_entrypoint_are_checked(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            build, pins, text = self.fixture(root)
            with mock.patch.object(reporter, 'HERE', root):
                result = reporter.original_payload_integrity(text, build, pins)
                self.assertEqual(result['bytes_checked'], 115712)
                bad = text.replace('actual=', 'actual=0', 1)
                for modified in (bad, '', text+text, text.replace('errors=0', 'errors=1')):
                    with self.assertRaises(ValueError):
                        reporter.original_payload_integrity(modified, build, pins)

    def test_repinning_bad_payload_or_missing_wrapper_is_not_enough(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            build, pins, text = self.fixture(root)
            path = build/'data/input_f32.bin'
            path.write_bytes(b'x'*8192)
            pins[str(path)] = reporter.digest(path)
            with mock.patch.object(reporter, 'HERE', root), self.assertRaises(ValueError):
                reporter.original_payload_integrity(text, build, pins)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            build, pins, text = self.fixture(root)
            path = build/'commands.json'
            commands = json.loads(path.read_text())
            commands[0]['argv'].remove('-Dmain=q6_profile_body')
            path.write_text(json.dumps(commands))
            pins[str(path)] = reporter.digest(path)
            with mock.patch.object(reporter, 'HERE', root), self.assertRaises(ValueError):
                reporter.original_payload_integrity(text, build, pins)


if __name__ == '__main__':
    unittest.main()
