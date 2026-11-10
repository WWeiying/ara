#!/usr/bin/env python3
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run


def fixture():
    lines = []
    for i in range(1, 37):
        for cache in ('WT', 'WB'):
            defect = int(i <= (11 if cache == 'WT' else 12))
            lines.append(f'DIRTY_CASE cache={cache} id={i} name=case{i} ack=00 old={defect} fixed=0 '
                         f'flags_write=0 flags=00 reproduced={defect}')
    return '\n'.join(lines) + '\n' + (
        'COMMIT_DIRTY_PASS configurations=2 checks=72 original_failures=23 fixed_failures=0 non_dirty_equal=72\n')


class Contract(unittest.TestCase):
    def test_complete_log(self):
        self.assertEqual(run.check_log(fixture())['original_failures'], 23)

    def test_missing_case(self):
        with self.assertRaises(ValueError):
            run.check_log(fixture().split('\n', 1)[1])

    def test_duplicate_case(self):
        with self.assertRaises(ValueError):
            run.check_log(fixture().replace('id=2 ', 'id=1 '))

    def test_unexpected_native_change(self):
        with self.assertRaises(ValueError):
            run.check_log(fixture().replace('id=13 name=case13 ack=00 old=0',
                                           'id=13 name=case13 ack=00 old=1'))

    def test_no_original_reproduction(self):
        with self.assertRaises(ValueError):
            run.check_log(fixture().replace('old=1', 'old=0', 1))

    def test_fatal_after_marker(self):
        with self.assertRaises(ValueError):
            run.check_log(fixture() + '\nFatal: checker failed\n')

    def test_duplicate_completion(self):
        with self.assertRaises(ValueError):
            run.check_log(fixture() + fixture().splitlines()[-1])

    def test_candidate_only_accel_term(self):
        before = (run.SOC / 'source' / run.TARGET).read_bytes()
        after = run.candidate_bytes(before)
        self.assertEqual(before[:before.index(b'  always_comb begin : dirty_fp_state')],
                         after[:after.index(b'  always_comb begin : dirty_fp_state')])
        self.assertEqual(before[before.index(b'  assign commit_tran_id_o'):],
                         after[after.index(b'  assign commit_tran_id_o'):])
        native_end = before.index(b'      ))) |')
        self.assertEqual(before[:native_end], after[:native_end])
        self.assertIn(b'commit_ack_o[i] && !commit_drop_i[i] && !commit_instr_i[i].ex.valid', after)
        with self.assertRaises(ValueError):
            run.candidate_bytes(before + b'\n')

    def test_patch_hash(self):
        self.assertEqual(run.sha(run.HERE / 'accel_dirty_retirement.patch'), run.PATCH_SHA)

    def test_patch_private_copy_and_reject_reapply(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(['git', 'init', '--quiet', str(root)], check=True, capture_output=True)
            destination = root / 'snapshot' / run.TARGET
            destination.parent.mkdir(parents=True)
            before = (run.SOC / 'source' / run.TARGET).read_bytes()
            destination.write_bytes(before)
            with patch.object(run, 'OUT', root):
                result = run.apply_to_snapshot(root / 'snapshot')
                self.assertEqual(result['before_sha256'], run.BEFORE)
                self.assertEqual(destination.read_bytes(), run.candidate_bytes(before))
                self.assertEqual(result['after_sha256'], hashlib.sha256(destination.read_bytes()).hexdigest())
                with self.assertRaises(ValueError):
                    run.apply_to_snapshot(root / 'snapshot')

    def test_reject_shared_and_original_target(self):
        for root in (run.ROOT, run.SOC / 'source'):
            with self.assertRaises(ValueError):
                run.apply_to_snapshot(root)

    def test_static_tb_coverage(self):
        text = (run.HERE / 'commit_dirty_tb.sv').read_text()
        names = re.findall(r'check_case\("(\w+)"', text)
        self.assertEqual(len(names), 36)
        self.assertEqual(len(set(names)), 36)
        calls = re.findall(r'check_case\("\w+", ([^\n]+)\);', text)
        self.assertEqual(sum(len(args.split(',')) == 5 and args.split(',')[-1].strip() == '1'
                             for args in calls), 11)
        for name in ('illegal_fs_off', 'exception_drop_ack_not_retire',
                     'flush_with_real_retire', 'native_two_port_flags_union',
                     'port1_native_exception', 'native_fp_drop_unchanged'):
            self.assertIn(name, names)
        self.assertIn('a !== b', text)
        self.assertIn('configuration(0)', text)
        self.assertIn('configuration(1)', text)
        self.assertIn('wb_bug = old_bug || name == "flush_cache_contract"', text)


if __name__ == '__main__':
    unittest.main()
