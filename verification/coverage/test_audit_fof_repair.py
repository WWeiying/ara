"""Offline checker fixtures/mutations only; never execute ELF or start EDA."""
import copy
import csv
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_fof_repair as audit


def row(**fields):
    result = dict.fromkeys(audit.common.COMMIT_FIELDS, '0')
    result.update(event='retire', trans_id='-1', pc='0000000000000000',
                  insn='00000000', rd_wdata='0000000000000000',
                  mem_addr='0000000000000000', mem_rmask='00', mem_wmask='00',
                  mem_wdata='0000000000000000')
    result.update({k: str(v) for k, v in fields.items()})
    return result


def vector_row(**fields):
    result = dict.fromkeys(audit.common.VECTOR_FIELDS, '0')
    result.update(event='config', insn='00000000', be='00', wdata='0000000000000000',
                  nr_lanes='4', vlen_bits='1024')
    result.update({k: str(v) for k, v in fields.items()})
    return result


def native_bytes(c, symbols):
    if c.pc == symbols['sf_fof']:
        # Deliberately disagree with Spike on the legal original-active suffix.
        return {(8, b): (audit.oracle.prior.WORD >> (8*b)) & 255 if b < 4 else 0xa6
                for b in range(16)}
    if c.instruction == audit.MASK:
        return {(0, b): 255 for b in range(32)}
    size = 32 if c.pc == symbols['sf_recovery_load'] else 128
    return {(reg, b): (value >> (8*b)) & 255
            for reg, value in c.vector_writes.items() for b in range(size)}


def synthetic_trace(reference, symbols):
    """Encode the sealed oracle as monitor records, not a DUT simulation."""
    rows, vectors, tracer = [], [vector_row()], []
    seq, order = 0, 0
    for index, c in enumerate(reference):
        cycle = (index + 1) * 100
        if c.pc == symbols['sf_handler']:
            rows.append(row(cycle=cycle-1, order=order, pc='%016x' % symbols['sf_ecall'],
                            insn='00000073', trap=1))
            order += 1
            tracer += ['Exception @ 1, PC: %016x, Cause: Environment Call Supervisor Mode, '
                       % symbols['sf_ecall'], '\t\ttval: 0000000000000000']
        if audit.is_vector_instruction(c.instruction):
            tid = seq % 8
            metadata = dict(trans_id=tid, insn='%08x' % c.instruction)
            rows += [row(cycle=cycle, event='arch_start', order=seq, **metadata),
                     row(cycle=cycle+1, event='cvx_req', order=-1, **metadata)]
            if c.vector_writes or c.instruction & 127 == 0x27:
                rows.append(row(cycle=cycle+2, event='uop_alloc', order=seq, port=tid, **metadata))
                eew = 0 if c.instruction == audit.MASK else 2
                context = dict(arch_seq=seq, vid=tid, insn='%08x' % c.instruction,
                               use_vd=int(bool(c.vector_writes)), vd=c.instruction >> 7 & 31,
                               eew=eew, vl=4 if c.instruction == audit.FOF else c.vector_vl,
                               vstart=0)
                vectors.append(vector_row(cycle=cycle+2, event='alloc', **context))
                gold = native_bytes(c, symbols)
                producer = 2 if c.instruction == audit.MASK else 1 if c.instruction == audit.DIV else 4
                for reg in sorted({reg for reg, byte in gold}):
                    for word in range(4):
                        for lane in range(4):
                            be = data = 0
                            for b in range(8):
                                byte = word*32 + audit.vc._deshuffle_byte(lane*8+b, 4, eew)
                                if (reg, byte) in gold:
                                    be |= 1 << b
                                    data |= gold[reg, byte] << (8*b)
                            if be:
                                vectors.append(vector_row(cycle=cycle+3+word, event='write',
                                    source=producer, lane=lane, addr=reg*4+word,
                                    be='%02x' % be, wdata='%016x' % data, **context))
                rows.append(row(cycle=cycle+40, event='uop_done', order=seq, port=tid, **metadata))
                vectors.append(vector_row(cycle=cycle+40, event='done', **context))
            rows.append(row(cycle=cycle+41, event='cvx_resp', order=-1, trans_id=tid))
            seq += 1
        r = row(cycle=cycle+50, order=order, pc='%016x' % c.pc, insn='%08x' % c.instruction)
        writes = {reg: value for reg, value in c.gpr_writes.items() if reg}
        if writes:
            reg, value = next(iter(writes.items()))
            r.update(rd=str(reg), rd_wdata='%016x' % value)
        access = audit.common.scalar_memory(c.instruction)
        if access:
            kind, width = access
            address, value = c.memory_accesses[0]
            r['mem_addr'] = '%016x' % address
            r['mem_rmask' if kind == 'read' else 'mem_wmask'] = '%02x' % (((1 << width)-1) << (address & 7))
            if value is not None:
                r['mem_wdata'] = '%016x' % value
        rows.append(r)
        privilege = 'S' if symbols['sf_s_entry'] <= c.pc < symbols['sf_s_end'] else 'M'
        tracer.append('0ns %s %s %016x 0 %08x' % (r['cycle'], privilege, c.pc, c.instruction))
        order += 1
    vectors.sort(key=lambda r: int(r['cycle']))
    return rows, vectors, '\n'.join(tracer) + '\n', seq


