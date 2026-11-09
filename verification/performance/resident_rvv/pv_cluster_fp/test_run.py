#!/usr/bin/env python3
"""Focused normal-only checker rejection tests; no simulator required."""
import copy
from pathlib import Path
import tempfile
import unittest

import run


def line(prefix, row):
    return prefix+' '+' '.join(f'{k}={v}' for k, v in row.items())+'\n'


def fixture():
    lanes = [dict(id=0, lane=l, seeds=1, packets=2, issued=1, returned=1,
                  writes=1, acks=1, flags=l) for l in range(4)]
    expected = dict(cases=1, lanes=lanes, groups=[dict(id=0, flags=3)])
    text = line('VMFPU_ADAPTER_CONFIG', dict(shared_fma=0, checker_pipe_label=3))*4
    text += ''.join(line('PV_CLUSTER_FP_LANE', r) for r in lanes)
    text += line('PV_CLUSTER_FP_CASE', expected['groups'][0])
    text += ''.join(line('PV_CLUSTER_FP_STALL', dict(lane=l, request=1, write=1)) for l in range(4))
    text += line('PV_CLUSTER_FP_PASS', dict(cases=1, issued=4, writes=4, late=1,
                same=1, excess=1, max16=1, skew=1, done_stall=1, debt_terminal=1))
    owner = dict(native_done=5, acquires=1, releases=1, native_stalls=1, private_stalls=1,
                 native_accepted=5, native_cancelled=0, private_issued=1, private_returned=1,
                 private_cancelled=0, acquire_collisions=1, miter_cycles=1,
                 native_grant_stalls=15, native_flag_events=1, reset_owned=0,
                 native_fma=1, native_mul=1, native_div=1, native_max=1)
    text += line('VMFPU_OWNER_COVERAGE', owner)*4
    return text, expected


class CheckerTests(unittest.TestCase):
    def test_normal_pass_without_reset(self):
        text, expected = fixture()
        self.assertEqual(run.check_log(text, expected, 0)['totals']['issued'], 4)

    def test_reject_corrupt_missing_duplicate_records(self):
        text, expected = fixture()
        mutations = [text.replace('returned=1', 'returned=0', 1),
                     text.replace('acks=1', 'acks=0', 1),
                     text.replace('PV_CLUSTER_FP_CASE id=0 flags=3', 'PV_CLUSTER_FP_CASE id=0 flags=2'),
                     text.replace('native_done=5', 'native_done=4', 1),
                     text.replace('releases=1', 'releases=0', 1),
                     text.replace('reset_owned=0', 'reset_owned=1', 1),
                     text.replace('native_cancelled=0', 'native_cancelled=1', 1),
                     text.replace('private_cancelled=0', 'private_cancelled=1', 1),
                     text.replace('debt_terminal=1', 'debt_terminal=0'),
                     text.replace('write=1', 'write=0', 1),
                     text.replace('shared_fma=0', 'shared_fma=1', 1),
                     text.replace('PV_CLUSTER_FP_CASE id=0 flags=3\n', ''),
                     text + line('PV_CLUSTER_FP_CASE', dict(id=0, flags=3)),
                     text.replace('native_done=5', 'native_done=5 native_done=5', 1),
                     text+'Fatal: checker failed\n']
        for index, mutated in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                run.check_log(mutated, expected, 0)

    def test_reject_expected_lane_order_change(self):
        text, expected = fixture()
        changed = copy.deepcopy(expected)
        changed['lanes'].reverse()
        with self.assertRaises(ValueError):
            run.check_log(text, changed, 0)

    def test_filelist_rejects_live_or_unpinned_source(self):
        for text in ('/tmp/vmfpu.sv\n', '+incdir+/tmp\n', '-f other.f\n',
                     str(run.FROZEN_SOURCE/'hardware/src/foo.sv')+'\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                run.frozen_filelist(text, {})

    def test_snapshot_and_inventory_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source, dest = directory/'source', directory/'copy'
            source.write_text('first')
            pins = {}
            run.copy_pin(source, dest, pins)
            run.verify(pins)
            inventory = {str(directory): sorted(map(str, directory.iterdir()))}
            run.verify_directories(inventory)
            source.write_text('second')
            with self.assertRaises(ValueError):
                run.verify(pins)
            (directory/'new-header.svh').write_text('new')
            with self.assertRaises(ValueError):
                run.verify_directories(inventory)


if __name__ == '__main__':
    unittest.main()
