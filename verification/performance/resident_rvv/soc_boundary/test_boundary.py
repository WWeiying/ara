#!/usr/bin/env python3
"""Host arithmetic, source/disassembly and adversarial checker tests; no DUT run."""
import copy
import csv
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

import cases
import check
import generate as g

PC = {str(cases.PV_INSN): 0x80001000, str(0x0485715b): 0x80001008,
      str(0x0445705b): 0x80001010, str(0x0485745b): 0x80001018}
VFIELDS = ('cycle event arch_seq vid lane source insn use_vd vd eew vl vstart addr be wdata nr_lanes vlen_bits').split()
CFIELDS = ('cycle event order port trans_id pc insn rd rd_wdata mem_addr mem_rmask mem_wmask mem_wdata trap').split()


def line(tag, row, hexfields=()):
    return tag+' '+' '.join(k+'='+ (f'{v:016x}' if k in hexfields else str(v)) for k, v in row.items())


def numerical(vectors):
    rows = [line('PV_BOUNDARY_BEGIN', dict(cases=21, vlenb=128, data=vectors['data_identity_sha256']))]
    for s in cases.attempts(vectors['cases']):
        bad = s['error']
        prep = (s['rm'] << 5) | s['initial_flags'] | s['prepared_flags']
        before = (5 << 5 | prep & 31) if bad and s['kind'] == 'frm' else prep
        start = int(bad and s['kind'] == 'vstart')
        off = bad and s['kind'] in ('fs_off', 'vs_off')
        status = 0x6600 & ~(0x6000 if s['kind'] == 'fs_off' else 0x600 if s['kind'] == 'vs_off' else 0)
        vl, vtype = ((0, 0xc0) if s['vtype_mode'] == 1 else
                     (0, 1 << 63) if s['vtype_mode'] == 2 else (128, 0xd2))
        r = dict(id=s['id'], phase=s['phase'], d=s['dimension'], heads=s['heads'], tokens=s['tokens'], rm=s['rm'],
                 prep_fcsr=prep, before_fcsr=before, before_vstart=start,
                 after_fcsr=before if bad else s['expected_fcsr'], after_vstart=start, traps=bad,
                 cause=2 if bad else 0, pc=PC[str(s['instruction'])] if bad else 0, mtval=0,
                 trap_fcsr=before if bad and not off else 0, trap_vstart=start if bad and not off else 0,
                 unexpected=0, guard_errors=0, before_mstatus=status, trap_mstatus=status if bad else 0,
                 after_mstatus=status, before_vl=vl, before_vtype=vtype, after_vl=vl, after_vtype=vtype,
                 trap_csrs_valid=int(bad and not off))
        rows.append(line('PV_BOUNDARY_CASE', r, check.CASE_HEX))
        values = vectors['destination_pattern'] if bad else s['expected']
        rows.append(line('PV_BOUNDARY_DATA', dict(id=s['id'], phase=s['phase'], kind='dest32' if bad else 'result',
                    bits=''.join(f'{v:0{8 if bad else 4}x}' for v in values))))
        if s['kind'] == 'mixed':
            for kind, width, values in (('source', 4, s['source']), ('guard64', 16, vectors['guard_pattern'])):
                rows.append(line('PV_BOUNDARY_DATA', dict(id=s['id'], phase=1, kind=kind,
                                                         bits=''.join(f'{v:0{width}x}' for v in values))))
    rows.append(line('PV_BOUNDARY_COMPAT', dict(qbs_fcsr=0, rvv_fcsr=0,
                qbs=''.join(f'{v:08x}' for v in [0x43800000, 0x44000000, 0x44400000]+[0]*29),
                rvv=''.join(f'{0x10203041+3*i:08x}' for i in range(32)))))
    rows.append(line('PV_BOUNDARY_DONE', dict(cases=21, successes=21, rejected=12, compat=1, errors=0)))
    return '\n'.join(rows)


