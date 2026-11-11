#!/usr/bin/env python3
"""Streaming model numerical/control/AKV-content audit. Never grants execution."""
import argparse
from array import array
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct

COUNTERS = ('denied unsupported lease_denied resident_calls native_calls resident_groups '
            'native_groups completed failed legacy_calls legacy_completed legacy_fallback').split()
QBS = ('gemv_calls gemm_calls input_rows output_rows activation_elements output_elements '
       'dot_elements split_calls native_qbexec emulated_commands command_dot_elements '
       'segmented_commands context_fill context_reuse context_release').split() + [f'commands_m{i}' for i in range(1, 9)]
ARCH = dict(info='index result', begin='seq pc insn rs1 rs2 frm fflags',
            read='seq pc address bytes', end='seq pc status fflags valid tile tokens tval')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'Duplicate JSON key: ' + k); out[k] = v
        return out
    def constant(v):
        raise ValueError('Nonfinite JSON: ' + v)
    def floating(v):
        result = float(v)
        require(math.isfinite(result), 'Nonfinite JSON number')
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def fields(text, names, strings=(), hexes=()):
    row = {}
    for word in text.split():
        require(word.count('=') == 1, 'Malformed record')
        k, v = word.split('=')
        require(k in names and k not in row, 'Unknown/duplicate field: ' + k)
        if k in strings:
            require(v != '', 'Empty field'); row[k] = v
        else:
            require(re.fullmatch(r'0x[0-9a-fA-F]+' if k in hexes else r'[0-9]+', v), 'Malformed integer: ' + k)
            row[k] = int(v, 16 if k in hexes else 10)
            require(row[k] < 1 << 64, 'Integer overflow')
    require(set(row) == set(names), 'Missing fields')
    return row


def expected_resident(spec, requested, step):
    if not requested or not step or not spec['resident_decode']:
        return []
    abi = spec['abi']; pv, qk = abi['resident_pv_profile'], abi['resident_qk_profile']
    rows = spec['q_heads'] // spec['kv_heads']; result = []
    length = spec['prompt_tokens'] + step
    for _ in range(spec['layers'] * spec['kv_heads']):
        for tile in range(0, length, abi['token_axis_profile']['tile_tokens']):
            tokens = min(length - tile, 64)
            result.append(('full' if tile == 0 else 'refill', None, tile, tokens))
            for kind in ('qk', 'pv'):
                for base in range(0, rows, 2):
                    heads = min(2, rows - base)
                    control = (tokens - 1) | ((heads - 1) << pv['heads_bit']) | (
                        pv['head_dim_codes'][str(spec['head_dim'])] << pv['dimension_shift'])
                    if kind == 'qk': control |= base << qk['query_base_shift']
                    result.append((kind, control, tile, tokens))
        result.append(('release', None, tile, tokens))
    return result


