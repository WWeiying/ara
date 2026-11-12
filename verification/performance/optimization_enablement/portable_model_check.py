"""Strict Refact native-QEMU pair checker; numerical limits are a reviewed contract."""
from collections import Counter
import math
import re
import struct

LIMITS = dict(max_kl=0.02, min_cosine=0.98, min_top5_overlap=0.8)


def require(ok, why):
    if not ok:
        raise ValueError(why)


def fields(line):
    result = {}
    for word in line.split()[1:]:
        key, value = word.split('=', 1)
        require(key not in result, 'Duplicate field')
        result[key] = value
    return result


def values(words):
    return [struct.unpack('<f', struct.pack('<I', word))[0] for word in words]


def metrics(reference, actual):
    a, b = values(reference), values(actual)
    top = lambda x: sorted(range(len(x)), key=lambda i: (-x[i], i))
    ta, tb = top(a), top(b)
    norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    require(norm > 0, 'Zero-norm logits')
    ma, mb = max(a), max(b)
    za = ma + math.log(sum(math.exp(x-ma) for x in a))
    zb = mb + math.log(sum(math.exp(x-mb) for x in b))
    kl = sum(math.exp(x-za) * ((x-za)-(y-zb)) for x, y in zip(a, b))
    n = min(5, len(a))
    return dict(kl=max(kl, 0.0), cosine=sum(x*y for x, y in zip(a, b))/norm,
        top5_overlap=len(set(ta[:n]) & set(tb[:n]))/n, top1=(ta[0], tb[0]),
        max_abs=max(abs(x-y) for x, y in zip(a, b)),
        bitwise_equal=reference == actual, bitwise_equal_values=sum(x == y for x, y in zip(reference, actual)))