def work_fixture(vectors):
    vector, commit, probes = [], [], []
    clock = 1
    def row(event, insn, seq, vid, vd=0, vl=256, eew=1, **extra):
        r = dict(cycle=clock, event=event, arch_seq=seq, vid=vid, lane=0, source=0,
                 insn=f'{insn:08x}', use_vd=1, vd=vd, eew=eew, vl=vl, vstart=0,
                 addr=0, be='00', wdata='0000000000000000', nr_lanes=4, vlen_bits=1024)
        r.update(extra)
        return {k: str(v) for k, v in r.items()}
    vector.append(row('config', 0, 0, 0, cycle=0))
    def cpu(event, insn, seq, trap=0):
        r = dict.fromkeys(CFIELDS, '0')
        r.update(cycle=str(clock), event=event, order=str(seq), insn=f'{insn:08x}', trap=str(trap))
        commit.append(r)
    def uop(insn, seq, vid, vd, vl, eew, data, source=4):
        nonlocal clock
        vector.append(row('alloc', insn, seq, vid, vd, vl, eew))
        clock += 1
        for (lane, addr), word in sorted(data.items()):
            vector.append(row('write', insn, seq, vid, vd, vl, eew, lane=lane, addr=addr,
                              source=source, be='ff', wdata=f'{word:016x}'))
            clock += 1
        vector.append(row('done', insn, seq, vid, vd, vl, eew))
        clock += 1
    admitted = 0
    for seq, s in enumerate(cases.attempts(vectors['cases']), 1):
        if not s['phase'] or not s['rejection'] or s['recovery_reloads_context']:
            cpu('retire', cases.FILL_INSN, 0)
            clock += 1
        if not s['phase'] and s['recovery_reloads_context']:
            cpu('retire', cases.RELEASE_INSN, 0)
            clock += 1
        off = s['error'] and s['kind'] in ('fs_off', 'vs_off')
        if not off: cpu('arch_start', s['instruction'], seq)
        if not s['error'] or s['rejection'] == 'backend':
            admitted += 1
            vid = admitted % 8
            if s['kind'] == 'mixed':
                for i in range(6):
                    chunk = s['source'][64*i:64*(i+1)]
                    data = {(l, (8+i)*4+w): check.word16(chunk, l, w) for l in range(4) for w in range(4)}
                    uop(cases.PV_INSN, seq, (vid+i+1) % 8, 8+i, 64, 1, data, 3)
            data = {} if s['error'] else {
                (l, h*8+w): check.word16(s['expected'][h*s['dimension']:(h+1)*s['dimension']], l, w)
                for l in range(4) for h in range(s['heads']) for w in range(s['dimension']//16)}
            uop(cases.PV_INSN, seq, vid, 0, 256, 1, data)
            words, writes = s['dimension']//16, s['dimension']//4*s['heads']
            if not s['error']:
                for l in range(4):
                    probes.append(line('[RESIDENT_PV_LANE]', dict(lane=l, vid=vid, tokens=s['tokens'],
                        elements=s['dimension']//4, heads=s['heads'], issued=words*s['heads']*s['tokens'],
                        returned=words*s['heads']*s['tokens'], writes=writes//4, flags=s['lane_flags'][l], error=0)))
            counts = dict(seed_words=writes, coefficients=4*s['tokens'], value_words=4*s['tokens']*words,
                          result_words=writes, final_acks=writes, row_reads=s['tokens']*words)
            if s['error']: counts = dict.fromkeys(counts, 0)
            probes.append(line('[RESIDENT_PV_PERF]', dict(seq=admitted, vid=vid, control=s['control'],
                tokens=s['tokens'], words=words, heads=s['heads'], cycles=100, error=s['error'],
                flags=0 if s['error'] else s['pv_flags'], source_words=96, **counts)))
        cpu('retire', s['instruction'], seq, s['error'])
        clock += 2
        if s['phase']:
            cpu('retire', cases.RELEASE_INSN, 0)
            clock += 1
    values = [0x43800000, 0x44000000, 0x44400000]+[0]*29
    data = {(l, 32+w): values[8*w+l] | (values[8*w+l+4] << 32) for l in range(4) for w in range(4)}
    uop(cases.QBS_INSN, 100, 1, 8, 32, 2, data)
    cpu('retire', cases.QBS_INSN, 100)
    clock += 1
    data = {(l, 64+w): (0x10203041+3*(8*w+l)) | ((0x10203041+3*(8*w+l+4)) << 32)
            for l in range(4) for w in range(4)}
    uop(cases.VADD_INSN, 101, 2, 16, 32, 2, data, 0)
    cpu('retire', cases.VADD_INSN, 101)
    return vector, commit, '\n'.join(probes)


class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = os.environ.get('PV_BOUNDARY_VECTORS')
        cls.temp = None
        if name:
            cls.vectors = json.loads(Path(name).read_text())
        else:
            cls.temp = tempfile.TemporaryDirectory()
            cls.vectors = g.generate(Path(cls.temp.name)/'vectors')

    @classmethod
    def tearDownClass(cls):
        if cls.temp: cls.temp.cleanup()

    def audit_work(self, vector, commit, text):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, fields, rows in (('v.csv', VFIELDS, vector), ('c.csv', CFIELDS, commit)):
                p = Path(tmp)/name
                with p.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader(); writer.writerows(rows)
                paths.append(p)
            return check.check_work(*paths, text, self.vectors)

    def test_fixed_matrix(self):
        rows = cases.scenarios()
        self.assertEqual((len(rows), len(cases.attempts(rows))), (21, 33))
        self.assertEqual(sum(r['rejection'] == 'frontend' for r in rows), 9)
        self.assertEqual(sum(r['rejection'] == 'backend' for r in rows), 3)
        self.assertEqual({r['rm'] for r in rows[:6]}, set(range(5)))
        self.assertEqual({r['dimension'] for r in rows[:6]}, {64, 96, 128})
        self.assertEqual({r['heads'] for r in rows[:6]}, {1, 2})
        self.assertEqual({r['tokens'] for r in rows[:6]}, {1, 9, 64})

    def test_real_provenance_and_aliases(self):
        for r in self.vectors['cases']:
            self.assertEqual(r['provenance']['derived_from_D128'], r['dimension'] != 128)
            self.assertEqual(len(r['expected']), r['dimension']*r['heads'])
        for r in self.vectors['cases'][16:]:
            for k in ('probability', 'scale', 'seed', 'value', 'key', 'source', 'expected'):
                self.assertEqual(r[k], self.vectors['cases'][5][k])

    def test_directed_flags(self):
        self.assertTrue(self.vectors['cases'][6]['pv_flags'] & 16)
        self.assertEqual(self.vectors['cases'][6]['initial_flags'], 8)
        self.assertEqual(self.vectors['cases'][7]['pv_flags'] & 19, 3)
        for r in self.vectors['cases']:
            flags = 0
            for f in r['lane_flags']: flags |= f
            self.assertEqual(flags, r['pv_flags'])

    def test_nonuniform_ew32_and_ew64_patterns(self):
        p, q = cases.dest_pattern(), cases.guard_pattern()
        self.assertEqual((len(set(p)), len(set(q))), (128, 32))
        self.assertNotEqual(p, p[::2]+p[1::2])
        self.assertNotEqual(q, list(reversed(q)))

    def test_native_permutation_covers_all_dimensions(self):
        for d in (64, 96, 128):
            indices = [i for l in range(4) for w in range(d//16) for i in cases.native_indices(l, w)]
            self.assertEqual(sorted(indices), list(range(d)))

    def test_scalar_control_codes_and_illegal_tokens(self):
        self.assertEqual(cases.control(128, 2, 64), 255)
        self.assertEqual(cases.control(96, 1, 9), 264)
        for args in ((32, 1, 1), (64, 0, 1), (64, 1, 0), (64, 1, 65)):
            with self.assertRaises(ValueError): cases.control(*args)

    def test_numerical_accepts_exact_complete_fixture(self):
        result = check.check_log(numerical(self.vectors), self.vectors, PC)
        self.assertEqual((result['scenarios'], result['compat_postludes']), (21, 1))

    def test_numerical_rejects_terminal_and_record_mutations(self):
        text = numerical(self.vectors)
        for bad in (text+'\n'+text.splitlines()[-1], text.rsplit('\n', 1)[0],
                    text+'\nPV_BOUNDARY_UNKNOWN errors=0', text.replace('errors=0', 'errors=1'),
                    text.replace('guard_errors=0', 'guard_errors=1'), text.replace('cause=2', 'cause=3')):
            with self.subTest(tail=bad[-50:]), self.assertRaises(ValueError): check.check_log(bad, self.vectors, PC)

    def test_numerical_rejects_wrong_output_even_if_target_claims_success(self):
        text = numerical(self.vectors)
        first = next(x for x in text.splitlines() if 'kind=result ' in x)
        bad = first[:-1]+('1' if first[-1] != '1' else '2')
        with self.assertRaises(ValueError): check.check_log(text.replace(first, bad), self.vectors, PC)

    def test_raw_csr_and_vector_config_mutations(self):
        text = numerical(self.vectors)
        for old, new in (('trap_vstart=1', 'trap_vstart=0'), ('before_vtype=8000000000000000', 'before_vtype=00000000000000c0'),
                         ('after_vl=0', 'after_vl=1'), ('trap_csrs_valid=0', 'trap_csrs_valid=1')):
            self.assertIn(old, text)
            with self.assertRaises(ValueError): check.check_log(text.replace(old, new), self.vectors, PC)

    def test_mtval_zero_is_legal_for_backend_error(self):
        self.assertTrue(check.check_log(numerical(self.vectors), self.vectors, PC)['numerical_checked'])

    def test_exact_work_including_maintenance_and_postlude(self):
        result = self.audit_work(*work_fixture(self.vectors))
        self.assertEqual((result['admitted_pv'], result['maintenance_uops'], result['frontend_rejected']), (24, 6, 9))
        self.assertEqual((result['same_context_recoveries'], result['released_context_reloads'],
                          result['actual_fill_retirements'], result['actual_release_retirements']), (11, 1, 22, 22))

    def test_recovery_uses_existing_context_geometry_and_oracle(self):
        specs = cases.attempts(self.vectors['cases'])
        mismatch = [s for s in specs if s['kind'] == 'context_d']
        overshoot = [s for s in specs if s['kind'] == 'context_t']
        self.assertEqual([s['dimension'] for s in mismatch], [96, 128])
        self.assertEqual([s['tokens'] for s in overshoot], [64, 9])
        for s in (mismatch[1], overshoot[1]):
            self.assertEqual(len(s['expected']), s['dimension']*s['heads'])
            self.assertEqual(s['control'], cases.control(s['dimension'], s['heads'], s['tokens']))
        rows = self.vectors['cases']
        self.assertEqual([r['kind'] for r in rows if r['recovery_reloads_context']], ['no_context'])

    def test_recovery_rejects_hidden_reload_release_or_refill(self):
        for insn in (cases.FILL_INSN, cases.RELEASE_INSN, 0x02a0605b):
            v, c, p = work_fixture(self.vectors)
            i = next(i for i, r in enumerate(c) if r['event'] == 'retire' and r['trap'] == '1')
            c.insert(i+1, dict(c[i], insn=f'{insn:08x}', trap='0'))
            with self.subTest(insn=hex(insn)), self.assertRaisesRegex(ValueError, 'Context lifetime/recovery'):
                self.audit_work(v, c, p)

    def test_firmware_recovery_has_no_unconditional_context_reload(self):
        source = (g.HERE/'main.c').read_text()
        recovery = source.split('attempt(c, 1);', 1)[1].split('attempt(&recovery, 0);', 1)[0]
        self.assertNotIn('boundary_release()', recovery)
        self.assertEqual(recovery.count('fill('), 1)
        self.assertIn('if (c->kind == KIND_NO_CONTEXT) fill(', recovery)
        self.assertIn('recovery.dimension = c->context_dimension;', recovery)
        self.assertIn('recovery.tokens = c->context_tokens;', recovery)

    def test_frontend_has_no_backend_alloc(self):
        v, c, p = work_fixture(self.vectors)
        # Change a rejected backend attempt to a frontend identity: it must fail.
        bad_seq = next(r['order'] for r in c if r['event'] == 'retire' and r['insn'] == '0485715b')
        first = next(r for r in v if r['event'] == 'alloc' and r['insn'] == '0485705b')
        first['arch_seq'] = bad_seq
        with self.assertRaises(ValueError): self.audit_work(v, c, p)

    def test_backend_error_cannot_write_destination(self):
        v, c, p = work_fixture(self.vectors)
        bad = cases.attempts(self.vectors['cases'])
        seq = str(next(i+1 for i, s in enumerate(bad) if s['error'] and s['rejection'] == 'backend'))
        i = next(i for i, r in enumerate(v) if r['arch_seq'] == seq and r['event'] == 'alloc')
        v.insert(i+1, dict(v[i], event='write', source='4', be='ff'))
        with self.assertRaises(ValueError): self.audit_work(v, c, p)

    def test_maintenance_cannot_escape_six_source_registers(self):
        for key, value in (('vd', '14'), ('source', '4'), ('addr', '56'), ('vl', '256')):
            v, c, p = work_fixture(self.vectors)
            r = next(r for r in v if r['event'] == 'write' and r['source'] == '3')
            r[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.audit_work(v, c, p)

    def test_final_pv_cannot_use_maintenance_permissions(self):
        v, c, p = work_fixture(self.vectors)
        r = next(r for r in v if r['event'] == 'write' and r['insn'] == '0485705b' and r['source'] == '4')
        r.update(source='3', addr='32')
        with self.assertRaises(ValueError): self.audit_work(v, c, p)

    def test_probes_require_local_flags_and_real_work(self):
        v, c, p = work_fixture(self.vectors)
        for bad in (p.replace('source_words=96', 'source_words=95'), p.replace('returned=', 'invalid='),
                    p+'\n[RESIDENT_PV_UNKNOWN] x=0', p.replace('seq=1 ', 'seq=2 ')):
            with self.assertRaises(ValueError): self.audit_work(v, c, bad)

    def test_qbs_skip_or_tail_corruption_is_not_acceptance(self):
        v, c, p = work_fixture(self.vectors)
        with self.assertRaises(ValueError): self.audit_work([r for r in v if r['insn'] != '00b5045b'], c, p)
        next(r for r in v if r['insn'] == '00b5045b' and r['event'] == 'write')['wdata'] = '0000000000000001'
        with self.assertRaises(ValueError): self.audit_work(v, c, p)

    def test_trap_and_capture_source_order(self):
        trap = (g.HERE/'trap.S').read_text()
        pv = (g.HERE/'pv.S').read_text()
        self.assertNotIn('addi t0, t0, 4', trap)
        self.assertIn('bne t2, t3, .Lunexpected', trap)
        self.assertIn('bne t1, t3, .Lunexpected', trap)
        self.assertLess(trap.index('beqz t1, .Ltrap_minimal'), trap.index('frcsr t3'))
        self.assertLess(pv.index('sd t1, 64(t0)'), pv.index('csrwi frm, 0'))
        self.assertLess(pv.index('sd t1, 160(t0)'), pv.index('vsetvli zero, s1'))
        self.assertIn('li t0, 192\n    vsetvli zero, t0, e32, m8', pv)
        self.assertIn('vle64.v v14, (a1)', pv)

    def test_no_live_sdk_or_skip_or_runtime_full_input_hash(self):
        src = (g.HERE/'main.c').read_text()+(g.HERE/'compat.c').read_text()
        self.assertNotIn('SKIP', src)
        self.assertNotIn('hash_bytes', src)
        self.assertIn('.word 0x00b5045b', src)
        self.assertNotIn('mtvec_handler', (g.HERE/'compat.c').read_text())

    def test_generated_header_deduplicates_arrays(self):
        header = g.header(self.vectors['cases'], '0'*64)
        self.assertNotIn('c20_probability[]', header)
        self.assertIn('#define BOUNDARY_CASES 21', header)

    def test_gnu_built_image_when_requested(self):
        name = os.environ.get('PV_BOUNDARY_BUILD')
        if not name: self.skipTest('GNU build not supplied; no target execution is inferred')
        out = Path(name)
        asm = (out/'disassembly.log').read_text()
        for symbol in ('boundary_pv_fault_pc', 'boundary_pv_rd2_pc', 'boundary_pv_vs2v4_pc',
                       'boundary_pv_alias_pc', 'resident_pv_prepare', 'boundary_trap', 'boundary_compat'):
            self.assertIn('<'+symbol+'>:', asm)
        self.assertIn('00b5045b', asm)
        self.assertIn('0300b857', asm)
        self.assertRegex(asm, r'vle32\.v\s+v8,\(x10\)')
        for line_ in (out/'segments.log').read_text().splitlines():
            if line_.split()[:1] == ['LOAD']:
                p = line_.split()
                self.assertLess(int(p[2], 16)+int(p[5], 16), 0x80ff0000)


if __name__ == '__main__':
    unittest.main()