def write_csv(path, fields, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference, cls.symbols, cls.pins = audit.reference_contract()
        cls.rows, cls.vectors, cls.tracer, requests = synthetic_trace(cls.reference, cls.symbols)
        cls.temp = tempfile.TemporaryDirectory(prefix='fof-audit-unit-')
        cls.directory = Path(cls.temp.name)
        write_csv(cls.directory / 'commit_trace.csv', audit.common.COMMIT_FIELDS, cls.rows)
        write_csv(cls.directory / 'vector_trace.csv', audit.common.VECTOR_FIELDS, cls.vectors)
        (cls.directory / 'trace_hart_0.log').write_text(cls.tracer)
        log = ('Core Test *** SUCCESS ***\n[ARA_CONTRACT] requests=%d responses=%d exceptions=0 '
               'mmu_request_cycles=10 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n'
               % (requests, requests))
        for name in ('console.log', 'run.vcs.log'):
            (cls.directory / name).write_text(log)
        _, _, cls.activities = audit.vc._parse_vector_trace(cls.directory / 'vector_trace.csv')
        starts, retires, rejected = audit.vc._parse_architecture_mapping(cls.directory / 'commit_trace.csv')
        cls.mapping = audit.vc._map_spike_commits(
            audit.vc._map_architecture_retires(starts, retires, rejected), cls.reference)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def native_mutation(self, instruction, mutate, message):
        activities = copy.deepcopy(self.activities)
        a = next(a for a in activities.values() if a.instruction == instruction)
        mutate(a)
        with self.assertRaisesRegex(ValueError, message):
            audit.native_state(self.reference, activities, self.mapping, self.symbols)

    def test_complete_positive_checker_fixture_not_dut(self):
        result = audit.audit(self.directory)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['scalar']['matched_instructions'], 83732)
        self.assertGreater(result['scalar_memory']['compressed_memory_accesses'], 0)
        self.assertEqual(result['native']['primary_writers'], 6)
        self.assertEqual(result['native']['defined_compared_bytes'], 684)
        self.assertFalse(result['image_provenance_verified'])
        self.assertFalse(result['coverage_admitted'])

    def test_software_pins_exclude_old_rtl_image(self):
        self.assertTrue(self.pins)
        self.assertFalse(any('/hardware/' in p or 'simv' in p for p in self.pins))
        with patch.object(audit.oracle, 'binding', side_effect=AssertionError('old pins forbidden')):
            audit.reference_contract()

    def test_command_is_original_elf_only_no_launch(self):
        command = audit.simulation_command('/tmp/new-build02/simv', self.directory)
        self.assertIn('+PRELOAD=' + str(audit.ORIGINAL_ELF), command)
        self.assertIn('+COMMIT_TOHOST=80001000', command)
        self.assertEqual(command[0], '/tmp/new-build02/simv')

    def test_reject_original_failed_directory(self):
        old = audit.PRE.parent / 'gap112-sv39-fof-old-image-740-agent-20261007-01'
        with self.assertRaisesRegex(ValueError, 'Empty/truncated CSV'):
            audit.audit(old)

    def test_reject_original_failure_even_without_truncated_last_row(self):
        old = audit.PRE.parent / 'gap112-sv39-fof-old-image-740-agent-20261007-01'
        raw = (old / 'commit_trace.csv').read_bytes().splitlines(keepends=True)
        rows = audit.common.read_csv(b''.join(raw[:-1]), audit.common.COMMIT_FIELDS)
        vectors = audit.common.read_csv((old / 'vector_trace.csv').read_bytes(), audit.common.VECTOR_FIELDS)
        with self.assertRaisesRegex(ValueError, 'Exactly one scalar S ECALL'):
            audit.trap_contract(rows, self.symbols)
        with self.assertRaises(ValueError):
            audit.control.lifecycle(rows, vectors)

    def test_reject_recorded_cause13_vl4_vstart1(self):
        diagnosis = json.loads((audit.PRE.parent /
            'gap112-sv39-fof-terminal-audit-741-agent-20261007-01/audit.json').read_text())
        rows = copy.deepcopy(self.rows)
        values = {self.symbols['sf_record'] + 8*i: int(v, 16)
                  for i, v in enumerate(diagnosis['actual_trap_record'])}
        for r in rows:
            if (self.symbols['sf_handler'] <= int(r['pc'], 16) < self.symbols['sf_handler_end']
                    and int(r['mem_wmask'], 16)):
                address = int(r['mem_addr'], 16)
                if address in values:
                    r['mem_wdata'] = '%016x' % values[address]
        with self.assertRaisesRegex(ValueError, 'Scalar store value'):
            audit.scalar_memory_exact(rows, self.reference)

    def test_reject_compressed_store_corruption(self):
        target = next(r for r in self.rows if r['event'] == 'retire' and
                      int(r['insn'], 16) & 3 != 3 and int(r['mem_wmask'], 16))
        with patch.dict(target, mem_wdata='%016x' % (int(target['mem_wdata'], 16) ^ 1)):
            with self.assertRaisesRegex(ValueError, 'Scalar store value including compressed'):
                audit.scalar_memory_exact(self.rows, self.reference)

    def test_reject_wrong_fof_prefix(self):
        self.native_mutation(audit.FOF,
            lambda a: a.writes.__setitem__(0, replace(a.writes[0], data=a.writes[0].data ^ 1)),
            'defined destination bytes')

    def test_reject_div_corruption(self):
        self.native_mutation(audit.DIV,
            lambda a: a.writes.__setitem__(0, replace(a.writes[0], data=a.writes[0].data ^ 1)),
            'defined destination bytes')

    def test_reject_missing_other_writer(self):
        self.native_mutation(audit.RECOVERY, lambda a: a.writes.clear(), 'defined destination bytes')

    def test_reject_recovery_tail_not_fof_suffix(self):
        self.native_mutation(audit.RECOVERY,
            lambda a: a.writes.append(replace(a.writes[0], addr=12*4+1, be=1)),
            'Unproved tail')

    def test_reject_fof_tail_beyond_original_vl(self):
        self.native_mutation(audit.FOF,
            lambda a: a.writes.append(replace(a.writes[0], addr=8*4+1, be=1)),
            'Unproved tail')

    def test_reject_fof_neighbor_clobber(self):
        self.native_mutation(audit.FOF,
            lambda a: a.writes.append(replace(a.writes[0], addr=10*4, be=1, data=1)),
            'Unproved tail/non-destination')

    def test_reject_unknown_accepted_mask(self):
        self.native_mutation(audit.MASK,
            lambda a: a.writes.__setitem__(0, replace(a.writes[0], known_be=0)),
            'Unknown/invalid accepted')

    def test_reject_illegal_mask_tail(self):
        self.native_mutation(audit.MASK,
            lambda a: a.writes.append(replace(a.writes[0], addr=1, be=1, data=0)),
            'mask-tail')

    def test_reject_bad_write_overwritten_by_correct_write(self):
        self.native_mutation(audit.FOF,
            lambda a: a.writes.insert(0, replace(a.writes[0], cycle=a.writes[0].cycle-1,
                                               data=a.writes[0].data ^ 1)),
            'Corrupt earlier accepted')

    def test_reject_forged_fof_response_trap(self):
        seq = next(seq for seq, a in self.activities.items() if a.instruction == audit.FOF)
        start = next(i for i, r in enumerate(self.rows) if r['event'] == 'arch_start' and int(r['order']) == seq)
        response = next(r for r in self.rows[start:] if r['event'] == 'cvx_resp')
        with patch.dict(response, trap='1'):
            with self.assertRaises(ValueError):
                audit.control.lifecycle(self.rows, self.vectors)

    def test_reject_native_completion_missing(self):
        rows = [r for r in self.rows if not (r['event'] == 'uop_done' and int(r['insn'], 16) == audit.FOF)]
        with self.assertRaises(ValueError):
            audit.control.lifecycle(rows, self.vectors)

    def test_reject_post_return_guard_div_source_context_corruption(self):
        for name in ('sf_guard_lo', 'sf_guard_hi', 'sf_pages', 'sf_source', 'sf_div',
                     'sf_neighbor', 'sf_recovery', 'sf_after'):
            candidates = [r for r in self.rows if r['event'] == 'retire' and
                          int(r['mem_addr'], 16) == self.symbols[name] and int(r['mem_rmask'], 16)]
            self.assertTrue(candidates, name)
            target = candidates[-1]
            with self.subTest(name=name), patch.dict(target,
                    rd_wdata='%016x' % (int(target['rd_wdata'], 16) ^ 1)):
                with self.assertRaises(ValueError):
                    audit.observed(self.rows, self.symbols, audit.ORIGINAL_ELF.read_bytes())

    def test_reject_success_footer_without_full_scalar(self):
        result = audit.common.spike_trace.compare_commit_prefix(
            audit.PRE / 'spike.trace', self.directory / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=self.symbols['tohost'], rvfi_store_data_layout='unshifted')
        result['matched_instructions'] -= 1
        with self.assertRaisesRegex(ValueError, 'Complete scalar differential'):
            audit.scalar_exact(result, self.reference, self.symbols)


if __name__ == '__main__':
    unittest.main()
