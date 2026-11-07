#!/usr/bin/env python3
"""Preserve first compile FAIL; correct only its three VCS +incdir tokens."""
import argparse
import json
from pathlib import Path
import signal
import sys
import unittest

import run_mmu_mxr_hit as original

ORIGINAL_SHA = 'f28cd7552837d8de6bb39167f097d51dbbb5de9e70b401a0979e446f53406304'
BENCH_SHA = 'c68bbc2b393eb85b3398b6da664d8689f20627de1b316025b494636faa080a80'
FIRST = original.RUNS/'e2e_mmu_mxr_hit_20261106_01'
FIRST_SHA = '8771ee9dfab61462182af057afbcaa700f11dd9749c8d57334c7d8445c5105ea'
FIRST_PINS_SHA = '679940b262e8441821312080d0fbc857228b26b178010e94eb05036803685c72'


def correct_vcs_argv(argv):
    if Path(argv[0]).name == 'vcs':
        original.require(sum(a.startswith('+incdir=') for a in argv)==3 and
                         not any(a.startswith('+incdir+') for a in argv),
                         'Unreviewed include-argument shape')
        argv[:] = ['+incdir+'+a[len('+incdir='):] if a.startswith('+incdir=') else a for a in argv]
    return argv


def run(output):
    original.require(original.digest(Path(original.__file__))==ORIGINAL_SHA and
                     original.digest(original.HERE/'mmu_mxr_hit_tb.sv')==BENCH_SHA,
                     'Frozen worker or bench changed')
    original.require(original.digest(FIRST/'result.json')==FIRST_SHA and
                     original.digest(FIRST/'source-pins.json')==FIRST_PINS_SHA,
                     'First failure identity changed')
    first = json.loads((FIRST/'result.json').read_text())
    original.require(first['state']=='FAIL' and first['error']=="ValueError('VCS compile failed')" and
                     first['compile_count']==1 and first['simulation_count']==0 and first['post_pins_match'],
                     'Different first failure scope')
    for path, sha in json.loads((FIRST/'source-pins.json').read_text()).items():
        original.require(original.digest(path)==sha,'First input drift: '+path)
    real_popen, real_save = original.subprocess.Popen, original.save
    own_sha = original.digest(__file__)

    def checked_popen(argv, *args, **kwargs):
        # Mutate the same recorded list before launch; final commands.json has
        # the actual corrected argv, not the rejected spelling.
        return real_popen(correct_vcs_argv(argv), *args, **kwargs)

    def checked_save(path, value):
        if path.name=='source-pins.json':
            value[str(Path(__file__).resolve())]=own_sha
            value[str(FIRST/'result.json')]=FIRST_SHA
            value[str(FIRST/'source-pins.json')]=FIRST_PINS_SHA
        if path.name in ('status.json','result.json'):
            value.update(original_worker_state='FAIL', original_worker_relabelled=False,
                         original_result_sha256=FIRST_SHA,
                         adaptation='Only three VCS +incdir= tokens corrected to +incdir+',
                         campaign_compile_count=1+value['compile_count'],
                         campaign_simulation_count=value['simulation_count'])
        real_save(path,value)

    original.subprocess.Popen, original.save = checked_popen, checked_save
    try:
        return original.run(output)
    finally:
        original.subprocess.Popen, original.save = real_popen, real_save


class CorrectionTests(unittest.TestCase):
    def test_three_tokens_only(self):
        argv=['/tool/vcs','-sverilog','+incdir=/a','+incdir=/b','+incdir=/c','dut.sv']
        self.assertIs(correct_vcs_argv(argv),argv)
        self.assertEqual(argv,['/tool/vcs','-sverilog','+incdir+/a','+incdir+/b','+incdir+/c','dut.sv'])

    def test_shape_drift_rejected(self):
        for argv in (['vcs','+incdir=/a'],['vcs','+incdir+/a']):
            with self.assertRaises(ValueError): correct_vcs_argv(argv)

    def test_simulator_untouched(self):
        argv=['/build/simv','-no_save']
        self.assertEqual(correct_vcs_argv(argv),['/build/simv','-no_save'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:
        suite=unittest.TestSuite((unittest.defaultTestLoader.loadTestsFromTestCase(original.AuditTests),
                                 unittest.defaultTestLoader.loadTestsFromTestCase(CorrectionTests)))
        sys.exit(0 if unittest.TextTestRunner().run(suite).wasSuccessful() else 1)
    original.require(args.output is not None,'--output required')
    def stop(sig,_frame): raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,stop)
    sys.exit(run(args.output))
