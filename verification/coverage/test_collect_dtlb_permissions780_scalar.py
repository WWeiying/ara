"""Actual native scalar/handler evidence and precise fault/schema negatives."""
import copy
import csv
import json
from types import FunctionType
import unittest

import collect_dtlb_permissions780_scalar as c


class ActualScalarFaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=c.life.read_bound(c.runner.PRE,c.runner.PRE_SHA)
        cls.commits=c.runner.software.parse_spike_commits(c.runner.PRE.parent/'spike.trace')
        run=c.life.OUT/'dtlb-permissions780-agent-20261008-01'
        with (run/'commit_trace.csv').open() as f:cls.rows=list(csv.DictReader(f))
        path=c.life.OUT/'dtlb-permissions780-scalar-diagnosis-agent-20261008-01/original-wave-audit.json'
        cls.wave=json.loads(path.read_bytes())
        cls.memory=c.architecture_gate(cls.rows,cls.commits,cls.q['symbols'])

    def gate(self,wave):
        # Only the already captured replacement result is supplied; exercise the full new phase gate.
        fn=FunctionType(c.wave_gate.__code__,dict(c.wave_gate.__globals__,replacement_gate=lambda it:copy.deepcopy(wave)))
        return fn(iter(()))

    def test_full_actual_scalar_memory_and_handlers(self):
        self.assertEqual((self.memory['retired'],self.memory['compressed'],self.memory['uncompressed'],
                          self.memory['loads'],self.memory['stores'],self.memory['skipped']),
                         (193080,17141,2716,9245,10612,0))
        self.assertEqual(len(self.memory['handler_faults']),5)
        self.assertFalse(self.memory['trap_rows_observable'])
        self.assertEqual(self.memory['native_trap_rows'],0)

    def test_actual_mmu_phase_and_cycle_ownership(self):
        wave=self.gate(self.wave)
        self.assertEqual(len(wave['replacements']),56)
        self.assertEqual(c.link_fault_cycles(wave,self.memory)['faults'],5)

    def test_wrong_mmu_permission(self):
        wave=copy.deepcopy(self.wave);wave['fault_samples'][0]['SUM']=1
        with self.assertRaises(ValueError):self.gate(wave)

    def test_missing_mmu_fault(self):
        wave=copy.deepcopy(self.wave);wave['fault_samples'].pop()
        with self.assertRaises(ValueError):self.gate(wave)

    def test_wrong_fault_owner_cycle(self):
        wave=copy.deepcopy(self.wave)
        wave['fault_samples'][0]['cycle']=self.memory['handler_faults'][0]['handler_cycle']
        with self.assertRaises(ValueError):c.link_fault_cycles(wave,self.memory)

    def test_foreign_trap_row(self):
        rows=list(self.rows);rows[0]=dict(rows[0],trap='1')
        with self.assertRaises(ValueError):c.architecture_gate(rows,self.commits,self.q['symbols'])

    def test_wrong_handler_cause(self):
        rows=list(self.rows)
        i=next(i for i,r in enumerate(rows) if
               self.q['symbols']['dpa_handler_begin']<=int(r['pc'],16)<self.q['symbols']['dpa_handler_end'] and
               int(r['insn'],16)>>20==0x342 and int(r['rd'])!=0)
        rows[i]=dict(rows[i],rd_wdata=format(int(rows[i]['rd_wdata'],16)^1,'016x'))
        with self.assertRaises(ValueError):c.handler_gate(rows,self.commits,self.q['symbols'])

    def test_typed_vector_zero(self):
        good=c.zero_schema.zero_schema();c.zero_schema.vector_zero(good)
        for bad in (False,[],1):
            value=dict(good,non_bit_exact_instructions=bad)
            with self.assertRaises(ValueError):c.zero_schema.vector_zero(value)


if __name__=='__main__':unittest.main()
