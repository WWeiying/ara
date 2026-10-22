import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

import build_readonly_csr_preflight as p


def commit(pc, memory=(), vectors=None, gprs=None, csrs=None, fprs=None, word=0x00003023):
    return SimpleNamespace(pc=pc, instruction=word, memory_accesses=list(memory),
        vector_writes=vectors or {}, gpr_writes=gprs or {}, csr_writes=csrs or {}, fpr_writes=fprs or {})


def fixture():
    s = {n: 0x80010000 + i * 0x1000 for i, n in enumerate(p.SYMBOLS)}
    s['rc_handler_end'] = s['rc_handler_begin'] + 16
    rows = []; trace = ''
    for i, name in enumerate(p.FAULTS):
        trace += f'exception trap_illegal_instruction, epc {s[name]:#x}\n'
        rows.append(commit(s['rc_handler_begin'], [(s['rc_traps'] + i * 32 + j * 8, v)
            for j, v in enumerate([1, 2, s[name], p.opcode(i)])] + [(s['rc_count'], i + 1)]))
        rows.append(commit(s['rc_handler_begin'] + 4, [(0x801fff00 + j * 8, 0) for j in range(3)],
            word=0x00013023))
        for n in ('rc_before', 'rc_after'):
            rows.append(commit(0x80001000, [(s[n] + (i * 10 + j) * 8, v) for j, v in enumerate(p.CONFIG)]))
        rows.append(commit(0x80001000, [(s['rc_rd'] + i * 8, p.SENTINEL)]))
    for n in ('rc_source', 'rc_dump', 'rc_result'):
        rows.append(commit(0x80001000, [(s[n] + i, v) for i, v in enumerate(p.buffer(n))], word=0x23))
    rows += [commit(0x80001000, [(s['g75_result'], p.CHECKS), (s['g75_result'] + 4, 0),
        (s['num_failed'], 0)], word=0x2023), commit(0x80001000, [(s['tohost'], 1)]),
        commit(0x80001000, vectors={8: int.from_bytes(p.buffer('rc_source')[8:136], 'little')}),
        commit(0x80001000, vectors={10: int.from_bytes(bytes([0xa5] * 128), 'little')}),
        commit(s['rc_recovery'], vectors={10: int.from_bytes(p.buffer('rc_result')[8:136], 'little')})]
    return rows, s, trace


class OracleTests(unittest.TestCase):
    def setUp(self): self.rows, self.s, self.trace = fixture()

    def reject(self):
        with self.assertRaises(ValueError): p.validate(self.rows, self.s, self.trace)

    def test_complete_independent_fixture(self):
        result = p.validate(self.rows, self.s, self.trace)
        self.assertEqual((result['checks'], result['exact_traps'], result['handler_store_words']), (733, 12, 96))

    def test_encoding_matrix(self):
        self.assertEqual([p.opcode(i) for i in range(12)], [0xc212ae73, 0xc202ae73, 0xc222ae73,
            0xc212be73, 0xc202be73, 0xc222be73, 0xc210ee73, 0xc200ee73, 0xc220ee73,
            0xc210fe73, 0xc200fe73, 0xc220fe73])
        with self.assertRaises(ValueError): p.opcode(12)

    def test_missing_trap(self):
        self.trace = self.trace.split('\n', 1)[1]; self.reject()

    def test_wrong_trap_cause(self):
        self.rows[0].memory_accesses[1] = (self.s['rc_traps'] + 8, 7); self.reject()

    def test_wrong_tval(self):
        self.rows[0].memory_accesses[3] = (self.s['rc_traps'] + 24, p.opcode(0) ^ 1); self.reject()

    def test_wrong_mepc(self):
        self.rows[0].memory_accesses[2] = (self.s['rc_traps'] + 16, self.s[p.FAULTS[0]] + 4); self.reject()

    def test_rd_change(self):
        self.rows.append(commit(0x80001000, [(self.s['rc_rd'], 0)])); self.reject()

    def test_csr_change(self):
        self.rows.append(commit(0x80001000, [(self.s['rc_after'] + 24, 1)])); self.reject()

    def test_tail_guard_change(self):
        self.rows.append(commit(0x80001000, [(self.s['rc_result'] + 16, 0)], word=0x23)); self.reject()

    def test_unknown_buffer_byte(self):
        self.rows[-7].memory_accesses = []; self.reject()

    def test_illegal_word_retired(self):
        self.rows.append(commit(self.s[p.FAULTS[0]])); self.reject()

    def test_handler_rd_write(self):
        self.rows[0].gpr_writes = {28: 0}; self.reject()

    def test_unexpected_fp(self):
        self.rows[0].fpr_writes = {0: 1}; self.reject()

    def test_extra_vector_write(self):
        self.rows.append(commit(0x80001000, vectors={1: 0})); self.reject()

    def test_exact_single_memory_option(self):
        cmd = p.spike_command(p.OUT / 'fixture')
        self.assertEqual([v for v in cmd if v.startswith('-m')], ['-m0x80000000:0x200000'])
        self.assertIn('--pmpregions=0', cmd)

    @unittest.skipUnless(os.environ.get('RC_PREFLIGHT'), 'Set RC_PREFLIGHT for actual sealed-artifact regression')
    def test_actual_serialized_preflight(self):
        out = Path(os.environ['RC_PREFLIGHT'])
        pre = p.verify(out, p.life.digest(out / 'preflight-manifest.json'))
        self.assertEqual(len(pre['targets']), 24)


if __name__ == '__main__': unittest.main()
