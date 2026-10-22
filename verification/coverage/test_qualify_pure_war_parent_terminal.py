"""Independent terminal gates and mutations, static fixtures only; no running DUT reads."""
from collections import defaultdict
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import qualify_pure_war_parent_terminal as q
import test_pure_war_preflight as fixture


def row(event, cycle, seq=-1, tid=0, insn=0, port=-1, **values):
    r = dict.fromkeys(q.common.COMMIT_FIELDS, '0')
    r.update(event=event, cycle=str(cycle), order=str(seq), trans_id=str(tid), insn='%08x' % insn,
             port=str(port), pc='0000000000000000', mem_addr='0000000000000000',
             mem_rmask='00', mem_wmask='00', mem_wdata='0000000000000000', rd_wdata='0000000000000000')
    r.update({k: str(v) for k, v in values.items()}); return r


def vrow(event, cycle, seq, vid, insn, vd=8, **values):
    r = dict.fromkeys(q.common.VECTOR_FIELDS, '0')
    r.update(event=event, cycle=str(cycle), arch_seq=str(seq), vid=str(vid), insn='%08x' % insn,
             use_vd='1', vd=str(vd), eew='0', vl='1024', vstart='0', nr_lanes='4', vlen_bits='1024',
             be='ff', wdata='0000000000000000')
    r.update({k: str(v) for k, v in values.items()}); return r


def life_fixture():
    s = fixture.symbols(); cs, vs = [], []
    # Seed load response/retirement may precede backend completion.
    for seq, word, pc, vid, vd in ((0, 0x02000007, 0x80003000, 0, 0),
                                  (1, q.p.DIV, s['gpw_div'], 1, 24), (2, q.p.LOAD, s['gpw_load'], 2, 8)):
        t = seq * 10 + 1
        cs += [row('arch_start', t, seq, seq, word), row('uop_alloc', t + 1, seq, seq, word, vid),
               row('cvx_req', t + 2, -1, seq, word), row('cvx_resp', t + 3, -1, seq),
               row('retire', t + 4, seq, seq, word, pc='%016x' % pc), row('uop_done', t + 6, seq, seq, word, vid)]
        vs += [vrow('alloc', t + 1, seq, vid, word, vd), vrow('write', t + 5, seq, vid, word, vd),
               vrow('done', t + 6, seq, vid, word, vd)]
    return s, cs, vs


def observed_fixture():
    s = fixture.symbols(); memory = fixture.expected_memory(s); rows = []
    for address, byte in memory.items():
        rows.append(row('retire', len(rows), len(rows), insn=0x23, mem_addr='%016x' % address,
                        mem_wmask='%02x' % (1 << (address & 7)), mem_wdata='%016x' % byte))
    for word, pc in ((q.p.DIV, s['gpw_div']), (q.p.LOAD, s['gpw_load'])):
        rows.append(row('retire', len(rows), len(rows), insn=word, pc='%016x' % pc))
    for name, size in (('gpw_seed', 4608), ('gpw_dump', 9216), ('gpw_base', 144)):
        for offset in range(0, size, 8):
            address = s[name] + offset; value = int.from_bytes(bytes(memory[address + i] for i in range(8)), 'little')
            rows.append(row('retire', len(rows), len(rows), insn=0x3003, mem_addr='%016x' % address,
                            mem_rmask='ff', rd=1, rd_wdata='%016x' % value))
    rows.append(row('retire', len(rows), len(rows), insn=0x3023, mem_addr='%016x' % s['tohost'], mem_wmask='ff', mem_wdata='0000000000000001'))
    return s, rows


