"""Synthetic checker mutations only; no model or native execution evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import check as c
import prepare as p

HERE = Path(__file__).resolve().parent
ABI = c.read(HERE/'akv_abi.json' if (HERE/'akv_abi.json').exists() else p.ROOT/'config/akv_abi.json')


def spec(resident=True, dimension=64):
    return dict(id='fixture', binding_id='a'*64, layers=1, q_heads=3, kv_heads=1,
                head_dim=dimension, prompt_tokens=64, context_capacity=128,
                resident_decode=resident, vocabulary=4, formats=['Q4_K'], abi=ABI)


def transcript(s):
    rows = []; sequence = 0
    def emit(tag, **r): rows.append(tag+' '+' '.join(f'{k}={v}' for k, v in r.items()))
    def event(kind, control, tile, tokens, resident):
        nonlocal sequence
        sequence += 1
        insns = dict(full=0x00b5605b, refill=0x02a0605b, release=0x0000505b,
                     qk=(3<<25)|(10<<15)|(7<<12)|0x5b,
                     pv=(2<<25)|(16<<20)|(10<<15)|(7<<12)|0x5b)
        pc = dict(full=0x100, refill=0x104, release=0x108, qk=0x200, pv=0x300)[kind]
        rs1 = control if kind in ('qk', 'pv') else 0x1000 if kind == 'full' else 0
        emit('akv_arch_begin', seq=sequence, pc=hex(pc), insn=hex(insns[kind]), rs1=hex(rs1),
             rs2=hex(tile if kind in ('full', 'refill') else 0), frm=0, fflags=8)
        if resident and kind in ('full', 'refill'):
            sizes = [2*s['head_dim']]*(2*tokens)
            if kind == 'full': sizes = [64]+[2*s['head_dim']]*(s['q_heads']//s['kv_heads'])+sizes
            for i, size in enumerate(sizes):
                emit('akv_arch_read', seq=sequence, pc=hex(pc), address=hex(0x1000 if kind == 'full' and i == 0 else 0x2000+i*512), bytes=size)
        emit('akv_arch_end', seq=sequence, pc=hex(pc), status=0, fflags=0,
             valid=int(kind != 'release'), tile=tile, tokens=tokens, tval='0x0')
    emit('BIND_ID', id=s['binding_id'])
    for mode in (0, 1):
        counts = dict.fromkeys(c.COUNTERS, 0)
        emit('STAGE5_MODEL_BEGIN', case=s['id'], requested=mode)
        emit('STAGE5_CONTEXT', case=s['id'], requested=mode, n_ctx_requested=s['context_capacity'], n_ctx_effective=256)
        for step in range(3):
            identity = dict(case=s['id'], requested=mode, step=step)
            emit('STAGE5_STEP_BEGIN', **identity, input_rows=s['prompt_tokens'] if step == 0 else 1,
                 logical_context=s['prompt_tokens']+step)
            emit('BIND_COUNTER', **identity, when='before', **counts)
            if step and s['resident_decode']:
                if mode:
                    for op in c.expected_resident(s, mode, step): event(*op, True)
                else:
                    # Synthetic native work shell, not a numerical/native fixture.
                    for _ in range(s['layers']*s['kv_heads']):
                        for tile in range(0, s['prompt_tokens']+step, 64):
                            tokens = min(64, s['prompt_tokens']+step-tile)
                            event('full' if tile == 0 else 'refill', None, tile, tokens, False)
                        event('release', None, tile, tokens, False)
                route = 'resident' if mode else 'native'
                counts[route+'_calls'] += s['layers']; counts[route+'_groups'] += s['layers']*s['kv_heads']
                counts['completed'] += s['layers']
                for _ in range(s['layers']):
                    emit('GGML_RISCV_AKV_RESIDENT_V1', route=route, requested=mode, groups=s['kv_heads'],
                         dimension=s['head_dim'], tokens=s['prompt_tokens']+step)
            else:
                counts['legacy_calls'] += s['layers']
                counts['legacy_fallback' if s['head_dim'] == 256 else 'legacy_completed'] += s['layers']
            emit('BIND_COUNTER', **identity, when='after', **counts)
            emit('BIND_LOGITS', **identity, offset=0, count=4, bits='00000000,3f800000,40400000,bf800000')
            emit('STAGE5_STEP_END', **identity, greedy=2, fcsr=9, vcsr=5, vstart=0, outputs=4)
        emit('STAGE5_MODEL_END', case=s['id'], requested=mode)
        q = dict.fromkeys(c.QBS, 0)
        q.update(gemv_calls=2, gemm_calls=1, input_rows=3, output_rows=3, activation_elements=12,
                 output_elements=12, dot_elements=100, command_dot_elements=100, native_qbexec=10,
                 context_fill=1, context_reuse=1, context_release=1, commands_m1=6, commands_m4=4)
        emit('GGML_RISCV_QBS_EXEC', type='Q4_K', **q)
    for step in range(3):
        emit('STAGE5_NUMERICAL_COMPARE', case=s['id'], step=step, outputs=4, bitwise=1, csr_equal=1, token_equal=1)
    emit('STAGE5_NUMERICAL_PAIR_ONLY', case=s['id'], comparisons=3, route_audit_required=1, performance='not_measured')
    return rows


class BindingTests(unittest.TestCase):
    def setUp(self): self.s = spec(); self.rows = transcript(self.s)

    def audit(self, rows=None, s=None, pcs=None):
        return c.check_lines(iter(self.rows if rows is None else rows), self.s if s is None else s, pcs)

    def reject_replace(self, old, new):
        text = '\n'.join(self.rows)
        self.assertIn(old, text)
        with self.assertRaises(ValueError): self.audit(text.replace(old, new, 1).splitlines())

    def test_full_content_but_never_acceptance(self):
        r = self.audit(pcs=dict(qk=[0x200], pv=[0x300]))
        self.assertEqual(r['state'], 'CONTENT_CHECKED_NOT_ACCEPTED')
        self.assertEqual(r['logits_compared'], 12)
        self.assertFalse(r['release_binding_checked'])
        self.assertFalse(r['pv_prep_retirement_checked'])

    def test_legacy_quantized_and_d256_are_not_resident(self):
        for d in (128, 256):
            s = spec(False, d); r = self.audit(transcript(s), s)
            self.assertEqual(sum(x['counters']['resident_groups'] for x in r['phases']), 0)
        s = spec(False, 256); rows = transcript(s)
        i = next(i for i, r in enumerate(rows) if 'when=before' in r)
        rows.insert(i + 1, 'akv_arch_begin seq=1 pc=0x100 insn=0xb5605b rs1=0x1000 rs2=0x0 frm=0 fflags=8')
        with self.assertRaises(ValueError): self.audit(rows, s)

    def test_odd_heads_tail_and_querybase(self):
        ops = c.expected_resident(self.s, 1, 1)
        qk = [r for r in ops if r[0] == 'qk']
        self.assertEqual([r[1] for r in qk], [127, 1087, 64, 1024])
        self.assertEqual([r[3] for r in qk], [64, 64, 1, 1])
        self.assertEqual([r[0] for r in ops], ['full','qk','qk','pv','pv','refill','qk','qk','pv','pv','release'])

    def test_one_bit_logit_mismatch(self): self.reject_replace('00000000,3f800000', '00000000,3f800001')
    def test_nonfinite_or_malformed_logits(self):
        self.reject_replace('00000000,3f800000', '7fc00001,3f800000')
        self.reject_replace('offset=0 count=4', 'offset=1 count=4')
        self.reject_replace('count=4 bits=', 'count=3 bits=')
    def test_greedy_and_csr(self):
        self.reject_replace('greedy=2', 'greedy=1')
        self.reject_replace('fcsr=9', 'fcsr=41')
        self.reject_replace('vstart=0 outputs=', 'vstart=1 outputs=')
    def test_missing_duplicate_and_extra_records(self):
        for rows in (self.rows[:-1], self.rows+[self.rows[-1]], [r for r in self.rows if not r.startswith('STAGE5_MODEL_END')]):
            with self.assertRaises(ValueError): self.audit(rows)
        self.reject_replace('when=before denied=0', 'when=before denied=0 denied=0')
    def test_counter_and_all_fallback_rejected(self):
        self.reject_replace('resident_calls=1 native_calls=0', 'resident_calls=0 native_calls=1')
        self.reject_replace('legacy_completed=1 legacy_fallback=0', 'legacy_completed=0 legacy_fallback=1')
        self.reject_replace('lease_denied=0', 'lease_denied=1')
    def test_qbs_fair_work_and_no_emulation(self):
        self.reject_replace('native_qbexec=10', 'native_qbexec=9')
        self.reject_replace('emulated_commands=0', 'emulated_commands=1')
        self.reject_replace('context_release=1', 'context_release=0')
    def test_architectural_control_flags_reads_and_completions(self):
        self.reject_replace('rs1=0x7f', 'rs1=0x27f')
        self.reject_replace('status=0', 'status=1')
        self.reject_replace('frm=0', 'frm=1')
        self.reject_replace('bytes=64', 'bytes=32')
        self.reject_replace('tile=64 tokens=1', 'tile=64 tokens=2')
        rows = list(self.rows); i = next(i for i,r in enumerate(rows) if r.startswith('akv_arch_end'))
        rows.pop(i)
        with self.assertRaises(ValueError): self.audit(rows)
    def test_native_pc_binding_is_not_assumed(self):
        self.assertFalse(self.audit()['resident_pcs_checked'])
        with self.assertRaises(ValueError): self.audit(pcs=dict(qk=[0x204], pv=[0x300]))
    def test_unknown_json_and_harness_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'x.json'
            for raw in ('{"x":0,"x":1}', '{"x":NaN}', '{"x":1e999}', '{"x":'):
                path.write_text(raw)
                with self.assertRaises(ValueError): c.read(path)
        with self.assertRaises(ValueError): p.instrument('not the sealed harness')


if __name__ == '__main__': unittest.main()
