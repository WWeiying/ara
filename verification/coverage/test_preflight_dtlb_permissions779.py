"""Actual scalar Spike fixture plus focused corruptions; no RTL or EDA."""
from dataclasses import replace
import json
import unittest

import preflight_dtlb_permissions779 as pre

FIXTURE = pre.p.OUT / 'dtlb-permissions-preflight779-agent-20261008-03'


class ActualPermissionPreflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((FIXTURE/'preflight.json').read_bytes())
        pre.p.life.check(cls.report['input_pins'])
        pre.p.life.check(cls.report['output_pins'])
        cls.s=cls.report['symbols']
        cls.commits=pre.parse_spike_commits(FIXTURE/'spike.trace')

    def changed_store(self, address):
        result=list(self.commits)
        index=max(i for i,c in enumerate(result) if any(a==address and v is not None
                                                       for a,v in c.memory_accesses))
        c=result[index]
        result[index]=replace(c,memory_accesses=tuple((a,v^1 if a==address and v is not None else v)
                                                    for a,v in c.memory_accesses))
        return result

    def rejected(self, commits):
        with self.assertRaises((ValueError,KeyError)):
            pre.validate(commits,self.s)

    def test_actual_complete_replay(self):
        self.assertEqual(pre.validate(self.commits,self.s),self.report['counts'])

    def test_handler_registers_and_resume(self):
        handler=[c for c in self.commits if self.s['dpa_handler_begin']<=c.pc<self.s['dpa_handler_end']]
        self.assertTrue(handler)
        self.assertTrue(all(set(c.gpr_writes)<=set((5,6,7)) for c in handler))
        self.assertEqual([c.csr_writes[0x341] for c in handler if 0x341 in c.csr_writes],
                         [self.s[x]+4 for x in ('dpa_load','dpa_load','dpa_store','dpa_load','dpa_store')])

    def test_wrong_fault_tval(self):
        self.rejected(self.changed_store(self.s['dpa_traps']+16))

    def test_wrong_probe_memory(self):
        self.rejected(self.changed_store(self.s['dpa_probe']+64*6+48))

    def test_wrong_guard_reread(self):
        result=list(self.commits)
        index=max(i for i,c in enumerate(result) if c.memory_accesses==((pre.p.pa(17)+16,None),))
        result[index]=replace(result[index],gpr_writes={k:v^1 for k,v in result[index].gpr_writes.items()})
        self.rejected(result)

    def test_wrong_permission_setting(self):
        result=list(self.commits)
        index=next(i for i,c in enumerate(result) if c.pc==self.s['dpa_enable'])
        result[index]=replace(result[index],csr_writes={0x300:result[index].csr_writes[0x300]^0x800})
        self.rejected(result)

    def test_missing_restore(self):
        result=list(self.commits)
        index=next(i for i,c in enumerate(result) if c.pc==self.s['dpa_disable'])
        del result[index]
        self.rejected(result)

    def test_duplicate_translated_store(self):
        result=list(self.commits)
        index=next(i for i,c in enumerate(result) if c.pc==self.s['dpa_store'])
        result.insert(index,result[index])
        self.rejected(result)

    def test_wrong_pte_history(self):
        self.rejected(self.changed_store(self.s['dpa_leaf']+8*(pre.p.shared.vpn(0,1)&511)))

    def test_extra_vector_write(self):
        result=list(self.commits)
        result[0]=replace(result[0],vector_writes={8:1})
        self.rejected(result)


if __name__=='__main__':
    unittest.main()
