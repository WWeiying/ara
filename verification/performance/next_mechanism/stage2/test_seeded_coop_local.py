#!/usr/bin/env python3
"""Suffix-local evidence checks; no changes to the sealed numeric/queue oracle."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import run_seeded_coop_local as gate
from test_seeded_coop import fixture

PREPARED=None
if '--prepared' in sys.argv:
    index=sys.argv.index('--prepared'); PREPARED=Path(sys.argv[index+1]); del sys.argv[index:index+2]


class LocalTests(unittest.TestCase):
    def fixture(self, queued=0):
        text=fixture()
        line=next(x for x in text.splitlines() if x.startswith('SEEDED_COMMAND seq=5 '))
        return text+f'STAGE2_QUEUE_COMMAND seq=5 fault_drain={queued} terminal=1\n'+(
            f'SEEDED_LOCAL_DONE seed_checks=104 after_nx=64 fault_queued={queued} oracle_suffix=1 active_tail_n=5\n')

    def test_honest_empty_fault_scope_and_nonempty_scope(self):
        for queued in (0,1):
            result=gate.check_log(self.fixture(queued))
            self.assertEqual(result['fault_while_fifo_nonempty'],bool(queued))
            self.assertTrue(result['suffix_local_flags_checked'])

    def test_seed_flag_clear_and_fault_claim_mutations(self):
        for before,after in (('seed_checks=104','seed_checks=103'),('after_nx=64','after_nx=0'),
                             ('fault_queued=0','fault_queued=1')):
            with self.subTest(before=before),self.assertRaises(ValueError):
                gate.check_log(self.fixture().replace(before,after))

    def test_only_local_flags_and_observation_are_added(self):
        parent=gate.v1.ACCEPTED/'matrix_tb.sv'
        original=gate.v1.bench_source(parent.read_text(),(gate.HERE/'seeded_coop_scenarios.svh').read_text())
        result=gate.adapt(original)
        self.assertIn('load_seed_vectors();\n    load_local_flags();',result)
        self.assertIn('fflags_o === 5\'b0 && result_fflags === 5\'b0',result)
        self.assertIn('integer_queue_occupancy != 0) local_fault_queued=1',result)
        scoreboard=original.split('  always_ff @(posedge clk) begin : score_vrf_commit',1)[1].split('  task automatic send_command',1)[0]
        self.assertIn(scoreboard,result)

    def test_actual_callback_pass_active_n_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            if PREPARED:
                program=PREPARED/'local-oracle'; vectors=PREPARED/'vectors.txt'
            else:
                program=tmp/'local-oracle'; vectors=tmp/'vectors'; oracle=tmp/'oracle'
                for source,target in ((gate.HERE/'seeded_coop_vectors.c',oracle),
                                      (gate.HERE/'seeded_coop_local_flags.c',program)):
                    result=subprocess.run(['cc','-O2','-std=c11','-ffp-contract=off','-frounding-math',
                        '-I'+str(gate.v1.ROOT/'verification/qbs'),source,
                        gate.v1.ROOT/'verification/qbs/qbs_ref.c','-lm','-o',target],
                        capture_output=True,text=True,timeout=30)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                result=subprocess.run([oracle,vectors],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            flags=tmp/'flags'
            result=subprocess.run([program,vectors,flags],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(flags.read_text(),'S2LOCAL1\n0 16 0\n1 16 1\n2 16 1\n3 5 1\nEND\n')
            original=vectors.read_text(); lines=original.splitlines()
            target=next(i for i,s in enumerate(lines) if s.startswith('O 3 0 '))
            bits=int(lines[target].split()[3],16); lines[target]=f'O 3 0 {bits^1:08x}'
            mutated=tmp/'mutated'; mutated.write_text('\n'.join(lines)+'\n')
            result=subprocess.run([program,mutated,tmp/'bad-flags'],capture_output=True,text=True,timeout=30)
            self.assertNotEqual(result.returncode,0)


if __name__=='__main__': unittest.main()