class Architectural:
    def __init__(self, spec, mode, step, pcs, sequence):
        self.spec, self.pcs, self.sequence = spec, pcs, sequence
        self.expected = expected_resident(spec, mode, step)
        self.context = [r for r in expected_resident(spec, 1, step) if r[0] in ('full', 'refill', 'release')]
        self.context_index = 0
        self.index = 0; self.pending = None; self.kind = None; self.total = Counter(); self.read_index = 0
        self.mode, self.step = mode, step

    def event(self, tag, r):
        if tag == 'info':
            require(self.pending is None and r['index'] <= 4, 'INFO ordering/index')
            if r['index'] == 4: require(r['result'] == 0, 'Production capability changed')
            return
        if tag == 'begin':
            require(self.spec['head_dim'] != 256, 'D256 fallback executed AKV work')
            require(self.pending is None and r['seq'] == self.sequence + 1, 'Missing/end/sequence')
            require(r['frm'] == 0 and r['fflags'] <= 31, 'Architectural FP state')
            insn = r['insn']; abi = self.spec['abi']
            require(insn <= 0xffffffff and insn & 127 == int(abi['instruction']['opcode'], 0), 'Wrong opcode')
            f3, f7 = (insn >> 12) & 7, insn >> 25
            self.kind = None
            for kind, key in (('qk', 'resident_qk_profile'), ('pv', 'resident_pv_profile')):
                if (f3, f7) == (abi[key]['funct3'], abi[key]['funct7']): self.kind = kind
            if self.kind in ('qk', 'pv'):
                require(self.index < len(self.expected), 'Unexpected resident work in OFF/Prefill/fallback')
                want = self.expected[self.index]
                require((self.kind, r['rs1']) == want[:2], 'Resident order/control/querybase')
                require(((insn >> 7) & 31) % 4 == 0, 'Unaligned resident destination')
                if self.kind == 'qk': require(((insn >> 20) & 31) == 0, 'QK source import')
                else:
                    src, dst = (insn >> 20) & 31, (insn >> 7) & 31
                    require(src % 8 == 0 and src <= 24 and not (dst < src + 8 and src < dst + 4),
                            'PV source/destination overlap')
                if self.pcs is not None:
                    require(r['pc'] in self.pcs[self.kind], 'Resident PC outside bound ELF')
            elif f3 == abi['token_axis_profile']['fill_funct3']:
                require(f7 in (0, 1), 'Unexpected FILL encoding')
                self.kind = 'full' if f7 == 0 else 'refill'
            elif f3 == abi['instruction']['release_funct3']:
                require(f7 == 0 and ((insn >> 7) & 31) == ((insn >> 15) & 31) == ((insn >> 20) & 31) == 0,
                        'Malformed RELEASE')
                self.kind = 'release'
            elif self.expected:
                raise ValueError('Legacy column/source instruction in resident Decode')
            if self.context and self.kind in ('full', 'refill', 'release'):
                require(self.context_index < len(self.context) and
                        self.kind == self.context[self.context_index][0], 'Native/resident context order')
                if self.kind in ('full', 'refill'):
                    require(r['rs2'] == self.context[self.context_index][2], 'Wrong context tile start')
                    require(((insn >> 7) & 31) == 0, 'FILL destination encoding')
                    if self.kind == 'full': require(r['rs1'] != 0 and r['rs1'] % 64 == 0, 'Descriptor alignment')
                    else: require(((insn >> 15) & 31) == 0 and r['rs1'] == 0, 'REFILL descriptor encoding')
            if self.expected:
                require(self.index < len(self.expected) and self.kind == self.expected[self.index][0],
                        'FULL/REFILL/compute/RELEASE order')
                if self.kind in ('full', 'refill'):
                    require(r['rs2'] == self.expected[self.index][2], 'Wrong tile start')
                    if self.kind == 'full': require(r['rs1'] % 64 == 0, 'Unaligned descriptor')
            self.read_index = 0
            self.pending = r; self.sequence = r['seq']; self.total['begin'] += 1
        elif tag == 'read':
            require(self.pending is not None and (r['seq'], r['pc']) ==
                    (self.pending['seq'], self.pending['pc']) and r['bytes'] > 0 and
                    r['address'] + r['bytes'] <= 1 << 64, 'Orphan/invalid RAM read')
            require(self.kind not in ('qk', 'pv', 'release'), 'Resident/RELEASE instruction imported memory')
            if self.expected:
                want = self.expected[self.index]
                rows = self.spec['q_heads'] // self.spec['kv_heads']
                sizes = ([64] + [2 * self.spec['head_dim']] * (rows + 2 * want[3]) if self.kind == 'full'
                         else [2 * self.spec['head_dim']] * (2 * want[3]))
                require(self.read_index < len(sizes) and r['bytes'] == sizes[self.read_index], 'Wrong RAM work')
                if self.kind == 'full' and self.read_index == 0:
                    require(r['address'] == self.pending['rs1'], 'Wrong descriptor read')
            self.read_index += 1
        elif tag == 'end':
            require(self.pending is not None and (r['seq'], r['pc']) ==
                    (self.pending['seq'], self.pending['pc']), 'Orphan/mismatched END')
            require(r['status'] == 0 and r['tval'] == 0 and r['fflags'] <= 31 and
                    r['valid'] in (0, 1) and r['tokens'] <= 64, 'Fault/invalid architectural completion')
            if self.context and self.kind in ('full', 'refill', 'release'):
                want = self.context[self.context_index]
                require((r['valid'], r['tile'], r['tokens']) == (int(self.kind != 'release'), want[2], want[3]),
                        'Wrong native/resident context/tail')
                self.context_index += 1
            if self.expected:
                want = self.expected[self.index]
                require((r['valid'], r['tile'], r['tokens']) == (int(self.kind != 'release'), want[2], want[3]),
                        'Wrong resident context/tail')
                rows = self.spec['q_heads'] // self.spec['kv_heads']
                reads = 1 + rows + 2 * want[3] if self.kind == 'full' else 2 * want[3] if self.kind == 'refill' else 0
                require(self.read_index == reads, 'Missing RAM work')
                self.index += 1
            if self.kind: self.total[self.kind] += 1
            self.pending = None; self.kind = None

    def finish(self):
        require(self.pending is None and self.index == len(self.expected), 'Missing architectural work/completion')
        require(self.context_index == len(self.context), 'Missing native/resident context sequence')
        if self.step and self.spec['resident_decode']:
            groups = self.spec['layers'] * self.spec['kv_heads']
            tiles = (self.spec['prompt_tokens'] + self.step + 63) // 64
            require((self.total['full'], self.total['refill'], self.total['release']) ==
                    (groups, groups * (tiles - 1), groups), 'Resident whole-group ownership balance')
        return dict(self.total)


