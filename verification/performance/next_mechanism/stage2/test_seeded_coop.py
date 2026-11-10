#!/usr/bin/env python3
"""Directed seed-gate contracts, including the actual unchanged C oracle."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import run_seeded_coop as gate


def fixture():
    lines = []
    for seq, updates in ((1,128),(2,256),(3,256),(4,80),(5,17),(6,256),(8,256)):
        row = dict(seq=seq,seeded=int(seq != 1),success=int(seq != 5),fault=int(seq == 5),
            source_words=0 if seq == 1 else 32,seed_rows=0 if seq == 1 else 8 if seq == 4 else 16,
            enq=updates,deq=updates,maxq=4,held_next=12 if seq == 1 else 0,
            updates=updates,flags=int(seq != 1))
        lines.append('SEEDED_COMMAND '+' '.join(f'{k}={row[k]}' for k in gate.SCHEMA))
    lines += ['SEEDED_RESET seq=7 enq=8 deq=3 flushed=5 source_words=32',
        'SEEDED_PASS success=6 faults=1 resets=1 commands=8 oracle=original_qbs_ref scope=component_not_isa',
        'STAGE2_MATRIX_LENDERS_DONE commands=7 native_issues=6000 loan_issues=6000 loan_returns=5999 reset_commands=1 reset_flushed=1 latency=3 instances=4 scope=engine_not_soc',
        'STAGE2_QUEUE_DONE commands=7 enq=1300 deq=1295 resets=1 reset_flushed=5 depth=16']
    return '\n'.join(lines)+'\n'


class SeededTests(unittest.TestCase):
    def reject(self, text):
        with self.assertRaises(ValueError): gate.check_log(text)

    def test_complete_directed_ledger(self):
        self.assertEqual(len(gate.check_log(fixture())['commands']),7)

    def test_missing_duplicate_command(self):
        lines = fixture().splitlines()
        self.reject('\n'.join(lines[1:])); self.reject('\n'.join([lines[0],*lines]))

    def test_seed_and_flags_mutations(self):
        self.reject(fixture().replace('source_words=32','source_words=31',1))
        self.reject(fixture().replace('flags=1','flags=0',1))
        self.reject(fixture().replace('seed_rows=16','seed_rows=15',1))

    def test_no_handoff_or_no_queued_reset(self):
        self.reject(fixture().replace('held_next=12','held_next=0'))
        self.reject(fixture().replace('enq=8 deq=3 flushed=5','enq=3 deq=3 flushed=0'))

    def test_real_lender_and_original_queue_are_required(self):
        self.reject(fixture().replace('instances=4','instances=0'))
        self.reject(fixture().replace('loan_returns=5999','loan_returns=5998'))
        self.reject(fixture().replace('enq=1300 deq=1295','enq=1300 deq=1294'))

    def test_original_numerical_checker_and_real_multiplier_retained(self):
        original = (gate.ACCEPTED/'matrix_tb.sv').read_text()
        scenarios = (gate.HERE/'seeded_coop_scenarios.svh').read_text()
        generated = gate.bench_source(original,scenarios)
        scoreboard = original.split('  always_ff @(posedge clk) begin : score_vrf_commit',1)[1].split('  task automatic send_command',1)[0]
        self.assertIn(scoreboard,generated)
        self.assertIn('.SeedRestoreEnable(1\'b1)',generated)
        self.assertIn('first_write && final_wait == 0',generated)
        self.assertIn('stage2_matrix_lenders',generated)
        self.assertIn('stage2_matrix_queue_probe',generated)
        self.assertIn('source_stream(16,1)',generated)
        lender = (gate.HERE/'matrix_lenders.sv').read_text()
        self.assertIn('simd_mul #(.ElementWidth(EW8), .NumPipeRegs(0)',lender)
        self.assertIn('.op_i(VMULH)',lender)

    def test_fixture_anchor_drift_is_rejected(self):
        with self.assertRaises(ValueError): gate.bench_source('no canonical main','// BEGIN ROUTINES\n')

    def test_actual_oracle_nonzero_prefix_order_and_aligned_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); program = tmp/'oracle'; data = tmp/'vectors'
            result = subprocess.run(['cc','-O2','-std=c11','-ffp-contract=off','-frounding-math',
                '-I'+str(gate.ROOT/'apps/common'),gate.HERE/'seeded_coop_vectors.c',
                gate.ROOT/'verification/qbs/qbs_ref.c','-lm','-o',program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result = subprocess.run([program,data],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('nonzero_seeds=128 prefix_flags=0 continuation_flags=1',result.stdout)
            records = [line.split() for line in data.read_text().splitlines()]
            self.assertEqual(records[0],['S2SEED1']); self.assertEqual(records[-1],['END'])
            self.assertEqual([r for r in records if r[0] == 'F'],
                             [['F','0','0'],['F','1','1'],['F','2','1'],['F','3','1']])
            outputs = [r for r in records if r[0] == 'O']; self.assertEqual(len(outputs),512)
            self.assertTrue(all(int(r[3],16)&0x7fffffff for r in outputs))
            self.assertEqual([int(r[4]) for r in records if r[0] == 'R'],[1,2,2,2,3])
            self.assertTrue(all(int(r[1],16)%16 == 0 and r[2] == 'ffff'
                                for r in records if r[0] == 'B'))
            self.assertNotEqual(outputs[:128],outputs[128:256])


if __name__ == '__main__': unittest.main()