def check(lines, symbols, model):
    vocab, layers = model['vocabulary'], model['layers']
    require(vocab >= 5 and layers > 0, 'Invalid metadata')
    pcs = {int(pc): name for name, pc in symbols.items()}
    require(set(symbols) == {'qbs', 'features'} and len(pcs) == 2, 'Trace symbols')
    mode, sequence, active, previous, stdout_mode = None, 0, None, None, False
    logits, partial = {}, []
    csr, tokens, qbs = [[], []], [[], []], [{}, {}]
    entries, cancelled = [Counter(), Counter()], [Counter(), Counter()]
    executions, fallbacks, cache, coverage = [[], []], [Counter(), Counter()], [Counter(), Counter()], [None, None]
    environments, generated, stdout_records = [None, None], [None, None], []
    exits = 0
    for raw in lines:
        line = raw.rstrip('\r\n')
        last, previous = previous, None
        if stdout_mode:
            if line.startswith('PORTABLE_STDOUT_END '):
                require(fields(line) == dict(mode=str(mode)), 'Wrong stdout owner')
                data = ''.join(stdout_records)
                require(data.endswith('\n') and len(data[:-1].encode()) == stdout_bytes, 'Truncated stdout')
                generated[mode] = data[:-1]
                stdout_mode = False
            else:
                stdout_records.append(line + '\n')
            continue
        require('Trace 0:' not in line or line.startswith('Trace 0:'), 'UART-glued trace outside captured stdout')
        if line.startswith('Stopped execution of TB chain before '):
            match = re.fullmatch(r'Stopped execution of TB chain before ((?:0x)?[0-9a-f]+) \[([0-9a-f]+)\] .*', line)
            require(match and last and (match[1], int(match[2], 16)) == last[:2], 'Unpaired cancelled TB')
            entries[last[2]][pcs[last[1]]] -= 1
            cancelled[last[2]][pcs[last[1]]] += 1
        elif line.startswith('PORTABLE_ARM_BEGIN '):
            require(mode is None and sequence < 2 and fields(line) == dict(mode=str(sequence)), 'Arm order')
            mode = sequence
        elif line.startswith('PORTABLE_ARM_END '):
            require(mode is not None and active is None and generated[mode] is not None and
                    fields(line) == dict(mode=str(mode), status='0'), 'Arm failed/incomplete')
            mode = None
            sequence += 1
        elif line.startswith('PORTABLE_ENV '):
            require(mode is not None and environments[mode] is None, 'Environment scope/duplicate')
            f = fields(line)
            require(f == dict(mode=str(mode), portable='0' if mode == 0 else 'unset',
                              master='unset', emulate='unset', qbs='unset'), 'Unexpected arm policy/emulation')
            environments[mode] = f
        elif line.startswith('PORTABLE_STDOUT_BEGIN '):
            require(mode is not None and generated[mode] is None, 'Stdout scope/duplicate')
            f = fields(line)
            require(f.keys() == {'mode', 'bytes'} and f['mode'] == str(mode) and int(f['bytes']) > 0, 'Stdout header')
            stdout_bytes, stdout_records, stdout_mode = int(f['bytes']), [], True
        elif line.startswith('PORTABLE_DECODE '):
            require(mode is not None, 'Decode outside arm')
            f = {k: int(v) for k, v in fields(line).items()}
            require(set(f) == {'step', 'rows', 'rc', 'before_fcsr', 'before_vcsr', 'before_vstart', 'fcsr', 'vcsr', 'vstart'} and
                    f['step'] == len(csr[mode]) and f['rc'] == 0 and f['vstart'] == f['before_vstart'] == 0 and
                    f['fcsr'] >> 5 == f['before_fcsr'] >> 5 == 0 and
                    f['vcsr'] == f['before_vcsr'] and 0 <= f['vcsr'] <= 7 and
                    f['before_fcsr'] & ~f['fcsr'] == 0, 'Decode/CSR contract')
            require(1 < f['rows'] <= 16 if f['step'] == 0 else f['rows'] == 1, 'Prompt/decode shape')
            csr[mode].append(f)
        elif line.startswith('PORTABLE_TOKEN '):
            require(mode is not None, 'Token outside arm')
            f = fields(line)
            require(f.keys() == {'step', 'token'} and int(f['step']) == len(tokens[mode]) and
                    0 <= int(f['token']) < vocab, 'Token record')
            tokens[mode].append(int(f['token']))
        elif line.startswith('GGML_RISCV_QBS_EXEC '):
            require(mode is not None, 'QBS outside arm')
            f = fields(line)
            kind = f.pop('type')
            data = {k: int(v) for k, v in f.items()}
            require(kind not in qbs[mode] and data['native_qbexec'] > 0 and data['emulated_commands'] == 0 and
                    all(v >= 0 for v in data.values()), 'Duplicate/non-native QBS work')
            qbs[mode][kind] = data
        elif line.startswith('GGML_RISCV_QBS_M4_SELECTED '):
            require(mode is not None, 'M4 outside arm')
            f = fields(line)
            if f.get('source') == 'cache':
                require(f.keys() == {'source', 'tag', 'event', 'k'} and int(f['tag']) in (1, 2, 3) and
                        f['event'] in ('compute_rvv', 'compute_generic', 'hit'), 'Unexpected Refact producer/tag4')
                cache[mode][(int(f['k']), int(f['tag']), f['event'])] += 1
        elif line.startswith('GGML_RISCV_AKV_EXEC '):
            require(mode == 1, 'OFF arm executed AKV')
            f = fields(line)
            require(f['mode'] == 'decode' and f['kernel'] == 'v2' and int(f['kv_heads']) == model['kv_heads'] and
                    int(f['q_rows']) == model['q_heads'] and int(f['gqa_rows']) == 32 and int(f['head_dim']) == 64 and
                    int(f['groups']) == 4 and f['portable'] == '1' and float(f['max_bias']) == 8 and
                    float(f['softcap']) == 0 and f['sinks'] == '0', 'Not the portable ALiBi/MQA32 path')
            executions[mode].append(f)
        elif line.startswith('GGML_RISCV_AKV_FALLBACK '):
            require(mode is not None, 'Fallback outside arm')
            f = fields(line)
            require(f.keys() == {'mode', 'reason', 'portable'} and f['mode'] in ('prefill', 'decode') and
                    f['reason'] == 'feature' and f['portable'] == '0', 'Unexpected fallback')
            fallbacks[mode][f['mode']] += 1
        elif line.startswith('GGML_RISCV_AKV_COVERAGE '):
            require(mode is not None and coverage[mode] is None, 'Coverage duplicate/scope')
            coverage[mode] = {k: int(v) for k, v in fields(line).items()}
        elif line.startswith('Trace '):
            match = re.fullmatch(r'Trace 0: ((?:0x)?[0-9a-f]+) \[[0-9a-f]+/([0-9a-f]+)/[0-9a-f]+/[0-9a-f]+\].*', line)
            require(mode is not None and match, 'Unscoped/wrong-hart trace')
            pc = int(match[2], 16)
            require(pc in pcs, 'Unfiltered trace')
            entries[mode][pcs[pc]] += 1
            previous = (match[1], pc, mode)
        elif line.startswith('PORTABLE_LOGITS_BEGIN '):
            f = fields(line)
            key = (mode, int(f['step']))
            require(mode is not None and active is None and key not in logits and key[1] in (0, 1) and
                    f == dict(mode=str(mode), step=str(key[1]), values=str(vocab)), 'Logits begin')
            active, partial = key, []
        elif line.startswith('PORTABLE_BITS '):
            require(active is not None, 'Unscoped logits')
            words = line.split()
            require(words[1] == 'index=' + str(len(partial)) and len(words[2:]) == min(32, vocab-len(partial)) and
                    all(re.fullmatch('[0-9a-f]{8}', word) for word in words[2:]), 'Truncated/reordered logits')
            data = [int(word, 16) for word in words[2:]]
            require(all(word & 0x7f800000 != 0x7f800000 for word in data), 'Nonfinite logits')
            partial.extend(data)
        elif line.startswith('PORTABLE_LOGITS_END '):
            require(active is not None and len(partial) == vocab and
                    fields(line) == dict(mode=str(active[0]), step=str(active[1])), 'Incomplete logits')
            logits[active], active = partial, None
        elif line.startswith('GUEST_TEST_EXIT='):
            require(line == 'GUEST_TEST_EXIT=0' and sequence == 2, 'Guest failed')
            exits += 1
    require(sequence == 2 and mode is None and active is None and not stdout_mode and exits == 1, 'Missing terminal')
    require(all(environments) and generated[0] == generated[1], 'Environment/text mismatch')
    require(len(csr[0]) == len(csr[1]) == 2 and csr[0] == csr[1], 'CSR/API mismatch')
    require(len(tokens[0]) == len(tokens[1]) == 2 and tokens[0] == tokens[1], 'Generated tokens differ/missing')
    require(set(logits) == {(a, s) for a in (0, 1) for s in (0, 1)}, 'Incomplete full vocabulary')
    numerical = []
    for step in (0, 1):
        result = metrics(logits[(0, step)], logits[(1, step)])
        require(result['top1'] == (tokens[0][step], tokens[0][step]), 'Not both greedy argmax tokens')
        require(result['kl'] <= LIMITS['max_kl'] and result['cosine'] >= LIMITS['min_cosine'] and
                result['top5_overlap'] >= LIMITS['min_top5_overlap'], 'Logit numerical limits')
        require(step != 0 or result['bitwise_equal'], 'Prefill should be unchanged')
        numerical.append(result)
    require(qbs[0] and qbs[0] == qbs[1] and {'Q4_K', 'Q6_K'} <= qbs[0].keys(), 'QBS work/type mismatch')
    require(cache[0] == cache[1], 'Projection producer work mismatch')
    for arm in (0, 1):
        require(entries[arm]['qbs'] == sum(v['native_qbexec'] for v in qbs[arm].values()), 'QBS trace/work mismatch')
        require(coverage[arm] is not None, 'Missing AKV summary')
        cov = coverage[arm]
        require(cov['candidate_ops'] == 2*layers and cov['executed_ops'] == arm*layers and
                cov['groups'] == arm*4*layers and cov['executed_decode'] == arm*layers and cov['executed_prefill'] == 0 and
                cov['fallback_feature'] == (2-arm)*layers and
                all(v == 0 for k, v in cov.items() if k.startswith('fallback_') and k != 'fallback_feature'), 'AKV candidate accounting')
    require(fallbacks[0] == Counter(prefill=layers, decode=layers) and fallbacks[1] == Counter(prefill=layers), 'Fallback path/count')
    require(len(executions[1]) == layers and entries[0]['features'] == 0 and entries[1]['features'] == 4*layers, 'Native features SDK group entries')
    require(all(int(row['active_kv']) == csr[0][0]['rows']+1 for row in executions[1]), 'Decode context mismatch')
    require(all(int(row['attention_macs']) == 2*model['kv_heads']*int(row['active_kv'])*32*64
                for row in executions[1]), 'Decode MAC accounting')
    return dict(logits_compared=2*vocab, numerical=numerical, tokens=tokens[0], csr=csr[0],
        qbs=qbs[0], native_entries=[dict(v) for v in entries], cancelled_tb=[dict(v) for v in cancelled],
        portable_decode_ops=layers, portable_groups=4*layers, generated_text=generated[0],
        instruction_retirement_claim=False, performance_measured=False)
