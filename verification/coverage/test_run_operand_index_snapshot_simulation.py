import copy
import json
from pathlib import Path
import subprocess
import tempfile
from unittest import mock
import unittest

import run_operand_index_snapshot_simulation as m


class Runner(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((m.PRE/'preflight-manifest.json').read_bytes())
        self.targets = json.loads(m.TARGETS.read_bytes())

    def test_actual_sealed_preflight_and_targets(self):
        self.assertEqual(m.life.digest(m.PRE/'preflight-manifest.json'),m.PRE_SEAL)
        self.assertEqual(m.life.digest(m.TARGETS),m.TARGET_SEAL)
        m.validate(self.pre)
        m.validate_targets(self.targets)

    def test_real_reference_population(self):
        reference = m.reference_contract(self.pre)
        self.assertGreater(reference['matched_instructions'],0)
        self.assertEqual(reference['vector_destination_instructions'],4)
        self.assertEqual(reference['minimum_compared_vector_bytes'],608)

    def test_elf_trace_pin_and_symbol_rejected(self):
        for change in ('elf','trace','pc'):
            pre = copy.deepcopy(self.pre)
            if change == 'elf':
                pre['output_pins'][str(m.ELF)] = '0'*64
            elif change == 'trace':
                del pre['output_pins'][str(m.PRE/'spike.trace')]
            else:
                pre['symbols']['replay_indexed_load'] += 4
            with self.assertRaises(ValueError):
                m.validate(pre)

    def test_wrong_oracle_and_bool_count(self):
        for value in (458,True):
            self.pre['validation']['checks'] = value
            with self.assertRaises(ValueError):
                m.validate(self.pre)

    def test_duplicate_hit_shape_and_native_targets(self):
        for mutation in ('duplicate','hit','shape','id','false_branch'):
            t = copy.deepcopy(self.targets)
            if mutation == 'duplicate':
                t['targets'][1] = copy.deepcopy(t['targets'][0])
            elif mutation == 'hit':
                t['targets'][0]['hit_before'] = True
            elif mutation == 'shape':
                t['targets'][0]['checksum'] = None
            elif mutation == 'id':
                t['targets'][0]['point']['native_id'] = '1'
            else:
                t['targets'][-1]['point']['native_vector']['vector'] = '0'*29
            with self.assertRaises(ValueError):
                m.validate_targets(t)

    def test_exact_command_no_compiler_fsdb_or_retry(self):
        out = m.life.OUT/'snapshot-command-unit-test'
        command = m.command(out)
        self.assertEqual(command[0],str(m.life.IMAGE))
        self.assertIn('+NO_FSDB',command)
        self.assertIn('+PRELOAD='+str(m.ELF),command)
        self.assertIn('+COMMIT_TRACE='+str(out/'commit_trace.csv'),command)
        self.assertIn('+VECTOR_TRACE='+str(out/'vector_trace.csv'),command)
        self.assertEqual(command[command.index('-cm_dir')+1],str(out/'code.vdb'))
        self.assertFalse(any('clang' in v or '+FSDB' in v for v in command))

    def test_run_uses_1200_preserves_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)/'run'
            manifest = dict(timeout_s=1200,command=m.command(out),pins={})
            with mock.patch.object(m.life,'check'),mock.patch.object(m.subprocess,'run',
                    side_effect=subprocess.TimeoutExpired(manifest['command'],1200)) as execute:
                with self.assertRaises(subprocess.TimeoutExpired):
                    m.run(out,manifest)
            self.assertEqual(execute.call_args.kwargs['timeout'],1200)
            self.assertEqual(execute.call_count,1)
            self.assertTrue((out/'manifest.json').is_file())
            status = json.loads((out/'simulation-status.json').read_bytes())
            self.assertEqual(status['status'],'SIMULATION_NOT_ADMITTED')
            self.assertFalse(status['coverage_admitted'])

    def test_run_exit_zero_not_architecture_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)/'run'
            manifest = dict(timeout_s=1200,command=m.command(out),pins={})
            with mock.patch.object(m.life,'check'),mock.patch.object(m.subprocess,'run'):
                m.run(out,manifest)
            status = json.loads((out/'simulation-status.json').read_bytes())
            self.assertEqual(status['status'],'SIMULATION_EXITED_NOT_ADMITTED')
            self.assertFalse(status['admission_performed'])

    def test_wrong_budget_and_existing_directory_rejected(self):
        out = m.life.OUT/'snapshot-command-unit-test'
        with self.assertRaises(ValueError):
            m.run(out,dict(timeout_s=600,command=m.command(out),pins={}))
        with self.assertRaises(ValueError):
            m.prepare(m.PRE)

    def scalar_result(self):
        reference = dict(matched_instructions=10,matched_scalar_writes=5,
                         matched_floating_writes=0,matched_scalar_memory_accesses=3)
        result = dict(reference,status='TERMINAL_TOHOST_MATCH',entry='0x0000000080000000',
            rvfi_store_data_layout='unshifted',skipped_unobservable_register_values=0,
            stopped_at_unobservable=None,aligned_vector_faults=[],ara_trap_events=0,
            mismatch=None,terminal_ecall=None,vector_state_compared=False,
            ara_retired_instructions=10,ara_committed_instructions=10,
            terminal_tohost=dict(address='0x0000000080001000',write_value='0x1'))
        return result,reference

    def test_full_scalar_partial_skip_trap_bool_rejected(self):
        result,reference = self.scalar_result()
        m.validate_scalar(result,reference)
        for key,value in (('status','PREFIX'),('skipped_unobservable_register_values',1),
                          ('ara_trap_events',1),('matched_floating_writes',False),
                          ('matched_instructions',9),('mismatch',{})):
            changed = copy.deepcopy(result)
            changed[key] = value
            with self.assertRaises(ValueError):
                m.validate_scalar(changed,reference)

    def test_vector_partial_unknown_missing_bytes_rejected(self):
        result = dict(status='PASS',nr_lanes=4,vlen_bits=1024,vector_destination_requests=4,
            prefix_vector_destination_requests=4,compared_instructions=4,skipped_unknown_bytes=0,
            non_bit_exact_instructions=0,unobservable_instructions=0,incomplete_requests=[],
            unretired_requests=[],trapped_requests=[],first_mismatch=None,stopped_at_spike_index=None,
            compared_bytes=608)
        reference = dict(minimum_compared_vector_bytes=608)
        m.validate_vector(result,reference)
        for key,value in (('status','PREFIX'),('skipped_unknown_bytes',1),('compared_bytes',607),
                          ('unretired_requests',[1]),('non_bit_exact_instructions',1)):
            changed = copy.deepcopy(result)
            changed[key] = value
            with self.assertRaises(ValueError):
                m.validate_vector(changed,reference)

    def signature_rows(self):
        symbols = self.pre['symbols']
        indices,data,after = m.software.images()
        values = {'replay_dump':([0x07070707]*32+after+[0x0a0a0a0a]*32,4),
                  'indices':(indices,4),'source':(data,4),'replay_csr':([37,17,13,0,37,0],8),
                  'g75_result':([457,0],4),'num_failed':([0],4),'g75_trap':([0,0,0],8)}
        def row(pc=0x80000000,insn=0x13,address=0,data=0,mask=0):
            return dict(event='retire',order='0',pc=hex(pc),insn=hex(insn),trap='0',
                        mem_addr=hex(address),mem_wdata=hex(data),mem_wmask=hex(mask))
        rows = [row(symbols['replay_indexed_load'],m.software.WORD)]
        for name,(words,size) in values.items():
            for i,word in enumerate(words):
                address = symbols[name]+i*size
                insn = 0x3023 if size == 8 else 0x2023
                rows.append(row(insn=insn,address=address,data=word,mask=((1<<size)-1)<<(address&7)))
        rows.append(row(insn=0x3023,address=symbols['tohost'],data=1,mask=255))
        for i,r in enumerate(rows):
            r['order'] = str(i)
        return rows,symbols

    def test_signature_exact_and_wrong_csr_guard_prefix(self):
        rows,symbols = self.signature_rows()
        self.assertEqual(m.signature(rows,symbols)['checks'],457)
        for name,offset in (('replay_csr',16),('replay_dump',0),('replay_dump',128),('replay_dump',276)):
            changed = copy.deepcopy(rows)
            target = next(r for r in changed if int(r['mem_addr'],16) == symbols[name]+offset)
            target['mem_wdata'] = hex(int(target['mem_wdata'],16)^1)
            with self.assertRaises(ValueError):
                m.signature(changed,symbols)

    def test_signature_partial_trap_bad_mask_and_failed_terminal(self):
        rows,symbols = self.signature_rows()
        with self.assertRaises(ValueError):
            m.signature(rows[1:],symbols)
        for field,value in (('trap','1'),('mem_wmask','0x7f'),('mem_wdata','0x3')):
            changed = copy.deepcopy(rows)
            changed[-1][field] = value
            with self.assertRaises(ValueError):
                m.signature(changed,symbols)

    def test_prepare_mode_cannot_launch(self):
        output = m.life.OUT/'snapshot-prepare-mode-unit-test'
        with mock.patch.object(m,'prepare',return_value=(output,{'pins':{}})),mock.patch.object(m.life,'save'),\
                mock.patch.object(m.life,'digest',return_value='a'*64),mock.patch.object(m,'run') as execute:
            m.main(['prepare','--output',str(output)])
            execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
