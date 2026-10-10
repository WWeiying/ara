"""Offline sealed Spike fixtures and strict negative cases; no DUT files or EDA."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import qualify_store_fifo_burst_terminal as q


def row(**values):
    result = {k: '0' for k in q.common.COMMIT_FIELDS}
    result.update(values)
    return result


def rvfi_fixture(reference):
    active, rows = False, []
    for c in reference:
        if c.pc == 0x80000000:
            active = True
        if not active:
            continue
        gpr = {r: v for r, v in c.gpr_writes.items() if r}
        if len(gpr) > 1:
            raise ValueError('Not a single RVFI scalar writer')
        rd, value = next(iter(gpr.items()), (0, 0))
        r = row(event='retire', order=str(len(rows)), cycle=str(len(rows)),
                pc=f'{c.pc:016x}', insn=f'{c.instruction:08x}', rd=str(rd), rd_wdata=f'{value:016x}')
        scalar = q.common.scalar_memory(c.instruction)
        if scalar and c.memory_accesses:
            kind, width = scalar
            address, written = c.memory_accesses[0]
            r['mem_addr'] = f'{address:016x}'
            r['mem_rmask' if kind == 'read' else 'mem_wmask'] = f'{((1 << width) - 1) << (address & 7):x}'
            if written is not None:
                r['mem_wdata'] = f'{written:016x}'
        rows.append(r)
        if (0x80001000, 1) in c.memory_accesses:
            break
    return rows


def lifecycle_fixture():
    rows, vectors, reference, mapping = [], [], [], {}
    begin = 0x80002000
    for seq in range(56):
        phase, store = divmod(seq, 8)
        cycle = seq * 10
        reference.append(SimpleNamespace(pc=begin + store * 8, instruction=q.p.STORE))
        mapping[seq] = seq
        for event, time, order, insn in [('arch_start', cycle, seq, q.p.STORE),
                ('cvx_req', cycle + 1, seq, q.p.STORE), ('uop_alloc', cycle + 2, seq, q.p.STORE),
                ('cvx_resp', cycle + 3, -1, 0), ('uop_done', cycle + 4, seq, q.p.STORE)]:
            rows.append(row(event=event, cycle=str(time), order=str(order), trans_id='0', port='0',
                            pc='0000000000000000', insn=f'{insn:08x}'))
        for event, time in [('alloc', cycle + 2), ('done', cycle + 4)]:
            r = {k: '0' for k in q.common.VECTOR_FIELDS}
            r.update(event=event, cycle=str(time), arch_seq=str(seq), insn=f'{q.p.STORE:08x}',
                     vl=str(q.p.LENGTHS[phase]), eew='2', nr_lanes='4', vlen_bits='1024')
            vectors.append(r)
    return rows, vectors, mapping, reference


class QualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre = q.life.read_bound(q.runner.PRE / 'preflight-manifest.json', q.PRE_SEAL)
        cls.symbols = pre['symbols']
        cls.reference = q.p.shared.parse_spike_commits(q.runner.PRE / 'spike.trace')
        cls.rows = rvfi_fixture(cls.reference)

    def test_all_sealed_reference_memory_and_store_bases(self):
        result = q.observed(self.rows, self.symbols)
        self.assertEqual(result['checks'], 2360)
        self.assertEqual(result['explicit_scalar_read_bytes'], 9664)
        self.assertEqual(result['retired_target_stores'], 56)
        self.assertFalse(result['directly_observed_per_owner_AXI'])
        self.assertFalse(result['FIFO_push_pop_measured'])

    def test_destination_guard_corruption_rejected(self):
        rows = deepcopy(self.rows)
        target = self.symbols['sfb_dest']
        r = next(r for r in rows if int(r['mem_addr'], 16) == target and int(r['mem_rmask'], 16))
        r['rd_wdata'] = '0000000000000000'
        with self.assertRaisesRegex(ValueError, 'Destination'): q.observed(rows, self.symbols)

    def test_source_tail_corruption_rejected(self):
        rows = deepcopy(self.rows)
        target = self.symbols['sfb_seed'] + 33 * 4
        r = next(r for r in rows if int(r['mem_addr'], 16) == target and int(r['mem_rmask'], 16))
        r['rd_wdata'] = '0000000000000000'
        with self.assertRaisesRegex(ValueError, 'Source memory'): q.observed(rows, self.symbols)

    def test_wrong_burst_a0_rejected(self):
        rows = deepcopy(self.rows)
        first = next(i for i, r in enumerate(rows) if int(r['pc'], 16) == self.symbols['sfb_burst_begin'])
        writer = max(i for i in range(first) if rows[i]['rd'] == '10')
        rows[writer]['rd_wdata'] = '0000000080100000'
        with self.assertRaisesRegex(ValueError, 'actual a0'): q.observed(rows, self.symbols)

    def test_missing_full_readback_rejected(self):
        rows = deepcopy(self.rows)
        for r in rows:
            if int(r['mem_addr'], 16) == self.symbols['sfb_seed'] and int(r['mem_rmask'], 16):
                r['mem_addr'] = '00000000801f0000'
        with self.assertRaisesRegex(ValueError, 'readback'): q.observed(rows, self.symbols)

    def test_extra_postterminal_retirement_rejected(self):
        rows = deepcopy(self.rows)
        rows.append(row(event='retire', order=str(len(rows)), pc='000000008000007e', insn='0000a001'))
        with self.assertRaisesRegex(ValueError, 'terminal'): q.observed(rows, self.symbols)

    def test_complete_lifecycle(self):
        result = q.lifecycle(*lifecycle_fixture())
        self.assertEqual(result['requests'], 56)
        self.assertEqual(result['backend_uops'], 56)

    def test_sid_completion_owner_rejected(self):
        rows, vectors, mapping, reference = lifecycle_fixture()
        rows[4]['order'] = '1'
        with self.assertRaises(ValueError): q.lifecycle(rows, vectors, mapping, reference)

    def test_native_done_missing_rejected(self):
        rows, vectors, mapping, reference = lifecycle_fixture()
        vectors.pop()
        with self.assertRaisesRegex(ValueError, 'lifecycle'): q.lifecycle(rows, vectors, mapping, reference)

    def test_native_store_wrong_vl_or_writer_rejected(self):
        for key, value in [('vl', '3'), ('use_vd', '1'), ('eew', '0')]:
            rows, vectors, mapping, reference = lifecycle_fixture()
            vectors[0][key] = vectors[1][key] = value
            with self.assertRaisesRegex(ValueError, 'Store native'): q.lifecycle(rows, vectors, mapping, reference)

    def test_uvm_boundary_and_no_override(self):
        summary = '[ARA_CONTRACT] requests=56 responses=56 exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'
        good = summary + '\nUVM_ERROR : 0\nUVM_FATAL : 0\n'
        result = q.logs(good, 'Core Test *** SUCCESS ***\n', dict(requests=56))
        self.assertEqual(result['UVM_errors'], 0)
        for bad in ['UVM_ERROR file.sv(504) [CVXIF/NO_TRAFFIC] no traffic',
                    'UVM_ERROR : 2', 'UVM_FATAL : 1', 'UVM_ERROR : 0 trailing garbage']:
            with self.assertRaisesRegex(ValueError, 'UVM'): q.logs(good + bad, 'Core Test *** SUCCESS ***\n', dict(requests=56))

    def test_terminal_rejects_timeout_unknown_returncode(self):
        with self.assertRaisesRegex(ValueError, 'terminal'): q.terminal({}, {}, {}, {})
        state = dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=None)
        with self.assertRaisesRegex(ValueError, 'terminal'): q.terminal(state, {}, {}, {})

    def test_active_run_never_reads_trace(self):
        plan = dict(status=q.PLAN_STATUS, run=str(q.RUN), preflight_seal=q.PRE_SEAL,
                    parent_prepared_seal=q.RUN_SEAL, pins={'/not/read': 'a' * 64})
        with patch.object(q.life, 'read_bound', return_value=plan) as read, patch.object(q.life, 'check'), \
                patch.object(Path, 'is_file', return_value=False):
            with self.assertRaisesRegex(ValueError, 'active traces'):
                q.collect(q.life.OUT / 'fake-plan.json', 'a' * 64, q.life.OUT / 'test-never-created-store-qualify')
            read.assert_called_once()

    def test_scalar_full_population_negative(self):
        with self.assertRaises(ValueError): q.common.scalar_exact({}, dict(matched_instructions=60995))

    def test_vector_skipping_negative(self):
        with self.assertRaises(ValueError): q.vector_exact(dict(status='PASS', compared_instructions=1,
                                                               compared_bytes=128, skipped_unknown_bytes=1), self.reference)

    def native_fixture(self):
        index = next(i for i, c in enumerate(self.reference) if c.vector_writes)
        commit = self.reference[index]
        seed = commit.vector_writes[8].to_bytes(128, 'little')
        writes = []
        for word in range(4):
            for lane in range(4):
                data = bytes(seed[word * 32 + q.vc._deshuffle_byte(lane * 8 + b, 4, 2)] for b in range(8))
                writes.append(q.vc.VectorWrite(len(writes), word, 0, 0, lane, 4,
                    commit.instruction, 2, 32 + word, 255, int.from_bytes(data, 'little'), 255))
        return {0: q.vc.ArchActivity(instruction=commit.instruction, writes=writes)}, {0: index}

    def test_native_seed_complete128(self):
        activities, mapping = self.native_fixture()
        result = q.native_exact(activities, mapping, self.reference)
        self.assertEqual(result['known_bytes'], 128)
        self.assertEqual(result['skipped_unknown_bytes'], 0)

    def test_native_unknown_and_wrong_source_rejected(self):
        for key, value in [('known_be', 254), ('source', 1), ('eew', 0)]:
            activities, mapping = self.native_fixture()
            activities[0].writes[0] = replace(activities[0].writes[0], **{key: value})
            with self.assertRaisesRegex(ValueError, 'Native source'): q.native_exact(activities, mapping, self.reference)

    def test_native_duplicate_rejected(self):
        activities, mapping = self.native_fixture()
        activities[0].writes.append(activities[0].writes[0])
        with self.assertRaisesRegex(ValueError, 'Duplicate native'): q.native_exact(activities, mapping, self.reference)

    def test_terminal_success_and_wrong_identity(self):
        prepared = q.life.read_bound(q.PREPARED, q.RUN_SEAL)
        state = dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, case=q.p.NAME,
                     timeout=False, coverage_admitted=False, admission_performed=False,
                     terminal_oracle_verified=False, pid=123, wall_seconds=1.0)
        started = dict(pid=123, process_group=123, budget_s=600,
                       input_elf=str(q.runner.PRE / 'input.elf'), elf_sha256=prepared['elf_sha256'],
                       image=str(q.life.IMAGE), image_sha256=prepared['image_sha256'],
                       command=prepared['command'], foreground_lifetime=True, coverage_admitted=False)
        q.terminal(state, prepared, started, prepared)
        started['elf_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'startup identity'): q.terminal(state, prepared, started, prepared)

    def test_vector_complete128_positive(self):
        commit = next(c for c in self.reference if c.vector_writes)
        result = dict(status='PASS', compared_instructions=1, compared_bytes=128, skipped_unknown_bytes=0,
                      non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024, selected_index=None,
                      stopped_at_spike_index=None, trapped_requests=[], first_mismatch=None,
                      unobservable_instructions=0, incomplete_requests=[], unretired_requests=[],
                      instructions=[dict(pc=hex(commit.pc), instruction=hex(commit.instruction),
                          compared_bytes=128, status='PASS', skipped_unknown_bytes=0,
                          unknown_write_bytes=0, mismatch_count=0, first_mismatch=None)])
        q.vector_exact(result, self.reference)


if __name__ == '__main__':
    unittest.main()
