import copy
import unittest
from unittest.mock import patch

import qualify_narrow_clip_reject_terminal_v2 as q


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = q.namespace()
        cls.pre = q.life.read_bound(q.runner.PRE / 'preflight-manifest.json', q.runner.PRE_SEAL)
        cls.ref = q.prior.p.frozen.shared.parse_spike_commits(q.runner.PRE / 'spike.trace')

    def receipt(self):
        record = dict(command=q.runner.command(q.life.OUT / 'synthetic-clip17-run'))
        state = dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, case=q.runner.NAME,
                     timeout=False, coverage_admitted=False, admission_performed=False,
                     terminal_oracle_verified=False, pid=123, wall_seconds=20.0)
        started = dict(command=record['command'], input_elf=str(q.runner.ELF),
                       elf_sha256=q.runner.ELF_SHA, image=str(q.life.IMAGE), image_sha256=q.runner.IMAGE_SHA,
                       pid=123, process_group=123, budget_s=300, foreground_lifetime=True, coverage_admitted=False)
        return state, copy.deepcopy(record), started, record

    def fixture(self):
        rows = []
        for c in self.ref:
            rd, value = next(iter(c.gpr_writes.items()), (0, 0))
            row = dict(event='retire', cycle=str(len(rows)), order=str(len(rows)), pc='%016x'%c.pc,
                       insn='%08x'%c.instruction, trap='0', rd=str(rd), rd_wdata=hex(value),
                       mem_addr='0', mem_rmask='0', mem_wmask='0', mem_wdata='0')
            access = q.prior.common.scalar_memory(c.instruction)
            if access and c.memory_accesses:
                kind, size = access
                addr, data = c.memory_accesses[0]
                row['mem_addr'] = hex(addr)
                row['mem_' + ('rmask' if kind == 'read' else 'wmask')] = hex(((1<<size)-1) << (addr&7))
                if kind == 'write': row['mem_wdata'] = hex(data)
            rows.append(row)
            if (self.pre['symbols']['tohost'], 1) in c.memory_accesses: break
        return rows

    def test_actual_gold_full_memory_and_ELF(self):
        rows = self.fixture()
        q.audit_retirements(rows)
        result = self.ns['observed'](rows, self.pre['symbols'])
        self.assertEqual((result['checks'], result['snapshots'], result['illegal_traps'],
                          result['explicit_dump_read_bytes'], result['handler_store_words']),
                         (2094, 3, 17, 13824, 221))

    def test_foreign_opcode_rejected(self):
        rows = self.fixture(); rows[0]['insn'] = 'ffffffff'
        with self.assertRaises(ValueError): q.audit_retirements(rows)

    def test_missing_full_snapshot_readback(self):
        rows = self.fixture(); addr = self.pre['symbols']['gnr_dump']
        rows = [r for r in rows if not (int(r['mem_addr'],16)==addr and int(r['mem_rmask'],16))]
        for i,r in enumerate(rows): r['order']=str(i)
        with self.assertRaises(ValueError): self.ns['observed'](rows,self.pre['symbols'])

    def test_corrupt_trap_ledger(self):
        rows=self.fixture(); addr=self.pre['symbols']['gnr_ledger']+16
        found=False
        for r in rows:
            if int(r['mem_addr'],16)==addr and int(r['mem_wmask'],16):
                r['mem_wdata']='0';found=True
        self.assertTrue(found)
        with self.assertRaises(ValueError): self.ns['observed'](rows,self.pre['symbols'])

    def test_successful_OS_identity(self): q.terminal(*self.receipt())

    def test_failed_timeout_unknown_OS_rejected(self):
        for key,value in [('returncode',None),('returncode',1),('timeout',True),('case','other'),('wall_seconds',float('nan'))]:
            args=self.receipt();args[0][key]=value
            with self.assertRaises(ValueError):q.terminal(*args)

    def test_wrong_started_identity_rejected(self):
        for key,value in [('pid',124),('process_group',124),('budget_s',180),('elf_sha256','a'*64),('image_sha256','b'*64),('foreground_lifetime',False)]:
            args=self.receipt();args[2][key]=value
            with self.assertRaises(ValueError):q.terminal(*args)

    def test_wrong_actual_manifest_rejected(self):
        args=self.receipt();args[1]['extra']=True
        with self.assertRaises(ValueError):q.terminal(*args)

    def test_vector_recovery_byte_bound(self):
        with patch.object(q.prior.inherited,'vector_exact'):
            q.vector_exact({'instructions':[{'compared_bytes':4}],'compared_bytes':4100},[],[])
            for size in (0,8,128):
                with self.assertRaises(ValueError):q.vector_exact({'instructions':[{'compared_bytes':size}],'compared_bytes':4096+size},[],[])

    def test_adapter_is_private_and_preserves_predecessor(self):
        self.assertNotEqual(self.ns['STATUS'],q.prior.STATUS)
        self.assertEqual(q.life.digest(q.PRIOR),q.PRIOR_SHA)
        self.assertEqual(self.ns['terminal'],q.terminal)


if __name__=='__main__':unittest.main()