def native_fixture():
    ref = [NS(pc=0x80003000 + r * 4, instruction=0x02000007 | (r << 7),
              vector_writes={r: int.from_bytes(q.p.expected_register(r), 'little')}) for r in range(32)]
    ref += [NS(pc=0x80002000, instruction=q.p.DIV, vector_writes={r: int.from_bytes(q.p.expected_register(r, 1), 'little') for r in range(24, 32)}),
            NS(pc=0x80002004, instruction=q.p.LOAD, vector_writes={r: int.from_bytes(q.p.expected_register(r, 1), 'little') for r in range(8, 16)})]
    activities = {}
    for seq, c in enumerate(ref):
        writes = []
        for reg, value in c.vector_writes.items():
            for word in range(4):
                for lane in range(4):
                    data = 0
                    for byte in range(8):
                        b = word * 32 + q.vc._deshuffle_byte(lane * 8 + byte, 4, 0)
                        data |= ((value >> (b * 8)) & 255) << (8 * byte)
                    writes.append(q.vc.VectorWrite(len(writes), len(writes), seq, seq % 8, lane,
                        1 if c.instruction == q.p.DIV else 4, c.instruction, 0, reg * 4 + word, 255, data, 255))
        activities[seq] = NS(instruction=c.instruction, writes=writes)
    mapping = {i: i for i in range(34)}
    result = dict(status='PASS', compared_instructions=34, compared_bytes=6144, skipped_unknown_bytes=0,
        non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024, selected_index=None, stopped_at_spike_index=None,
        trapped_requests=[], first_mismatch=None, unobservable_instructions=0, incomplete_requests=[], unretired_requests=[])
    result['instructions'] = [dict(pc=hex(c.pc), instruction=hex(c.instruction), status='PASS',
        compared_bytes=128 if i < 32 else 1024, skipped_unknown_bytes=0, unknown_write_bytes=0,
        mismatch_count=0, first_mismatch=None) for i, c in enumerate(ref)]
    return ref, mapping, activities, result


class LifecycleTests(unittest.TestCase):
    def setUp(self): self.s, self.cs, self.vs = life_fixture()
    def reject(self):
        with self.assertRaises(ValueError): q.lifecycle(self.cs, self.vs, self.s)
    def test_complete_seed_retire_before_done(self):
        result = q.lifecycle(self.cs, self.vs, self.s)
        self.assertTrue(result['retire_before_backend_done_allowed']); self.assertFalse(result['source_lifetime_stall_proven'])
    def test_exception(self): self.cs[3]['trap'] = '1'; self.reject()
    def test_missing_response(self): del self.cs[3]; self.reject()
    def test_extra_response(self): self.cs.insert(4, copy.copy(self.cs[3])); self.reject()
    def test_backend_wrong_owner(self): self.cs[5]['order'] = '1'; self.reject()
    def test_backend_wrong_sid(self): self.cs[5]['port'] = '3'; self.reject()
    def test_vector_wrong_owner(self): self.vs[1]['arch_seq'] = '1'; self.reject()
    def test_vector_wrong_metadata(self): self.vs[1]['eew'] = '1'; self.reject()
    def test_vector_after_done(self): self.vs[1]['cycle'] = '8'; self.vs.sort(key=lambda r: int(r['cycle'])); self.reject()
    def test_wrong_real_pc(self): self.cs[10]['pc'] = '%016x' % (self.s['gpw_div'] + 8); self.reject()
    def test_missing_done(self): self.vs.pop(); self.reject()
    def test_global_sid_live_reuse(self):
        self.cs.insert(3, row('uop_alloc', 3, 0, 0, 0x02000007, 0)); self.reject()
    def reuse_fixture(self):
        for r in self.cs:
            if int(r['order']) == 1 or int(r['trans_id']) == 1:
                r['cycle'] = str(int(r['cycle']) - 5)
                if r['event'] in ('uop_alloc', 'uop_done'): r['port'] = '0'
        for r in self.vs:
            if r['arch_seq'] == '1':
                r['cycle'] = str(int(r['cycle']) - 5); r['vid'] = '0'
        self.vs[1]['cycle'] = '7'
        self.cs.sort(key=lambda r: int(r['cycle'])); self.vs.sort(key=lambda r: int(r['cycle']))
    def test_same_cycle_reuse_old_metadata(self):
        self.reuse_fixture(); q.lifecycle(self.cs, self.vs, self.s)
    def test_same_cycle_reuse_wrong_new_owner(self):
        self.reuse_fixture()
        r = next(r for r in self.vs if r['event'] == 'write' and r['arch_seq'] == '0')
        r.update(arch_seq='1', insn='%08x' % q.p.DIV, vd='24'); self.reject()


class ObservedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.s, cls.original = observed_fixture()
    def setUp(self): self.rows = copy.deepcopy(self.original)
    def reject(self):
        with self.assertRaises(ValueError): q.observed(self.rows, self.s)
    def change_read(self, name, offset):
        address = self.s[name] + offset
        hits = [r for r in self.rows if int(r['mem_addr'], 16) == address and r['mem_rmask'] == 'ff']
        self.assertEqual(len(hits), 1); hits[0]['rd_wdata'] = '%016x' % (int(hits[0]['rd_wdata'], 16) ^ 1); self.reject()
    def test_complete(self): self.assertEqual(q.observed(self.rows, self.s)['explicit_read_bytes'], 13968)
    def test_vrf_quotient(self): self.change_read('gpw_dump', (32 + 24) * 144 + 8)
    def test_vrf_load(self): self.change_read('gpw_dump', (32 + 8) * 144 + 8)
    def test_unrelated_vrf(self): self.change_read('gpw_dump', 32 * 144 + 8)
    def test_source(self): self.change_read('gpw_seed', 8 * 144 + 8)
    def test_source_guard(self): self.change_read('gpw_seed', 0)
    def test_base_guard(self): self.change_read('gpw_base', 136)
    def test_missing_readback(self):
        address = self.s['gpw_dump'] + 8
        self.rows = [r for r in self.rows if not (int(r['mem_addr'], 16) == address and r['mem_rmask'] == 'ff')]
        for i, r in enumerate(self.rows): r['order'] = str(i)
        self.reject()
    def test_nonzero_fails(self):
        hits = [r for r in self.rows if int(r['mem_addr'], 16) == self.s['num_failed']]
        self.assertEqual(len(hits), 1); hits[0]['mem_wdata'] = '1'; self.reject()
    def test_nonpass_tohost(self): self.rows[-1]['mem_wdata'] = '3'; self.reject()
    def test_unknown_memory(self): self.rows[0]['insn'] = '00000013'; self.reject()


class NativeAndVectorTests(unittest.TestCase):
    def setUp(self): self.ref, self.mapping, self.activities, self.result = native_fixture()
    def reject_native(self):
        with self.assertRaises(ValueError): q.native_exact(self.activities, self.mapping, self.ref)
    def test_complete(self):
        self.assertEqual(q.native_exact(self.activities, self.mapping, self.ref)['known_bytes'], 6144)
        q.vector_exact(self.result, self.ref)
    def change_write(self, **kw):
        from dataclasses import replace
        self.activities[32].writes[0] = replace(self.activities[32].writes[0], **kw); self.reject_native()
    def test_native_source(self): self.change_write(source=3)
    def test_native_owner(self): self.change_write(arch_seq=1)
    def test_native_eew(self): self.change_write(eew=1)
    def test_native_data(self): self.change_write(data=0)
    def test_native_unknown(self): self.change_write(known_be=254)
    def test_native_overscope(self): self.change_write(addr=0)
    def test_native_missing(self): self.activities[32].writes.pop(); self.reject_native()
    def test_native_duplicate(self): self.activities[32].writes.append(self.activities[32].writes[0]); self.reject_native()
    def test_generic_unknown(self):
        self.result['skipped_unknown_bytes'] = 1
        with self.assertRaises(ValueError): q.vector_exact(self.result, self.ref)
    def test_generic_m2_limit_not_allowed(self):
        self.result['instructions'][-1]['compared_bytes'] = 128
        with self.assertRaises(ValueError): q.vector_exact(self.result, self.ref)
    def test_generic_wrong_pc(self):
        self.result['instructions'][-1]['pc'] = '0'
        with self.assertRaises(ValueError): q.vector_exact(self.result, self.ref)
    def test_mapping_real_helper_names(self):
        arch = [(i, c.instruction) for i, c in enumerate(self.ref)]
        retires = [q.vc.VectorRetire(c.pc, c.instruction) for c in self.ref]
        self.assertEqual(q.vc._map_spike_commits(q.vc._map_architecture_retires(arch, retires, set()), self.ref), self.mapping)


class BindingTerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = q.life.read_bound(q.runner.PRE / 'preflight-manifest.json', q.runner.PRE_SEAL)
        cls.prepared = q.life.read_bound(q.PREPARED, q.RUN_SEAL)
    def setUp(self):
        self.state = dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, case=q.p.NAME, timeout=False,
            coverage_admitted=False, admission_performed=False, terminal_oracle_verified=False, pid=1234)
        self.actual = dict(self.prepared, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
        self.started = dict(pid=1234, process_group=1234, budget_s=600, input_elf=str(q.runner.PRE / 'input.elf'),
            elf_sha256=q.runner.ELF_SEAL, image=str(q.life.IMAGE), image_sha256=q.runner.IMAGE_SEAL,
            command=self.prepared['command'], foreground_lifetime=True, coverage_admitted=False)
    def reject(self):
        with self.assertRaises(ValueError): q.terminal(self.state, self.actual, self.started, self.prepared)
    def test_complete(self): q.terminal(self.state, self.actual, self.started, self.prepared)
    def test_nonzero(self): self.state['returncode'] = 7; self.reject()
    def test_bool_exit(self): self.state['returncode'] = False; self.reject()
    def test_timeout(self): self.state['timeout'] = True; self.reject()
    def test_elf(self): self.started['elf_sha256'] = '0' * 64; self.reject()
    def test_command(self): self.actual['command'] = self.actual['command'] + ['+HINT']; self.reject()
    def test_false_user_provenance(self): self.actual['authorization_source'] = 'USER_REPORTED'; self.reject()
    def test_scope_binding(self):
        prepared = copy.deepcopy(self.prepared); prepared['targets'][0]['scope'] = 'wrong.port'
        with patch.object(q.runner, 'validate'), self.assertRaises(ValueError): q.binding(self.pre, prepared)
    def test_pin_drift(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / 'pin'; f.write_bytes(b'a'); seal = q.life.digest(f); f.write_bytes(b'b')
            with self.assertRaises(ValueError): q.life.check({str(f): seal})


class LogTests(unittest.TestCase):
    def summary(self, **changes):
        data = dict(requests=3, responses=3, exceptions=0, mmu_request_cycles=0, protocol_errors=0, outstanding=0, req_stalled=0, resp_stalled=0)
        data.update(changes)
        return '[ARA_CONTRACT] ' + ' '.join('%s=%s' % item for item in data.items())
    def test_success(self): q.logs(self.summary(), 'Core Test *** SUCCESS ***', dict(requests=3))
    def test_protocol(self):
        with self.assertRaises(ValueError): q.logs(self.summary(protocol_errors=1), 'Core Test *** SUCCESS ***', dict(requests=3))
    def test_extra_exception(self):
        with self.assertRaises(ValueError): q.logs(self.summary(exceptions=1), 'Core Test *** SUCCESS ***', dict(requests=3))
    def test_fatal(self):
        with self.assertRaises(ValueError): q.logs(self.summary(), 'Fatal: tohost3\nCore Test *** SUCCESS ***', dict(requests=3))
    def test_tracer(self):
        rows = [row('retire', 10, insn=0x13, pc='0000000080001000')]
        text = ' 1ns 10 M 0000000080001000 0 00000013 x0\n'
        self.assertEqual(q.tracer_exact(text, rows)['exceptions'], 0)
        with self.assertRaises(ValueError): q.tracer_exact(text + 'Exception @0, PC: 80001000, Cause: Illegal Instruction', rows)


if __name__ == '__main__': unittest.main()
