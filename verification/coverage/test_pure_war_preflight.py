"""Pure WAR independent oracle and refusal tests; actual fixture never launches Spike."""
import copy
import json
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import build_pure_war_preflight as q


def symbols():
    result = {n: 0x80010000 + i * 0x10000 for i, n in enumerate(q.SYMBOLS)}
    result.update(gpw_div=0x80002000, gpw_load=0x80002004, gpw_init_begin=0x80003000,
                  gpw_init_end=0x80003100, tohost=0x80001000)
    return result


def expected_memory(s):
    memory = {}
    def put(name, offset, value, width=8):
        for i, b in enumerate(value.to_bytes(width, 'little')):
            memory[s[name] + offset + i] = b
    put('g75_result', 0, q.CHECKS, 4); put('g75_result', 4, 0, 4); put('num_failed', 0, 0, 4)
    for phase in range(2):
        for i, value in enumerate((1024, 3, 0, 4, 117, 128)):
            put('gpw_cfg', (phase * 6 + i) * 8, value)
        for reg in range(32):
            data = b'\xa5' * 8 + q.expected_register(reg, phase) + b'\xa5' * 8
            for i, b in enumerate(data): memory[s['gpw_dump'] + (phase * 32 + reg) * 144 + i] = b
    for reg in range(32):
        data = b'\xa5' * 8 + q.expected_register(reg) + b'\xa5' * 8
        for i, b in enumerate(data): memory[s['gpw_seed'] + reg * 144 + i] = b
    data = b'\xa5' * 8 + bytes((73 * i + 41) % 256 for i in range(128)) + b'\xa5' * 8
    for i, b in enumerate(data): memory[s['gpw_base'] + i] = b
    for i, value in enumerate((0, 0, 0, 0, 0, s['trap_fail'], 0)):
        put('gpw_restore', i * 16, value); put('gpw_restore', i * 16 + 8, value)
    return memory


def commit(pc=0x80004000, instruction=0x13, **kw):
    return NS(pc=pc, instruction=instruction, memory_accesses=kw.get('memory_accesses', []),
              vector_writes=kw.get('vector_writes', {}), gpr_writes=kw.get('gpr_writes', {}),
              fpr_writes={}, csr_writes={})


def synthetic():
    s = symbols(); m = expected_memory(s)
    cs = [commit(s['gpw_init_begin'] + r * 4, 7,
                 vector_writes={r: int.from_bytes(q.expected_register(r), 'little')}) for r in range(32)]
    cs += [commit(gpr_writes={5: 3, 10: s['gpw_base'] + 8}),
           commit(s['gpw_div'], q.DIV, vector_writes={r: int.from_bytes(q.expected_register(r, 1), 'little') for r in range(24, 32)}),
           commit(s['gpw_load'], q.LOAD, vector_writes={r: int.from_bytes(q.expected_register(r, 1), 'little') for r in range(8, 16)})]
    # Individual byte stores make missing signatures and software reads independently mutable.
    cs += [commit(instruction=0x23, memory_accesses=[(a, b)]) for a, b in m.items()]
    for name, size in (('gpw_seed', 4608), ('gpw_dump', 9216), ('gpw_base', 144)):
        cs += [commit(instruction=0x3003, memory_accesses=[(s[name] + i, None)]) for i in range(0, size, 8)]
    cs += [commit(instruction=0x3023, memory_accesses=[(s['tohost'], 1)])]
    return s, cs


