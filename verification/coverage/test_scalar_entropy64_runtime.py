"""Real sealed reference fixtures and focused negative runtime contracts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_scalar_entropy64 as run
import collect_scalar_entropy64 as collect

LOG = ('Core Test *** SUCCESS ***\n[ARA_CONTRACT] requests=4 responses=4 exceptions=0 '
       'mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n')


def native_reference():
    pre = run.life.read_bound(run.PRE/'preflight.json',run.PRE_SHA)
    commits = run.oracle.build.parse_spike_commits(run.PRE/'spike.trace')
    commits = run.reference_interval(commits,pre['symbols'])
    rows = []
    for i,c in enumerate(commits):
        row = dict(event='retire',order=str(i),cycle=str(100+i*10),pc='%016x'%c.pc,
            insn='%08x'%c.instruction,trap='0',trans_id='0',mem_addr='0',mem_wmask='0',mem_rmask='0',mem_wdata='0')
        if c.instruction & 3 == 3:
            access = run.architecture.spike_trace._scalar_memory_access(c.instruction)
        else:
            access = run.compressed.decode(c.instruction)
            access = (access['kind'],access['size']) if access else None
        if c.memory_accesses and access:
            address,value = c.memory_accesses[0]
            kind,width = access
            row['mem_addr'] = '%016x'%address
            row['mem_wmask' if kind == 'write' else 'mem_rmask'] = '%x'%(((1<<width)-1)<<(address&7))
            if value is not None:
                row['mem_wdata'] = '%016x'%value
        rows.append(row)
    return pre,commits,rows


class Runtime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre,cls.commits,cls.rows = native_reference()

    def test_sealed_real_reference_native_frame(self):
        self.assertEqual(collect.native_frame(self.rows,self.pre['symbols'])['checks'],390)

    def test_actual_ELF_native_initial_read_dominance(self):
        result = collect.initial_and_dominance(run.PRE/'input.elf',self.rows,self.pre['symbols'])
        self.assertTrue(result['native_first_read_store_dominance'])
        self.assertEqual(result['frame_reads'],252)

    def test_result_guard_CSR_mutations_rejected(self):
        for name,offset in (('entropy_results',0),('entropy_memory',0),('entropy_csrs',48)):
            rows = copy.deepcopy(self.rows)
            address = self.pre['symbols'][name]+offset
            stores = [r for r in rows if int(r['mem_addr'],16) == address and int(r['mem_wmask'],16)]
            self.assertTrue(stores)
            stores[-1]['mem_wdata'] = '%x'%(int(stores[-1]['mem_wdata'],16)^1)
            with self.subTest(name=name),self.assertRaises(ValueError):
                collect.native_frame(rows,self.pre['symbols'])

    def test_missing_phase_write_rejected(self):
        address = self.pre['symbols']['entropy_memory']+8
        rows = copy.deepcopy(self.rows)
        stores = [r for r in rows if int(r['mem_addr'],16) == address and int(r['mem_wmask'],16)]
        stores[-2]['mem_wmask'] = '0'
        with self.assertRaises(ValueError):
            collect.native_frame(rows,self.pre['symbols'])

    def test_read_before_native_initialization_rejected(self):
        rows = copy.deepcopy(self.rows)
        address = self.pre['symbols']['entropy_memory']
        read = next(r for r in rows if int(r['mem_addr'],16) == address and int(r['mem_rmask'],16))
        rows.insert(0,read)
        with self.assertRaises(ValueError):
            collect.initial_and_dominance(run.PRE/'input.elf',rows,self.pre['symbols'])

    def test_unshifted_subword_store(self):
        row = dict(insn='00a02223',mem_addr='0000000080004e04',mem_wmask='f0',mem_wdata='0000000000000186')
        self.assertEqual(run.architecture.scalar_store(row),(0x80004e04,b'\x86\x01\x00\x00'))

    def test_full_reference_counts(self):
        counts = run.architecture.reference_counts(self.commits,self.pre['symbols'])
        self.assertEqual(counts['matched_instructions'],3326)
        self.assertEqual(counts['matched_scalar_writes'],1646)
        self.assertEqual(counts['matched_scalar_memory_accesses'],903)
        self.assertEqual(counts['matched_floating_writes'],0)

    def test_terminal_types_and_failure(self):
        good = dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,coverage_admitted=False)
        collect.terminal(good)
        for value in (False,None,1):
            with self.subTest(value=value),self.assertRaises(ValueError):
                collect.terminal(dict(good,returncode=value))

    def test_locked_command(self):
        out = run.OUT/'entropy64-test-only'
        command = run.make_command(out,self.pre)
        self.assertEqual(command.count('+NO_FSDB'),1)
        self.assertIn('+ntb_random_seed=1',command)
        self.assertIn('+PRELOAD='+str(run.PRE/'input.elf'),command)
        self.assertEqual(command[-1],'scalar_entropy64')

    def test_prepare_refuses_existing_output(self):
        with self.assertRaises(ValueError):
            run.prepare(run.PRE)

    def test_module_closure_stable_when_foreign_module_loaded(self):
        self.assertEqual(run.helper_pins(),run.helper_pins())
        self.assertIn(str(Path(run.compressed.__file__).resolve()),run.helper_pins())

    def control_rows(self):
        retires = [copy.deepcopy(r) for r in self.rows if int(r['insn'],16)&127 == 0x73 and
                   int(r['insn'],16)>>20 in (8,15)]
        events = []
        for i,r in enumerate(retires):
            base = 100+i*20
            for event,cycle in (('arch_start',base),('cvx_req',base+1),('cvx_resp',base+2)):
                events.append(dict(r,event=event,cycle=str(cycle),order=str(i)))
            r['cycle'] = str(base+30)
            events.append(r)
        return events

    def test_readonly_CSR_legal_ID_reuse_retire_overlap(self):
        self.assertEqual(collect.lifecycle(self.control_rows(),[],LOG)['requests'],4)

    def test_duplicate_or_late_response_rejected(self):
        for mode in ('duplicate','late'):
            rows = self.control_rows()
            if mode == 'duplicate':
                rows.insert(3,copy.deepcopy(rows[2]))
            else:
                rows[2]['cycle'] = '200000'
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                collect.lifecycle(rows,[],LOG)

    def test_vector_write_rejected(self):
        with self.assertRaises(ValueError):
            collect.lifecycle(self.control_rows(),[dict(event='write')],LOG)

    def test_contract_unknown_trailing_or_UVM_error_rejected(self):
        for log in (LOG.replace('resp_stalled=0','resp_stalled=0 foreign=1'),LOG+'UVM_ERROR @ 12: bad\n'):
            with self.subTest(log=log),self.assertRaises(ValueError):
                collect.lifecycle(self.control_rows(),[],log)

    def test_MDA_codes_are_raw_not_binary_directions(self):
        groups = run.mda.intervals('0 3 14 3 2 4 -1')
        self.assertEqual(groups[0]['extent'],5)
        self.assertEqual(groups[0]['raw_runs'][0]['raw_code'],14)
        for text in ('0 2 4 3 1 0 -1','0 3 14','0 3 -1 -1'):
            with self.subTest(text=text),self.assertRaises(ValueError):
                run.mda.intervals(text)

    def test_reference_boot_and_tail_not_arbitrarily_skipped(self):
        full = run.oracle.build.parse_spike_commits(run.PRE/'spike.trace')
        self.assertEqual(len(run.reference_interval(full,self.pre['symbols'])),3326)
        for records in (full[1:],full+full[:5]):
            with self.assertRaises(ValueError):
                run.reference_interval(records,self.pre['symbols'])


if __name__ == '__main__':
    unittest.main()
