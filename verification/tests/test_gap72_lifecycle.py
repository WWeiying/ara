#!/usr/bin/env python3
"""Gap72 evidence fixtures, not simulator outcomes or measured coverage."""
import copy
import csv
import hashlib
import inspect
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification/coverage'), str(ROOT / 'verification')]
import audit_gap72_lifecycle as audit
import run_gap72_lifecycle_checked_extension as adapter
from ara_verify import vector_commit as vc

COMMIT = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
VECTOR = 'cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,wdata,nr_lanes,vlen_bits'.split(',')


def fixture(name):
    commit, vector = [], []
    sites = {k: dict(pc=0x80001000 + i * 8, word=w) for i, (k, w) in enumerate(audit.WORDS.items())}
    csrs = [0xc20, 0xc21, 8, 3, 15, 0x180]
    elf = dict(sites=sites, csr_sites=[dict(pc=0x80002000 + i * 8, word=c << 20 | 0x22f3, csr=c)
                                     for i, c in enumerate(csrs)])
    cycle = 1
    eew = 2 if name == audit.CASE_NAMES[0] else 1
    def c(event, seq=0, word=0, pc=0, trap=0, data=0):
        commit.append(dict.fromkeys(COMMIT, '0') | dict(cycle=str(cycle), event=event,
            order=str(seq), insn=f'{word:08x}', pc=f'{pc:016x}', trap=str(trap),
            trans_id='0', rd_wdata=f'{data:016x}'))
    def v(event, seq, word, addr=0, lane=0, data=0):
        vector.append(dict.fromkeys(VECTOR, '0') | dict(cycle=str(cycle), event=event,
            arch_seq=str(seq), insn=f'{word:08x}', nr_lanes='4', vlen_bits='1024', eew=str(eew),
            addr=str(addr), lane=str(lane), be='ff' if event == 'write' else '00',
            wdata=f'{data:016x}', use_vd='1', vd=str(word >> 7 & 31), vl='64', vstart='0'))
    v('config', 0, 0)
    def writes(seq, word, image, start, size):
        v('alloc', seq, word)
        for register in range(start // 128, (start + size) // 128):
            for vrf_word in range(4):
                for lane in range(4):
                    values = [image[register * 128 + vrf_word * 32 + vc._deshuffle_byte(lane * 8 + b, 4, eew)]
                              for b in range(8)]
                    v('write', seq, word, register * 4 + vrf_word, lane, int.from_bytes(bytes(values), 'little'))
        v('done', seq, word)
    for phase, (key, word, fault) in enumerate(audit.sequence(name)):
        seed, expected = audit.golden(name, phase)
        for group, rd in enumerate((0, 8, 16, 24)):
            seq = phase * 5 + group
            load = 0x02000007 | (rd << 7) | ((6 if eew == 2 else 5) << 12) | (12 << 15)
            c('arch_start', seq, load); c('cvx_req', seq, load)
            cycle += 1
            writes(seq, load, seed, rd * 128, 1024)
            c('cvx_resp', seq, load)
            cycle += 1
        seq = phase * 5 + 4
        c('arch_start', seq, word); c('cvx_req', seq, word)
        cycle += 1
        if expected != seed:
            writes(seq, word, expected, 1024, 128)
        else:
            v('alloc', seq, word)
            v('done', seq, word)
        c('cvx_resp', seq, word, trap=fault)
        if not fault:
            c('retire', seq, word, sites[key]['pc'])
        cycle += 1
        values = [32, 16, 0, 64, 5, 0] if eew == 2 else [64, 8, 0, 64, 5, 0]
        for s, value in zip(elf['csr_sites'], values):
            c('retire', seq, s['word'], s['pc'], data=value)
            cycle += 1
    return commit, vector, elf


class Gap72(unittest.TestCase):
    def trace(self, name, change=None):
        commits, vectors, elf = fixture(name)
        if change:
            change(commits, vectors, elf)
        with tempfile.TemporaryDirectory(prefix='gap72-fixture-') as directory:
            paths = [Path(directory) / n for n in ('commit.csv', 'vector.csv')]
            for path, fields, rows in zip(paths, (COMMIT, VECTOR), (commits, vectors)):
                with path.open('w') as stream:
                    writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
            return audit.trace_oracle(*paths, elf, name)

    def test_qbs_fixture(self):
        self.assertEqual(self.trace(audit.CASE_NAMES[0])['exceptions'], 2)

    def test_akv_fixture(self):
        self.assertEqual(len(self.trace(audit.CASE_NAMES[1])['independent_vrf']), 7)

    def test_runtime_trace_json_round_trip(self):
        for name in audit.CASE_NAMES:
            trace = self.trace(name)
            self.assertEqual(json.loads(json.dumps(trace)), trace)

    def test_write_before_request_handshake(self):
        def change(c, v, e):
            req = next(r for r in c if r['event'] == 'cvx_req' and int(r['insn'], 16) & 127 == 91)
            req['cycle'] = str(int(req['cycle']) + 1)
        self.trace(audit.CASE_NAMES[0], change)

    def test_write_after_early_response(self):
        def change(c, v, e):
            resp = next(r for r in c if r['event'] == 'cvx_resp' and
                        int(r['insn'], 16) == audit.WORDS['gap72_akv_load_site'])
            resp['cycle'] = str(int(resp['cycle']) - 1)
        self.trace(audit.CASE_NAMES[1], change)

    def test_write_after_backend_done(self):
        def change(c, v, e):
            index = next(i for i, r in enumerate(v) if r['event'] == 'write' and int(r['insn'], 16) & 127 == 91)
            row = copy.deepcopy(v[index])
            done_index = next(i for i in range(index, len(v)) if v[i]['event'] == 'done')
            row['cycle'] = str(int(v[done_index]['cycle']) + 1)
            v.insert(done_index + 1, row)
        with self.assertRaisesRegex(ValueError, 'backend lifetime'):
            self.trace(audit.CASE_NAMES[0], change)

    def test_done_before_same_cycle_final_write(self):
        def change(c, v, e):
            index = next(i for i, r in enumerate(v) if r['event'] == 'write' and int(r['insn'], 16) & 127 == 91)
            done_index = next(i for i in range(index, len(v)) if v[i]['event'] == 'done')
            v.insert(index, v.pop(done_index))
        self.trace(audit.CASE_NAMES[0], change)

    def test_missing_nonwriting_custom_lifecycle(self):
        def change(c, v, e):
            v[:] = [r for r in v if r['arch_seq'] != '9']
        with self.assertRaisesRegex(ValueError, 'allocation missing'):
            self.trace(audit.CASE_NAMES[0], change)

    def test_unbound_custom_event(self):
        def change(c, v, e):
            row = dict(next(r for r in v if int(r['insn'], 16) & 127 == 91))
            row.update(arch_seq='999', cycle=v[-1]['cycle'])
            v.append(row)
        with self.assertRaisesRegex(ValueError, 'unbound custom'):
            self.trace(audit.CASE_NAMES[0], change)

    def test_extra_custom_group(self):
        def change(c, v, e):
            row = dict(next(r for r in v if int(r['insn'], 16) & 127 == 91))
            row.update(vid='1', cycle=v[-1]['cycle'])
            v.append(row)
        with self.assertRaisesRegex(ValueError, 'extra custom'):
            self.trace(audit.CASE_NAMES[0], change)

    def test_completion_metadata_drift(self):
        def change(c, v, e):
            next(r for r in v if r['event'] == 'done' and int(r['insn'], 16) & 127 == 91)['vl'] = '123'
        with self.assertRaisesRegex(ValueError, 'metadata differs'):
            self.trace(audit.CASE_NAMES[0], change)

    def test_wrong_result(self):
        def change(c, v, e):
            row = next(r for r in v if r['event'] == 'write' and int(r['insn'], 16) & 127 == 91)
            row['wdata'] = '0000000000000001'
        with self.assertRaisesRegex(ValueError, 'numerical'):
            self.trace(audit.CASE_NAMES[0], change)

    def test_source_register_corruption(self):
        def change(c, v, e):
            row = next(r for r in v if r['event'] == 'write')
            row['wdata'] = '0000000000000000'
        with self.assertRaisesRegex(ValueError, 'seed VRF'):
            self.trace(audit.CASE_NAMES[1], change)

    def test_fault_writes(self):
        def change(c, v, e):
            row = copy.deepcopy(next(r for r in v if r['event'] == 'write' and int(r['insn'], 16) & 127 == 91))
            row.update(arch_seq='9', insn='00b5045b', cycle=str(int(v[-1]['cycle']) + 1))
            done_index = next(i for i, r in enumerate(v) if r['event'] == 'done' and r['arch_seq'] == '9')
            row['cycle'] = v[done_index]['cycle']
            v.insert(done_index, row)
        with self.assertRaisesRegex(ValueError, 'fault/nonload'):
            self.trace(audit.CASE_NAMES[0], change)

    def test_wrong_epc(self):
        def change(c, v, e):
            next(r for r in c if r['event'] == 'retire' and int(r['insn'], 16) & 127 == 91)['pc'] = '8000ffff'
        with self.assertRaisesRegex(ValueError, 'retirement PC'):
            self.trace(audit.CASE_NAMES[1], change)

    def test_missing_response(self):
        with self.assertRaises(ValueError):
            self.trace(audit.CASE_NAMES[0], lambda c, v, e: c.pop(next(i for i, r in enumerate(c) if r['event'] == 'cvx_resp')))

    def test_csr_mismatch(self):
        def change(c, v, e):
            next(r for r in c if r['event'] == 'retire' and int(r['pc'], 16) == e['csr_sites'][3]['pc'])['rd_wdata'] = '0'
        with self.assertRaisesRegex(ValueError, 'CSR values'):
            self.trace(audit.CASE_NAMES[0], change)

    def test_perf_positive(self):
        for name in audit.CASE_NAMES:
            rows = [dict(audit.perf_expected(name, i), id=i, busy_cycles=100) for i in range(audit.STEPS[name])]
            for r in rows:
                if name == audit.CASE_NAMES[0] and not r['fault']:
                    r['commit_groups'] = 1
            prefix = '[QBS_PERF]' if name == audit.CASE_NAMES[0] else '[AKV_PERF]'
            log = '\n'.join(prefix + ' ' + ' '.join(f'{k}={v}' for k, v in r.items()) for r in rows)
            self.assertEqual(len(audit.perf_records(log, name)), audit.STEPS[name])
            wrong = log.replace('validation_error=11', 'validation_error=12') if name == audit.CASE_NAMES[1] else log.replace('read_fault=5', 'read_fault=0')
            with self.assertRaises(ValueError):
                audit.perf_records(wrong, name)

    def test_software_is_not_custom(self):
        good = 'core   0: 0x80000000 (0x00000013) nop\ncore   0: 3 0x80000000 (0x00000013)\n'
        self.assertEqual(audit.software_trace(good, audit.CASE_NAMES[0])['custom_instructions'], 0)
        with self.assertRaises(ValueError):
            audit.software_trace(good.replace('00000013', '00b5045b'), audit.CASE_NAMES[0])

    def test_markers_and_scopes(self):
        for name in audit.CASE_NAMES:
            steps = audit.STEPS[name]
            log = f'G72_END operations={steps} vrf_words={steps*1024} scope=SOFTWARE_REFERENCE_ONLY\nPASSED: {name} checks={4*steps+1} errors=0\n'
            audit.validate_log(log, name, host=True)
            with self.assertRaises(ValueError):
                audit.validate_log(log, name)
            with self.assertRaises(ValueError):
                audit.validate_log(log + log, name, host=True)

    def test_abi_and_no_script_change(self):
        self.assertEqual(tuple(inspect.signature(adapter.runtime_proof).parameters), ('output', 'plan', 'row', 'proof'))
        script = adapter.checked.SCRIPT
        delegate = adapter.evidence.precheck
        hooks = adapter.install_hooks()
        self.assertIs(adapter.install_hooks(), hooks)
        self.assertEqual(adapter.checked.SCRIPT, script)
        self.assertIs(hooks['precheck'].delegate, delegate)
        self.assertEqual(len(set(adapter.CASE_NAMES)), 2)
        self.assertIsInstance(adapter.CASE_NAMES, list)
        self.assertEqual(adapter.CASE_NAMES, ['app:' + name for name in audit.CASE_NAMES])
        self.assertEqual(adapter._RAW_CASE_NAMES, audit.CASE_NAMES)

    def test_plusargs(self):
        for public_name in adapter.CASE_NAMES:
            name = public_name.removeprefix('app:')
            command = ['simv', '+TESTCASE=' + name, '+NO_FSDB', '+COMMIT_TRACE=/tmp/gap72/commit_trace.csv']
            self.assertIn('+VECTOR_TRACE=/tmp/gap72/work/vector_trace.csv', adapter.perf_command(command))
            with self.assertRaises(ValueError):
                adapter.perf_command(command + ['+AKV_PERF'])

    def test_runtime_files_exclude_static_history(self):
        with tempfile.TemporaryDirectory(prefix='gap72-scope-fixture-') as directory:
            root = Path(directory)
            target = root / 'results/qbs_gap72_fill_abort'
            vdb = target / 'tests/app_qbs_gap72_fill_abort/work/code.vdb'
            vdb.mkdir(parents=True)
            log, xml, static = target / 'stdout.log', vdb / 'cond.xml', root / 'preflight.json'
            for path in (log, xml, static):
                path.write_text('fixture\n')
            digest = hashlib.sha256(log.read_bytes()).hexdigest()
            proof = adapter.evidence.Evidence(); proof.pin(static)
            row = dict(files={str(log): digest}, vdb_files={str(xml): digest}, vdb=str(vdb))
            bound = adapter.RuntimeFiles(target, row, proof)
            bound.pin(log); bound.pin(xml, database=True)
            self.assertEqual(bound.files, {str(log): digest, str(xml): digest})
            self.assertIn(str(static), proof.files)
            self.assertNotIn(str(static), bound.files)
            self.assertTrue(all(proof.files[p] == h for p, h in bound.files.items()))

    def test_runtime_files_reject_declared_foreign_paths(self):
        with tempfile.TemporaryDirectory(prefix='gap72-scope-fixture-') as directory:
            root = Path(directory); target = root / 'results'; target.mkdir()
            foreign = root / 'static.json'; foreign.write_text('fixture\n')
            digest = hashlib.sha256(foreign.read_bytes()).hexdigest()
            row = dict(files={str(foreign): digest}, vdb_files={str(foreign): digest}, vdb=str(target))
            bound = adapter.RuntimeFiles(target, row, adapter.evidence.Evidence())
            for database in (False, True):
                with self.assertRaisesRegex(ValueError, 'out-of-scope'):
                    bound.pin(foreign, database=database)

    def test_runtime_files_reject_unchecked_bytes(self):
        with tempfile.TemporaryDirectory(prefix='gap72-scope-fixture-') as directory:
            root = Path(directory); log = root / 'stdout.log'; log.write_text('fixture\n')
            row = dict(files={str(log): '0' * 64}, vdb=str(root), vdb_files={})
            bound = adapter.RuntimeFiles(root, row, adapter.evidence.Evidence())
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                bound.pin(log)
            self.assertEqual(bound.files, {})

    def test_golden_is_independent(self):
        seed, result = audit.golden(audit.CASE_NAMES[0], 3)
        self.assertEqual(struct.unpack('<I', result[1024:1028])[0], 0x44000000)
        self.assertEqual(result[:1024], seed[:1024])
        self.assertEqual(result[1152:], seed[1152:])
        self.assertEqual(result[1028:1152], bytes(124))


if __name__ == '__main__':
    unittest.main(verbosity=2)
