import copy
import unittest
from unittest.mock import patch

import collect_scalar_misalign789 as c


def fixture():
    want = [dict(pc=0x80002660 if i%2 == 0 else 0x80002668,
                 cause=4 if i%2 == 0 else 6, tval=c.oracle.ADDRESSES[i//2]) for i in range(6)]
    edges = []
    for i, w in enumerate(want):
        owner = dict(cause=w['cause'], tval=w['tval'], tid=i)
        for phase in range(3):
            e = dict(cycle=3*i+phase, detector=None, responses=[], load_fault=False,
                store_fault=False, tag_valid=0, kill_req=0, st_valid=0, commit=None, ack=0)
            if phase == 0: e['detector'] = dict(owner)
            if phase == 1:
                e['responses'] = [dict(owner)]
                if w['cause'] == 4: e.update(load_fault=True, tag_valid=1, kill_req=1)
                else: e['store_fault'] = True
            if phase == 2: e['commit'] = dict(w, tid=i)
            edges.append(e)
    return edges, want, [100+i for i in range(6)]


class Native(unittest.TestCase):
    def test_six_complete_owners_and_speculative_kills(self):
        e, w, h = fixture(); result = c.owner_gate(e, w, h)
        self.assertEqual(len(result['owners']), 6)
        self.assertEqual(result['killed_speculative_tags'], 3)
        self.assertFalse(result['external_AXI_directly_observed'])

    def reject(self, mutate):
        e, w, h = fixture(); mutate(e, w, h)
        with self.assertRaises(ValueError): c.owner_gate(e, w, h)

    def test_unowned_return(self): self.reject(lambda e,w,h: e[0].update(detector=None))
    def test_live_fault_load_tag(self): self.reject(lambda e,w,h: e[1].update(kill_req=0))
    def test_fault_store_enqueue(self): self.reject(lambda e,w,h: e[4].update(st_valid=1))
    def test_wrong_commit_tid(self): self.reject(lambda e,w,h: e[2]['commit'].update(tid=7))
    def test_wrong_tval(self): self.reject(lambda e,w,h: e[2]['commit'].update(tval=3))
    def test_wrong_pc(self): self.reject(lambda e,w,h: e[2]['commit'].update(pc=0x80002664))
    def test_fault_register_commit_ack(self): self.reject(lambda e,w,h: e[2].update(ack=1))
    def test_cycle_gap(self): self.reject(lambda e,w,h: e[2].update(cycle=8))
    def test_handler_before_exception(self): self.reject(lambda e,w,h: h.__setitem__(0,1))
    def test_missing_last(self): self.reject(lambda e,w,h: e.pop())
    def test_duplicate_return(self): self.reject(lambda e,w,h: e[1]['responses'].append(dict(e[1]['responses'][0])))

    def test_actual_source_layout_and_non_ecall_valid_semantics(self):
        p = c.source_proof()
        self.assertEqual(p['layouts']['lsu_ctrl_t']['width'], 188)
        self.assertEqual(p['layouts']['dcache_req_i_t']['width'], 199)
        self.assertEqual(p['layouts']['exception_t']['fields']['tval'], [138,75])
        self.assertTrue(p['RVFI_non_ecall_fault_not_valid'])


def reference_rows():
    pre = c.life.read_bound(c.runner.PRE/'preflight-manifest.json', c.runner.PRE_SEAL)
    ref = c.runner.reference(pre); regs = {i:0 for i in range(32)}; rows = []
    for i, commit in enumerate(ref):
        r = dict(order=i, cycle=i+100, event='retire', trap=0, pc=commit.pc, insn=commit.instruction,
            rd=next(iter(commit.gpr_writes),0), rd_wdata=next(iter(commit.gpr_writes.values()),0),
            mem_addr=0, mem_rmask=0, mem_wmask=0, mem_wdata=0)
        d = c.shared.primitive.memory_decode(commit.instruction)
        if d:
            address=(regs[d['base']]+d['offset']) & ((1<<64)-1)
            mask=((1<<d['size'])-1)<<(address&7);r['mem_addr']=address
            if d['kind']=='write':
                r['mem_wmask']=mask;r['mem_wdata']=regs[d['register']]&((1<<(8*d['size']))-1)
            else:r['mem_rmask']=mask
        rows.append(r);regs.update(commit.gpr_writes);regs[0]=0
    return pre, ref, rows


class Reference(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.pre, cls.ref, cls.rows = reference_rows()
    def audit(self, rows):
        return c.architecture(rows, self.ref, self.pre['symbols'], c.runner.ELF.read_bytes(),
            c.oracle.traps((c.runner.PRE/'spike.trace').read_text(),self.pre['symbols']))
    def test_actual_full_reference_gold(self):
        r=self.audit(self.rows)
        self.assertEqual(r['memory_accesses'],226);self.assertEqual(len(r['handlers']),6)
        self.assertEqual(r['gold']['checks'],56)
    def test_wrong_gpr(self):
        rows=copy.deepcopy(self.rows);i=next(i for i,r in enumerate(rows) if r['rd'])
        rows[i]['rd_wdata']^=1
        with self.assertRaises(ValueError):self.audit(rows)
    def test_wrong_store(self):
        rows=copy.deepcopy(self.rows);i=next(i for i,r in enumerate(rows) if r['mem_wmask'])
        rows[i]['mem_wdata']^=1
        with self.assertRaises(ValueError):self.audit(rows)
    def test_wrong_load_mask(self):
        rows=copy.deepcopy(self.rows);i=next(i for i,r in enumerate(rows) if r['mem_rmask'])
        rows[i]['mem_rmask']^=1
        with self.assertRaises(ValueError):self.audit(rows)
    def test_invented_rvfi_fault(self):
        rows=copy.deepcopy(self.rows);rows[0]['trap']=1
        with self.assertRaises(ValueError):self.audit(rows)


if __name__ == '__main__': unittest.main()