def counter_delta(before, after, spec, mode, step):
    require(all(after[k] >= before[k] for k in COUNTERS), 'Counter reset/wrap')
    d = {k: after[k] - before[k] for k in COUNTERS}
    require(d['failed'] == d['denied'] == d['lease_denied'] == d['unsupported'] == 0, 'Admission/SDK failure')
    require(d['completed'] == d['resident_calls'] + d['native_calls'], 'Whole-call completion mismatch')
    require(d['legacy_calls'] == d['legacy_completed'] + d['legacy_fallback'], 'Legacy completion mismatch')
    layers = spec['layers']; groups = layers * spec['kv_heads']
    expected = dict.fromkeys(COUNTERS, 0)
    if step and spec['resident_decode']:
        route = 'resident' if mode else 'native'
        expected.update({route + '_calls': layers, route + '_groups': groups, 'completed': layers})
    else:
        expected['legacy_calls'] = layers
        expected['legacy_fallback' if spec['head_dim'] == 256 else 'legacy_completed'] = layers
    require(d == expected, 'Wrong route, all-fallback positive, or extra work')
    return d


def check_lines(lines, spec, pcs=None):
    """Content check only. The release/binding/transport approval remains external."""
    mode = None; step = None; expected_mode = 0; next_step = 0; phase = None
    qbs = [{}, {}]; previous = {}; outputs = {}; comparisons = 0; terminal = False
    context_seen = False; binding_seen = False; sequence = 0; stats = []; ended = False
    for raw in lines:
        line = raw.rstrip('\r\n')
        m = re.search(r'\bakv_arch_(\w+)\s+(.+)$', line)
        if m:
            require(not terminal, 'Architectural event after terminal')
            require(m[1] in ARCH, 'Unknown architectural event')
            r = fields(m[2], ARCH[m[1]].split(), hexes={'pc', 'insn', 'rs1', 'rs2', 'address', 'tval', 'result'})
            if phase is None:
                require(m[1] == 'info' and r['index'] <= 4 and (r['index'] != 4 or r['result'] == 0), 'Unscoped native event')
            else:
                require(phase['before'] is not None and phase['after'] is None, 'Architectural event outside call snapshot')
                phase['arch'].event(m[1], r)
            continue
        if line.startswith('GGML_RISCV_QBS_EXEC '):
            require(not terminal and ended and mode is not None and step is None and next_step == 3, 'Unscoped QBS summary')
            r = fields(line.split(' ', 1)[1], ['type', *QBS], strings={'type'}); kind = r.pop('type')
            require(kind in spec['formats'] and kind not in qbs[mode], 'Unexpected/duplicate QBS format')
            require(r['native_qbexec'] > 0 and r['emulated_commands'] == 0 and
                    sum(r[f'commands_m{i}'] for i in range(1, 9)) == r['native_qbexec'] and
                    r['dot_elements'] == r['command_dot_elements'] > 0 and
                    r['context_fill'] == r['context_release'], 'QBS work/native/context balance')
            qbs[mode][kind] = r; continue
        if line.startswith('GGML_RISCV_AKV_RESIDENT_V1 '):
            require(phase is not None and phase['before'] is not None and phase['after'] is None, 'Unscoped route record')
            r = fields(line.split(' ', 1)[1], 'route requested groups dimension tokens'.split(), strings={'route'})
            require(step > 0 and spec['resident_decode'] and r == dict(route='resident' if mode else 'native',
                requested=mode, groups=spec['kv_heads'], dimension=spec['head_dim'], tokens=spec['prompt_tokens'] + step), 'Route/shape mismatch')
            phase['routes'] += 1; continue
        if not line.startswith(('STAGE5_', 'BIND_')):
            require(not re.search(r'STAGE5_|BIND_|akv_arch_|GGML_RISCV_QBS_EXEC|GGML_RISCV_AKV_RESIDENT_V1|(?i:segmentation fault|assertion .*failed|panic|illegal instruction|MODEL_FAIL)', line), 'Corrupt marker/guest failure')
            continue
        require(not terminal, 'Extra record after terminal')
        tag, body = line.split(' ', 1)
        if tag == 'BIND_ID':
            r = fields(body, ['id'], strings={'id'})
            require(not binding_seen and mode is None and re.fullmatch('[0-9a-f]{64}', r['id']), 'Binding identity')
            require(r['id'] == spec['binding_id'], 'Wrong binding identity'); binding_seen = True; continue
        require(binding_seen, 'Missing binding identity')
        if tag == 'STAGE5_MODEL_BEGIN':
            r = fields(body, ['case', 'requested'], strings={'case'})
            require(expected_mode < 2 and r == dict(case=spec['id'], requested=expected_mode), 'Model order/identity')
            require(phase is None and (mode is None or (ended and set(qbs[mode]) == set(spec['formats']))), 'Incomplete prior child')
            mode = expected_mode; expected_mode += 1; next_step = 0; context_seen = False
            ended = False
            previous = dict.fromkeys(COUNTERS, 0); continue
        if tag == 'STAGE5_CONTEXT':
            r = fields(body, 'case requested n_ctx_requested n_ctx_effective'.split(), strings={'case'})
            require(mode is not None and not ended and not context_seen and r == dict(case=spec['id'], requested=mode,
                n_ctx_requested=spec['context_capacity'], n_ctx_effective=256), 'Context allocation')
            context_seen = True; continue
        if tag == 'STAGE5_STEP_BEGIN':
            r = fields(body, 'case requested step input_rows logical_context'.split(), strings={'case'})
            require(context_seen and not ended and phase is None and next_step < 3 and r == dict(case=spec['id'], requested=mode,
                step=next_step, input_rows=spec['prompt_tokens'] if next_step == 0 else 1,
                logical_context=spec['prompt_tokens'] + next_step), 'Phase ordering/work')
            step = next_step; phase = dict(before=None, after=None, bits=array('I'), routes=0,
                                          arch=Architectural(spec, mode, step, pcs, sequence)); continue
        if tag in ('BIND_COUNTER', 'BIND_LOGITS', 'STAGE5_STEP_END'):
            require(phase is not None, 'Unscoped phase record')
            names = {'BIND_COUNTER': ['when', *COUNTERS], 'BIND_LOGITS': ['offset', 'count', 'bits'],
                     'STAGE5_STEP_END': ['greedy', 'fcsr', 'vcsr', 'vstart', 'outputs']}[tag]
            r = fields(body, ['case', 'requested', 'step', *names], strings={'case', 'when', 'bits'})
            require((r['case'], r['requested'], r['step']) == (spec['id'], mode, step), 'Wrong phase identity')
            if tag == 'BIND_COUNTER':
                when = r['when']; require(when in ('before', 'after') and phase[when] is None, 'Duplicate snapshot')
                values = {k: r[k] for k in COUNTERS}
                if when == 'before': require(values == previous, 'Counter continuity')
                else: require(phase['before'] is not None, 'Reversed snapshot')
                phase[when] = values
            elif tag == 'BIND_LOGITS':
                require(phase['after'] is not None and r['offset'] == len(phase['bits']) and
                        r['count'] == min(32, spec['vocabulary'] - r['offset']) and r['count'] > 0, 'Logit range/order')
                words = r['bits'].split(','); require(len(words) == r['count'], 'Logit count')
                for word in words:
                    require(re.fullmatch('[0-9a-f]{8}', word), 'Bad F32 bits')
                    bits = int(word, 16); require(bits & 0x7f800000 != 0x7f800000, 'Nonfinite logit')
                    phase['bits'].append(bits)
            else:
                require(phase['before'] is not None and phase['after'] is not None and
                        len(phase['bits']) == r['outputs'] == spec['vocabulary'], 'Truncated phase/logits')
                require(r['fcsr'] <= 31 and r['fcsr'] & 8 and r['vcsr'] <= 7 and r['vstart'] == 0, 'CSR state')
                values = (struct.unpack('<f', struct.pack('<I', b))[0] for b in phase['bits'])
                greedy = max(enumerate(values), key=lambda pair: pair[1])[0]
                require(r['greedy'] == greedy, 'Greedy token not derived from full logits')
                delta = counter_delta(phase['before'], phase['after'], spec, mode, step)
                require(phase['routes'] == (spec['layers'] if step and spec['resident_decode'] else 0), 'Missing/extra completed route trace')
                work = phase['arch'].finish(); sequence = phase['arch'].sequence
                record = (phase['bits'], r['greedy'], r['fcsr'], r['vcsr'], r['vstart'])
                if mode == 0: outputs[step] = record
                else: require(record == outputs[step], 'Full-logit/token/CSR OFF/ON mismatch')
                stats.append(dict(requested=mode, step=step, counters=delta, architectural=work))
                previous = phase['after']; next_step += 1; phase = None; step = None
            continue
        if tag == 'STAGE5_MODEL_END':
            r = fields(body, ['case', 'requested'], strings={'case'})
            require(not ended and phase is None and next_step == 3 and r == dict(case=spec['id'], requested=mode), 'Incomplete model end')
            ended = True
            # Child-exit QBS summaries follow this marker.
            continue
        if tag == 'STAGE5_NUMERICAL_COMPARE':
            r = fields(body, 'case step outputs bitwise csr_equal token_equal'.split(), strings={'case'})
            require(expected_mode == 2 and ended and next_step == 3 and r == dict(case=spec['id'], step=comparisons,
                outputs=spec['vocabulary'], bitwise=1, csr_equal=1, token_equal=1), 'Comparison marker')
            comparisons += 1; continue
        if tag == 'STAGE5_NUMERICAL_PAIR_ONLY':
            r = fields(body, 'case comparisons route_audit_required performance'.split(), strings={'case', 'performance'})
            require(comparisons == 3 and r == dict(case=spec['id'], comparisons=3, route_audit_required=1,
                                                  performance='not_measured'), 'Terminal marker')
            terminal = True; continue
        raise ValueError('Unknown model/binding record: ' + tag)
    require(terminal and phase is None, 'Missing terminal')
    require(all(set(s) == set(spec['formats']) for s in qbs) and qbs[0] == qbs[1], 'QBS format/work differs')
    require(all(sum(r[k] for r in qbs[0].values()) > 0 for k in ('gemv_calls', 'gemm_calls')), 'Missing model GEMV/GEMM')
    return dict(state='CONTENT_CHECKED_NOT_ACCEPTED', logits_compared=3 * spec['vocabulary'],
                phases=stats, qbs=qbs[0], resident_pcs_checked=pcs is not None,
                release_binding_checked=False, pv_prep_retirement_checked=False,
                qbs_instruction_retirement_checked=False, performance_measured=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args(); spec = read(args.spec)
    require(spec['binding_id'] is not None, 'HELD: exact approved binding identity is unresolved')
    with args.log.open() as stream: report = check_lines(stream, spec)
    report['log_sha256'] = sha(args.log)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
