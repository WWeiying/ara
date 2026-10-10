"""Software gate fixtures, not DUT results. Current simulation logs are never read."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import qualify_vnclipu_parent_terminal as c


def row(event='retire', **values):
    result = dict.fromkeys(c.common.COMMIT_FIELDS, '0'); result['event'] = event
    result.update({k: str(v) for k, v in values.items()}); return result


def control_fixture():
    rows = [row('arch_start', order=0, trans_id=0, insn='%08x' % c.p.BAD, cycle=0),
            row('cvx_req', order=0, trans_id=0, insn='%08x' % c.p.BAD, cycle=1),
            row('cvx_resp', order=-1, trans_id=0, trap=1, cycle=2),
            row('arch_start', order=1, trans_id=1, insn='%08x' % c.p.RECOVERY, cycle=3),
            row('cvx_req', order=1, trans_id=1, insn='%08x' % c.p.RECOVERY, cycle=4),
            row('uop_alloc', order=1, trans_id=1, port=0, insn='%08x' % c.p.RECOVERY, cycle=5),
            row('uop_done', order=1, trans_id=1, port=0, insn='%08x' % c.p.RECOVERY, cycle=6),
            row('cvx_resp', order=-1, trans_id=1, cycle=7)]
    vectors = []
    for event, cycle in [('alloc', 5), ('done', 6)]:
        v = dict.fromkeys(c.common.VECTOR_FIELDS, '0')
        v.update(event=event, cycle=str(cycle), arch_seq='1', insn='%08x' % c.p.RECOVERY,
                 nr_lanes='4', vlen_bits='1024', use_vd='1', vd='16', eew='1', vl='2')
        vectors.append(v)
    return rows, vectors


def signature_fixture(s):
    rows = []
    def store(name, index, value, handler=False, width=8):
        pc = s['gvc_handler'] if handler and not rows else s['gvc_handler'] + 4 if handler else s['gvc_init_begin']
        address = s[name] + index * width
        rows.append(row(pc='%016x' % pc, insn='0002b023' if width == 8 else '0002a023',
            mem_addr='%016x' % address, mem_wmask='%02x' % (((1 << width) - 1) << (address & 7)), mem_wdata='%016x' % value))
    sp = 0x801FFF00
    ledger = [2, s['gvc_bad'], c.p.BAD, 2, 25, 1, 4, 1, 0x2222, 0x3333, 117, sp]
    for i, v in enumerate(ledger): store('gvc_ledger', i, v, True)
    store('gvc_traps', 0, 1, True)
    arrays = dict(gvc_post=[0x1111, 0x2222, 0x3333, sp, 1, 2, 25, 4, 117],
                  gvc_cfg=[2, 25, 1, 4, 117], gvc_recovery_cfg=[2, 9, 0, 5, 117],
                  gvc_restore=[v for value in [s['trap_fail'], 0, sp, 0, 0, 0, 0, 0, 0] for v in [value, value]])
    for name, values in arrays.items():
        for i, value in enumerate(values): store(name, i, value)
    store('g75_result', 0, c.p.CHECKS, width=4); store('g75_result', 1, 0, width=4); store('num_failed', 0, 0, width=4)
    for name, phases in [('gvc_dump', range(3)), ('gvc_seed', range(1))]:
        for phase in phases:
            for reg in range(32):
                data = b'\xa5' * 8 + c.p.expected_register(reg, phase) + b'\xa5' * 8
                for w in range(18):
                    address = s[name] + ((phase * 32 + reg) * 18 + w) * 8
                    rows.append(row(pc='%016x' % s['gvc_init_begin'], insn='0002b303', rd=6,
                        mem_addr='%016x' % address, mem_rmask='ff', rd_wdata='%016x' % int.from_bytes(data[w*8:w*8+8], 'little')))
    store('tohost', 0, 1)
    for i, r in enumerate(rows): r.update(order=str(i), cycle=str(i))
    return rows


class QualificationGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = c.life.read_bound(c.p.PRE / 'preflight-manifest.json', c.PRE_SEAL)
        cls.prepared = c.life.read_bound(c.PREPARED, c.RUN_SEAL)
        cls.review = c.life.read_bound(c.REVIEW, c.REVIEW_SEAL)
        cls.s = cls.pre['symbols']; cls.signatures = signature_fixture(cls.s)
        cls.rows, cls.vectors = control_fixture()
        cls.rows.append(row(pc='%016x' % cls.s['gvc_recovery'], insn='%08x' % c.p.RECOVERY, cycle=8))
        cls.console = '[ARA_CONTRACT] requests=2 responses=2 exceptions=1 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n'
        cls.vcslog = 'Core Test *** SUCCESS ***\n'

    def test_frozen_reference_binding(self): c.binding(self.pre, self.prepared, self.review)
    def test_corrected_parent_test_pin(self):
        self.assertEqual(c.life.digest(c.ROOT / self.review['supplement_test']), self.review['supplement_test_sha256'])
    def test_scope_drift(self):
        pre = deepcopy(self.pre); pre['targets'][0]['scope'] += '.req_ports[2]'
        with self.assertRaises(ValueError): c.binding(pre, self.prepared, self.review)
    def test_checksum_drift(self):
        pre = deepcopy(self.pre); pre['targets'][0]['checksum'] = '0'
        with self.assertRaises(ValueError): c.binding(pre, self.prepared, self.review)
    def test_ELF_command_drift(self):
        prepared = deepcopy(self.prepared); prepared['command'][prepared['command'].index('+PRELOAD=' + self.pre['input_elf'])] = '+PRELOAD=/tmp/other.elf'
        with self.assertRaises(ValueError): c.binding(self.pre, prepared, self.review)
    def test_pin_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'software_fixture'; path.write_bytes(b'original')
            pins = {str(path): c.life.digest(path)}; path.write_bytes(b'changed')
            with self.assertRaises(ValueError): c.life.check(pins)
    def test_parent_review_drift(self):
        review = dict(self.review, preflight_sha256='0'*64)
        with self.assertRaises(ValueError): c.binding(self.pre, self.prepared, review)
    def test_software_lifecycle_fixture(self):
        self.assertEqual(c.lifecycle(self.rows, self.vectors, self.s)['rejected_backend_uops'], 0)
    def test_placeholder_not_real_PC(self):
        self.assertEqual(c.lifecycle(self.rows, self.vectors, self.s)['exception_arch_seq'], 0)
    def test_extra_exception(self):
        rows = deepcopy(self.rows); rows[7]['trap'] = '1'
        with self.assertRaises(ValueError): c.lifecycle(rows, self.vectors, self.s)
    def test_illegal_backend_allocation(self):
        rows = deepcopy(self.rows)
        rows.extend([dict(rows[5], order='0', insn='%08x' % c.p.BAD), dict(rows[6], order='0', insn='%08x' % c.p.BAD)])
        with self.assertRaises(ValueError): c.lifecycle(rows, self.vectors, self.s)
    def test_illegal_VRF_activity(self):
        with self.assertRaises(ValueError): c.lifecycle(self.rows, self.vectors + [dict(self.vectors[0], arch_seq='0')], self.s)
    def test_missing_response(self):
        with self.assertRaises(ValueError): c.lifecycle(self.rows[:7] + self.rows[8:], self.vectors, self.s)
    def test_wrong_recovery_PC(self):
        rows = deepcopy(self.rows); rows[-1]['pc'] = '80000000'
        with self.assertRaises(ValueError): c.lifecycle(rows, self.vectors, self.s)
    def test_late_backend_owner(self):
        rows = deepcopy(self.rows); rows[5]['cycle'] = '1'
        with self.assertRaises(ValueError): c.lifecycle(rows, self.vectors, self.s)
    def test_vector_metadata_drift(self):
        vectors = deepcopy(self.vectors); vectors[-1]['vd'] = '17'
        with self.assertRaises(ValueError): c.lifecycle(self.rows, vectors, self.s)
    def test_full_signature_software_fixture(self): self.assertEqual(c.observed(self.signatures, self.s)['explicit_read_bytes'], 18432)
    def corrupt(self, name, offset, value):
        rows = deepcopy(self.signatures); address = self.s[name] + offset
        matches = [r for r in rows if int(r['mem_addr'], 16) == address]
        self.assertTrue(matches)
        for r in matches: r['mem_wdata' if int(r['mem_wmask'], 16) else 'rd_wdata'] = '%016x' % value
        with self.assertRaises(ValueError): c.observed(rows, self.s)
    def test_nonzero_fails(self): self.corrupt('num_failed', 0, 1)
    def test_nonPASS_tohost(self): self.corrupt('tohost', 0, 3)
    def test_cause(self): self.corrupt('gvc_ledger', 0, 3)
    def test_tval(self): self.corrupt('gvc_ledger', 16, c.p.BAD ^ 1)
    def test_real_PC(self): self.corrupt('gvc_ledger', 8, 0)
    def test_post_vstart(self): self.corrupt('gvc_post', 32, 0)
    def test_guard(self): self.corrupt('gvc_dump', 0, 0)
    def test_far_register(self): self.corrupt('gvc_dump', (32*18 + 31*18 + 8)*8, 0)
    def test_recovery_tail(self): self.corrupt('gvc_dump', (2*32*18 + 16*18 + 16)*8, 0)
    def test_source_guard(self): self.corrupt('gvc_seed', 17*8, 0)
    def test_missing_readback(self):
        rows = deepcopy(self.signatures)
        for r in rows:
            if int(r['mem_rmask'], 16) and int(r['mem_addr'], 16) == self.s['gvc_dump']: r['mem_addr'] = '%016x' % (self.s['gvc_dump'] + 8)
        with self.assertRaises(ValueError): c.observed(rows, self.s)
    def test_contract_PASS_fixture(self): c.logs(self.console, self.vcslog, {'requests': 2})
    def test_protocol_error(self):
        with self.assertRaises(ValueError): c.logs(self.console.replace('protocol_errors=0', 'protocol_errors=1'), self.vcslog, {'requests': 2})
    def test_return0_fatal(self):
        with self.assertRaises(ValueError): c.logs(self.console, self.vcslog + 'Fatal: tohost=3', {'requests': 2})
    def test_extra_contract_exception(self):
        with self.assertRaises(ValueError): c.logs(self.console.replace('exceptions=1', 'exceptions=2'), self.vcslog, {'requests': 2})
    def test_terminal_requires_authorization(self):
        state = dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, case=c.p.NAME, coverage_admitted=False, admission_performed=False)
        c.terminal(state, dict(self.prepared, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'), self.prepared)
        with self.assertRaises(ValueError): c.terminal(state, self.prepared, self.prepared)


if __name__ == '__main__': unittest.main()
