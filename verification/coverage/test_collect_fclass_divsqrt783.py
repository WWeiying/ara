import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import collect_fclass_divsqrt783 as q


def result():
    return dict(status='PASS', first_mismatch=None, stopped_at_spike_index=None,
        vector_destination_requests=228, prefix_vector_destination_requests=228, compared_instructions=228,
        compared_bytes=10272, skipped_unknown_bytes=0, non_bit_exact_instructions=0, unobservable_instructions=0,
        incomplete_requests=[], unretired_requests=[], trapped_requests=[], instructions=[])


def writes(seq, c, expected, source, eew):
    out = []
    for reg in sorted({r for r, _ in expected}):
        for word in range(4):
            for lane in range(4):
                data, be = 0, 0
                for byte in range(8):
                    natural = word * 32 + q.vc._deshuffle_byte(lane * 8 + byte, 4, eew)
                    if (reg, natural) in expected:
                        be |= 1 << byte; data |= expected[(reg, natural)] << (8 * byte)
                if be:
                    out.append(q.vc.VectorWrite(len(out), len(out), seq, 1, lane, source, c.instruction,
                        eew, reg * 4 + word, be, data, 255))
    return out


def native_fixture():
    symbols = {}; refs = []; activities = {}; mapping = {}
    for v in (8, 16, 24): symbols['matrix_initial_v' + str(v)] = 100 + v
    for w in (16, 32, 64):
        for op in ('load_a', 'load_b', 'class', 'div', 'sqrt', 'store'):
            symbols['matrix_' + op + str(w)] = len(symbols) + 1000
    def add(pc, reg, image, eew, vl, source, initialization=False):
        seq = len(refs)
        vector = ({r: 0 for r in range(reg, reg + 8)} if initialization else {reg: int.from_bytes(image, 'little')}) if reg else {}
        c = SimpleNamespace(pc=pc, instruction=0x57, vector_writes=vector)
        expected = ({(r, b): 0 for r in range(reg, reg + 8) for b in range(128)} if initialization
            else {(reg, b): value for b, value in enumerate(image)}) if reg else {}
        refs.append(c); mapping[seq] = seq
        activities[seq] = q.vc.ArchActivity(c.instruction, 1, 1, bool(reg), reg, eew, vl, 0,
            writes(seq, c, expected, source, eew) if reg else [])
    for v in (8, 16, 24): add(symbols['matrix_initial_v' + str(v)], v, b'', 0, 1024, 0, True)
    for cell in range(75):
        w, phase = 16 << (cell // 25), cell % 25
        aa, bb, dest, _ = q.p.images(w, phase); op = q.p.inputs(w, phase, 0)[0]; eew = {16: 1, 32: 2, 64: 3}[w]
        for role, reg, image, source in (('load_a', 8, aa, 4), ('load_b', 16, bb, 4), (op, 24, dest, 1), ('store', 0, b'', 0)):
            add(symbols['matrix_' + role + str(w)], reg, image, eew, 256 // w, source)
    return refs, activities, mapping, symbols


class Collector(unittest.TestCase):
    def test_complete_native_matrix(self):
        proof = q.native_state(*native_fixture())
        self.assertEqual(len(proof['writers']), 225)
        self.assertEqual(proof['active_bytes'] + proof['initialization_bytes'], 10272)

    def test_native_corruption(self):
        for kind in ('byte', 'unknown', 'owner', 'duplicate', 'source', 'context', 'completion', 'missing', 'extra'):
            with self.subTest(kind=kind):
                refs, acts, mapping, symbols = native_fixture(); a = acts[3]; w = a.writes[0]
                if kind == 'byte': a.writes[0] = replace(w, data=w.data ^ 1)
                if kind == 'unknown': a.writes[0] = replace(w, known_be=0)
                if kind == 'owner': a.writes[0] = replace(w, arch_seq=999)
                if kind == 'duplicate': a.writes.append(w)
                if kind == 'source': a.writes[0] = replace(w, source=2)
                if kind == 'context': a.vl = 1
                if kind == 'completion': a.completions = 0
                if kind == 'missing': a.writes.pop()
                if kind == 'extra': acts[999] = a
                with self.assertRaises(ValueError): q.native_state(refs, acts, mapping, symbols)

    def test_vector_full_pass(self): q.vector_gate(result())

    def test_vector_rejects_partial_unknown_or_wrong_schema(self):
        for key, value in (('status', 'PREFIX'), ('compared_instructions', 227), ('compared_bytes', 10271),
            ('skipped_unknown_bytes', 1), ('non_bit_exact_instructions', []), ('unobservable_instructions', False),
            ('stopped_at_spike_index', 1), ('trapped_requests', [1]), ('first_mismatch', {})):
            with self.subTest(key=key):
                r = result(); r[key] = value
                with self.assertRaises(ValueError): q.vector_gate(r)

    def test_terminal_actual_types_and_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder); m = dict(command=['simv'])
            state = dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, timeout=False,
                case=q.runner.NAME, coverage_admitted=False, admission_performed=False, pid=123, wall_seconds=500)
            start = dict(command=m['command'], input_elf=str(q.runner.ELF), elf_sha256=q.runner.ELF_SHA,
                image=str(q.life.IMAGE), image_sha256=q.runner.IMAGE_SHA, pid=123, process_group=123,
                budget_s=900, foreground_lifetime=True)
            actual = dict(m, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
            for name, value in (('started.json', start), ('manifest.json', actual), ('simulation-status.json', state)):
                (run / name).write_text(json.dumps(value))
            self.assertEqual(q.terminal(run, m), state)
            for key, value in (('returncode', False), ('returncode', 1), ('timeout', 0), ('timeout', True), ('case', 'other')):
                bad = dict(state, **{key: value}); (run / 'simulation-status.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError): q.terminal(run, m)

    def test_exact_footprint_gold_size(self):
        names = ('matrix_a', 'matrix_b', 'matrix_dst', 'matrix_ledger', 'matrix_fcsr_restore', 'g75_result', 'num_failed', 'matrix_checks')
        symbols = {n: 0x80010000 + i * 0x2000 for i, n in enumerate(names)}
        wanted, reads = q.expected_footprint(symbols, 0)
        self.assertEqual(len(reads), 14400 + 3600)
        self.assertEqual(len(wanted), 18032)
        self.assertEqual(bytes(wanted[symbols['matrix_ledger'] + i] for i in range(48)),
            b''.join(v.to_bytes(8, 'little') for v in (16, 16, 11, 0, 0, 0)))

    def test_actual_sealed_reference_full_gold(self):
        pre = q.runner.preflight(); refs = q.reference_prefix(pre)
        self.assertEqual(len(refs), 165928)
        rows = []
        for i, c in enumerate(refs):
            rd, value = next(iter(c.gpr_writes.items()), (0, 0))
            row = dict(event='retire', order=str(i), insn=hex(c.instruction), pc=hex(c.pc), trap='0',
                rd=str(rd), rd_wdata=hex(value), mem_rmask='0', mem_wmask='0', mem_addr='0', mem_wdata='0')
            access = q.common.scalar_memory(c.instruction)
            if access:
                kind, width = access; address, data = c.memory_accesses[0]
                row['mem_addr'] = hex(address)
                row['mem_rmask' if kind == 'read' else 'mem_wmask'] = hex(((1 << width) - 1) << (address & 7))
                if kind == 'write': row['mem_wdata'] = hex(data)
            rows.append(row)
        mem = q.memory.scalar_memory_exact(rows, refs)
        self.assertEqual(mem['scalar_memory_accesses'], 30460)
        self.assertGreater(mem['compressed_memory_accesses'], 0)
        self.assertEqual(q.footprint(rows, pre['symbols'], refs)['checks'], 2251)
        for name, offset in (('matrix_a', 0), ('matrix_dst', 16), ('matrix_ledger', 40)):
            address = pre['symbols'][name] + offset
            idx = max(i for i, r in enumerate(rows) if int(r['mem_addr'], 16) == address and int(r['mem_rmask'], 16))
            old = rows[idx]['rd_wdata']; rows[idx]['rd_wdata'] = hex(int(old, 16) ^ 1)
            with self.subTest(corruption=name):
                with self.assertRaises(ValueError): q.footprint(rows, pre['symbols'], refs)
            rows[idx]['rd_wdata'] = old
        with self.assertRaises(ValueError): q.footprint(rows[:-1], pre['symbols'], refs)


if __name__ == '__main__': unittest.main()