class PureWarOracleTests(unittest.TestCase):
    def setUp(self): self.s, self.cs = synthetic()
    def reject(self, cs=None, text=''):
        with self.assertRaises(ValueError): q.validate(self.cs if cs is None else cs, self.s, text)
    def mutate_byte(self, name, offset):
        address = self.s[name] + offset
        hits = [c for c in self.cs if c.memory_accesses and c.memory_accesses[0][0] == address and c.memory_accesses[0][1] is not None]
        self.assertEqual(len(hits), 1)
        hits[0].memory_accesses[0] = (address, hits[0].memory_accesses[0][1] ^ 1)
        self.reject()
    def test_complete(self):
        r = q.validate(self.cs, self.s, '')
        self.assertEqual((r['checks'], r['known_vector_write_bytes'], r['skipped_unknown_bytes']), (1765, 6144, 0))
    def test_exception(self): self.reject(text='exception trap_illegal_instruction, epc 0x80002000')
    def test_fatal(self): self.reject(self.cs + [commit(self.s['trap_fail'])])
    def test_fail(self): self.mutate_byte('num_failed', 0)
    def test_checks(self): self.mutate_byte('g75_result', 0)
    def test_tohost(self): self.cs[-1].memory_accesses = [(self.s['tohost'], 3)]; self.reject()
    def test_extra_tohost(self): self.reject(self.cs + [self.cs[-1]])
    def test_source_guard(self): self.mutate_byte('gpw_seed', 0)
    def test_source_value(self): self.mutate_byte('gpw_seed', 8 * 144 + 8)
    def test_base_guard(self): self.mutate_byte('gpw_base', 143)
    def test_base_value(self): self.mutate_byte('gpw_base', 8)
    def test_vrf_unrelated(self): self.mutate_byte('gpw_dump', 32 * 144 + 8)
    def test_vrf_quotient(self): self.mutate_byte('gpw_dump', (32 + 24) * 144 + 8)
    def test_vrf_index(self): self.mutate_byte('gpw_dump', (32 + 16) * 144 + 8)
    def test_vrf_load(self): self.mutate_byte('gpw_dump', (32 + 8) * 144 + 8)
    def test_csr(self): self.mutate_byte('gpw_cfg', 8)
    def test_restore(self): self.mutate_byte('gpw_restore', 5 * 16 + 8)
    def test_missing_signature(self):
        self.cs = [c for c in self.cs if c.memory_accesses != [(self.s['gpw_base'] + 143, 0xa5)]]
        self.reject()
    def test_missing_full_readback(self):
        address = self.s['gpw_dump'] + 8
        self.cs = [c for c in self.cs if c.memory_accesses != [(address, None)]]
        self.reject()
    def test_div_owner(self): self.cs[33].pc += 8; self.reject()
    def test_load_word(self): self.cs[34].instruction ^= 1 << 20; self.reject()
    def test_nonadjacent(self): self.cs.insert(34, commit()); self.reject()
    def test_divisor(self): self.cs[32].gpr_writes[5] = 4; self.reject()
    def test_load_base(self): self.cs[32].gpr_writes[10] += 1; self.reject()
    def test_div_unknown_missing_register(self): del self.cs[33].vector_writes[31]; self.reject()
    def test_load_wrong_value(self): self.cs[34].vector_writes[8] ^= 1; self.reject()
    def test_extra_vector_write(self): self.reject(self.cs + [commit(vector_writes={0: 0})])
    def test_unknown_memory_instruction(self): self.reject(self.cs + [commit(instruction=0x13, memory_accesses=[(0, None)])])
    def test_pin_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'pin'; p.write_bytes(b'a'); seal = q.life.digest(p); p.write_bytes(b'b')
            with self.assertRaises(ValueError): q.life.check({str(p): seal})
    def test_elf_exact_pair_and_refusals(self):
        blob = bytearray(256); blob[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<HHIQQQIHHHHHH', blob, 16, 2, 243, 1, 0, 0, 64, 0, 64, 0, 0, 64, 1, 0)
        struct.pack_into('<IIQQQQIIQQ', blob, 64, 0, 1, 4, self.s['gpw_div'], 128, 8, 0, 0, 4, 0)
        struct.pack_into('<II', blob, 128, q.DIV, q.LOAD)
        q.verify_elf(blob, self.s)
        s = dict(self.s, gpw_load=self.s['gpw_load'] + 4)
        with self.assertRaises(ValueError): q.verify_elf(blob, s)
        blob[128] ^= 1
        with self.assertRaises(ValueError): q.verify_elf(blob, self.s)
    def test_oracle_old_source_not_overwritten(self):
        for r in range(24, 32):
            old = q.expected_register(r - 16)
            self.assertEqual(q.expected_register(r, 1), bytes(v // 3 for v in old))
        self.assertNotEqual(q.expected_register(8), q.expected_register(8, 1))
    def test_manifest_base_drift(self):
        pre = dict(status=q.STATUS, case=q.NAME, baseline_tests=726, coverage_admitted=False,
                   vcs_started=False, ZCC_executed=False, backend_budget_seconds=600)
        with patch.object(q.life, 'read_bound', return_value=pre), self.assertRaises(ValueError):
            q.verify(Path('/unused'), '0' * 64)
    def test_manifest_wrong_budget(self):
        pre = dict(status=q.STATUS, case=q.NAME, baseline_tests=727, coverage_admitted=False,
                   vcs_started=False, ZCC_executed=False, backend_budget_seconds=1800)
        with patch.object(q.life, 'read_bound', return_value=pre), self.assertRaises(ValueError):
            q.verify(Path('/unused'), '0' * 64)


class TargetBindingTests(unittest.TestCase):
    def mutate_review(self, scope=False):
        read = q.life.read_bound
        review = copy.deepcopy(read(q.REVIEW, q.REVIEW_SEAL))
        if scope: review['zero_targets'][0]['scope'] = 'wrong.port'
        else: review['zero_targets'][0]['point']['expression'] = 'wrong predicate'
        def bound(path, seal): return review if path == q.REVIEW else read(path, seal)
        with patch.object(q.life, 'read_bound', side_effect=bound), self.assertRaises(ValueError): q.target_binding()
    def test_scope_drift(self): self.mutate_review(scope=True)
    def test_source_expression_drift(self): self.mutate_review()


@unittest.skipUnless(os.environ.get('PURE_WAR_PREFLIGHT'), 'Requires actual host/Spike preflight fixture')
class ActualPureWarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(os.environ['PURE_WAR_PREFLIGHT']).absolute()
        cls.pre = json.loads((cls.out / 'preflight-manifest.json').read_bytes())
        cls.cs = q.shared.parse_spike_commits(cls.out / 'spike.trace')
        cls.text = (cls.out / 'spike.trace').read_text()
    def test_actual_complete(self):
        self.assertEqual(q.validate(self.cs, self.pre['symbols'], self.text), self.pre['validation'])
    def test_actual_pin_elf_targets(self):
        self.assertEqual(q.verify(self.out, q.life.digest(self.out / 'preflight-manifest.json')), self.pre)
    def test_actual_exact_one_pc_mutation(self):
        cs = list(self.cs); hits = [i for i, c in enumerate(cs) if c.pc == self.pre['symbols']['gpw_div']]
        self.assertEqual(len(hits), 1); cs[hits[0]] = copy.copy(cs[hits[0]]); cs[hits[0]].pc += 8
        with self.assertRaises(ValueError): q.validate(cs, self.pre['symbols'], self.text)


if __name__ == '__main__': unittest.main()
