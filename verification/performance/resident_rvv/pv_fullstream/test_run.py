#!/usr/bin/env python3
"""Host-only frozen mapping, minimal-diff, and fail-closed ledger tests."""
import copy
from pathlib import Path
import tempfile
import unittest

import run


def line(prefix, row):
    return prefix+' '+' '.join(f'{k}={v}' for k, v in row.items())+'\n'


def fixture(expected, guard=False):
    original = run.module(run.context_inputs()/'test_run.py')
    text = original.fixture(expected)
    if guard:
        lines = []
        for raw in text.splitlines():
            if raw.startswith('PV_CONTEXT_TIME id=1 '):
                continue
            if raw.startswith('PV_CONTEXT_TIME id=0 '):
                for old, new in (('first_write=8', 'first_write=30'), ('last_write=9', 'last_write=31'),
                                 ('last_ack=10', 'last_ack=32'), ('cluster_done=11', 'cluster_done=33'),
                                 ('drain=12', 'drain=34')):
                    raw = raw.replace(old, new)
            lines.append(raw)
        text = '\n'.join(lines)+'\n'
    for cid in range(expected['cases']):
        writes = sum(r['writes'] for r in expected['lanes'] if r['id'] == cid)
        row = dict(id=cid, guard=cid+1 if guard else 0, words=96, cmdpops=4, sentinels=4,
                   latency=100, source_first=2, import_done=6, reader_done=5, last_fp=7,
                   last_ack=10, transaction_done=11, final_drain=12, first_write=8,
                   gap_start=0, gap_cycles=0, tail_release=0, cancel_cycle=0,
                   cancel_terminal=0, cancel_wait=0, writes=writes, error=0,
                   credit_stalls=1, skew=1, coefficient_stalls=1)
        if guard and cid == 0:
            row.update(import_done=29, last_ack=32, transaction_done=33, final_drain=34,
                       first_write=30, gap_start=8, gap_cycles=12, tail_release=20)
        if guard and cid == 1:
            row.update(import_done=49, last_ack=0, transaction_done=50, final_drain=51,
                       first_write=0, gap_start=8, gap_cycles=12, tail_release=40, cancel_cycle=20,
                       cancel_terminal=24, cancel_wait=16, writes=0, error=1)
        text += line('PV_FULLSTREAM_CASE', row)
        if guard:
            for lane in range(4):
                text += line('PV_RETURN_STALL', dict(id=cid, lane=lane, cycles=2))
    return text


class FullstreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context, cls.helper, cls.importer = run.helpers()
        cls.expected, cls.guard_files = run.expected_bundle(run.context_inputs(), cls.context, cls.helper)
        cls.normal = cls.expected['normal']
        cls.guard = cls.expected['guard']

    def test_counts_exactly_66_plus_3(self):
        self.assertEqual((self.normal['cases'], self.guard['cases']), (66, 3))
        self.assertEqual(sum(r['issued'] for r in self.normal['lanes']), 36976)
        self.assertEqual(sum(r['writes'] for r in self.normal['lanes']), 2544)
        self.assertEqual(sum(r['issued'] for r in self.guard['lanes']), 1728)
        self.assertEqual(sum(r['writes'] for r in self.guard['lanes']), 128)
        self.assertEqual([r['source'] for r in self.normal['mapping'] if r['no_stalls']], [0, 1, 2])

    def test_normal_bodies_and_mapping_unchanged(self):
        expected, files = self.context.selection(run.context_inputs()/'upstream', self.helper)
        self.assertEqual(expected, self.normal)
        for name, content in files.items():
            self.assertEqual(content, (run.context_inputs()/name).read_text())

    def test_guard_exact_original_bodies_only_id_remapped(self):
        generator = run.module(run.context_inputs()/'upstream/corpus.py')
        import json
        records = generator.records((generator.BASE/'vectors/vectors.txt').read_text(),
            json.loads((generator.BASE/'vectors/vectors.json').read_text())['cases_by_id'])
        for lane in range(4):
            lines = iter(self.guard_files[f'lane{lane}.txt'].splitlines())
            self.assertEqual(next(lines), '50565531 3')
            for cid in range(3):
                original = records[self.normal['mapping'][2]['names'][lane]]
                header = original['header'][:]
                header[0] = str(cid)
                self.assertEqual(next(lines), ' '.join(header))
                self.assertEqual([next(lines) for _ in original['body']], original['body'])
            self.assertIsNone(next(lines, None))
        self.assertEqual(len(set(self.guard['mapping'][0]['names'])), 4)

    def test_guard_only_architectural_cancel_expectations_differ(self):
        for row in self.guard['lanes']:
            original = next(r for r in self.normal['lanes'] if r['id'] == 2 and r['lane'] == row['lane'])
            wanted = dict(original, id=row['id'])
            if row['id'] == 1:
                wanted.update(writes=0, acks=0)
            self.assertEqual(row, wanted)
        self.assertEqual(self.guard['groups'][1], dict(id=1, flags=0))

    def test_minimal_cluster_diff_and_mutations(self):
        original = (run.context_inputs()/'upstream/akv_resident_pv_cluster.sv').read_text()
        candidate = (run.HERE/'akv_resident_pv_cluster.sv').read_text()
        run.check_cluster(original, candidate)
        for bad in (original, candidate.replace(' || commit_authorized_o', ''),
                    candidate.replace('lane_result_valid &', 'lane_result_ready &'),
                    candidate+'\n// unrelated change\n'):
            with self.assertRaises(ValueError):
                run.check_cluster(original, bad)

    def test_queue_command_and_electrical_guard_contract(self):
        source = (run.HERE/'source_harness.svh').read_text()
        tb = (run.HERE/'tb.sv').read_text()
        self.importer.check_command_contract((run.import_inputs()/self.importer.CONTRACTS[0]).read_text(), source)
        for fragment in ('source_sent[l]<18', '.DataBufDepth(2)', '.AccessCmdPop(1)',
                         '.FPUSupport(FPUSupportNone)', 'import_done && !import_error && reader_complete_q && !reader_failed_q',
                         'clock_cycle-cancel_terminal_start>=12',
                         'import_done_ready = done_valid_o && done_ready_i',
                         '.cancel_i(abort_i)', '.flush_i(1\'b0)'):
            self.assertIn(fragment, source)
        self.assertIn('&& import_done && reader_complete_q && reader_retired;', tb)
        self.assertNotIn('seed_valid_i[l]=', tb)
        self.assertNotIn('coefficient=coefficients', tb)
        self.assertNotIn('force ', source+tb)

    def test_independent_coefficient_pair_permutation(self):
        # Populate by the accepted natural halfslot table, recover by a separate
        # explicit pair routing table. Both heads remain raw, including H1 padding.
        offsets = (0, 8, 4, 12)
        pairs = [((i*73+0x7c01)&65535) | (((i*89+0xfc00)&65535)<<16) for i in range(64)]
        for group in range(8):
            physical = [[0]*4 for _ in range(4)]
            for lane in range(4):
                for slot, offset in enumerate(offsets):
                    index = 16*group+lane+offset
                    physical[lane][slot] = (pairs[index//2] >> (16*(index%2)))&65535
            for token, (a, b) in enumerate(((0, 1), (2, 3), (0, 1), (2, 3),
                                             (0, 1), (2, 3), (0, 1), (2, 3))):
                slot = (0, 0, 2, 2, 1, 1, 3, 3)[token]
                self.assertEqual(physical[a][slot] | (physical[b][slot]<<16), pairs[group*8+token])

    def test_complete_normal_and_guard_checkers(self):
        for guard in (False, True):
            expected = self.guard if guard else self.normal
            result = run.check_log(fixture(expected, guard), expected, self.context, self.helper, guard)
            self.assertEqual(len(result['source']), expected['cases'])
            self.assertEqual(len(result['owners']), 4)
            self.assertEqual(len(result['real_no_injected_stall_intervals']), 0 if guard else 3)

    def test_source_count_timing_and_reader_barrier_mutations(self):
        text = fixture(self.normal)
        mutations = (('words=96', 'words=95'), ('cmdpops=4', 'cmdpops=3'),
            ('sentinels=4', 'sentinels=3'), ('latency=100', 'latency=99'),
            ('source_first=2', 'source_first=7'), ('import_done=6', 'import_done=8'),
            ('reader_done=5 last_fp=7', 'reader_done=8 last_fp=7'),
            ('transaction_done=11', 'transaction_done=6'), ('error=0', 'error=1'))
        for old, new in mutations:
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(ValueError):
                run.check_log(text.replace(old, new, 1), self.normal, self.context, self.helper)

    def test_cancel_still_delays_tail_after_error_terminal(self):
        text = fixture(self.guard, True)
        for old, new in (('cancel_wait=16', 'cancel_wait=0'), ('cancel_wait=16', 'cancel_wait=11'),
                         ('tail_release=40', 'tail_release=20'), ('tail_release=40', 'tail_release=30'),
                         ('cancel_terminal=24', 'cancel_terminal=20'), ('error=1', 'error=0'),
                         ('first_write=0', 'first_write=25'), ('gap_cycles=12', 'gap_cycles=11')):
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(ValueError):
                run.check_log(text.replace(old, new, 1), self.guard, self.context, self.helper, True)

    def test_original_numerical_and_native_checkers_fail_closed(self):
        text = fixture(self.guard, True)
        first = line('PV_RETURN_STALL', dict(id=0, lane=0, cycles=2))
        for bad in (text.replace(first, '', 1), text+first,
                    text.replace(first, first.replace('cycles=2', 'cycles=0'), 1)):
            with self.assertRaises(ValueError):
                run.check_log(bad, self.guard, self.context, self.helper, True)
        text = fixture(self.normal)
        for old, new in (('native_done=330', 'native_done=329'), ('returned=1024', 'returned=1023'),
                         ('flags=3', 'flags=2'), ('reset_owned=0', 'reset_owned=1'),
                         ('private_cancelled=0', 'private_cancelled=1')):
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(ValueError):
                run.check_log(text.replace(old, new, 1), self.normal, self.context, self.helper)
        with self.assertRaises(ValueError):
            run.check_log(text+'Fatal: injected\n', self.normal, self.context, self.helper)

    def test_missing_duplicate_source_receipts(self):
        text = fixture(self.normal)
        first = next(x for x in text.splitlines(True) if x.startswith('PV_FULLSTREAM_CASE'))
        for bad in (text.replace(first, '', 1), text+first, text.replace('cmdpops=4', 'cmdpops=4 cmdpops=4', 1)):
            with self.assertRaises(ValueError):
                run.check_log(bad, self.normal, self.context, self.helper)

    def test_service_logs_excluded_and_pin_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'service.log').write_text('changing')
            (out/'stdout.json').write_text('changing')
            (out/'expected.json').write_text('{}')
            self.assertEqual(set(run.artifact_pins(out, self.helper)), {str(out/'expected.json')})
        with self.assertRaises(ValueError):
            self.context.merge({'README.md': 'a'}, {'README.md': 'b'})

    def test_guard_bad_selection_rejected(self):
        bad = copy.deepcopy(self.normal)
        bad['mapping'][2]['tokens'] = 64
        with self.assertRaises(ValueError):
            run.guard_selection(run.context_inputs(), bad, self.helper)


if __name__ == '__main__':
    unittest.main()
