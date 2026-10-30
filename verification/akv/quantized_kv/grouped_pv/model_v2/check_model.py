"""Paired QBS-Attention grouped OFF/ON model contract, never an all-RVV baseline."""
import re
import sys
from pathlib import Path

LEGACY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LEGACY))
from check_model_live import (Records as OriginalRecords, FAILURE, FLOAT, UINT,
                             KV_PATTERN, KV_FIELDS, QBS_PATTERN, QBS_FIELDS,
                             require, unsigned_fields)

SUITE = ('GROUPED_MODEL_SUITE_PASS profiles=2 generations=4 tokens_each=3 '
         'common_greedy_trajectory=1 baseline=qbs_attention_grouped_default_off performance=not_measured')
CALL = (rf'GGML_RISCV_QBS_CALL type=(?P<type>[A-Za-z0-9_]+) mode=(?P<mode>gemv|gemm) '
        rf'k=(?P<k>{UINT}) input_rows=(?P<input_rows>{UINT}) output_rows=(?P<output_rows>{UINT}) split_k=(?P<split_k>[01])')


class Records(OriginalRecords):
    def __init__(self, text):
        require(not FAILURE.search(text) and 'GROUPED_MODEL_FAIL' not in text, 'Guest failure text')
        reserved = ('GROUPED_MODEL', 'GGML_RISCV_QUANT_KV', 'GGML_RISCV_QBS_EXEC',
                    'GGML_RISCV_QBS_CALL', 'GUEST_TEST_EXIT')
        self.lines = [(i, line) for i, line in enumerate(re.split(r'\r?\n', text), 1)
                      if any(prefix in line for prefix in reserved) or
                      re.search(r'llama_context: n_ctx(?:\s|=|$)', line)]
        self.position = 0


def check_log(text):
    records = Records(text)
    generations, comparisons, all_calls = [], [], []
    native_calls = commands = panels = copied = decodes = prefill = 0
    vocabulary = None
    for kind, row in (('q8_0', 136), ('q4_0', 72)):
        pair = []
        for grouped, mode in enumerate(('baseline', 'candidate')):
            records.take(r'llama_context: n_ctx[ \t]+=[ \t]+256')
            records.take(f'GROUPED_MODEL_BEGIN kind={kind} mode={mode} layers=28 '
                         'prompt_tokens=4 generated=3 context=128 threads=1')
            tokens, pieces, csrs, vstate, jobs = [], [], [], [], []
            for step in range(3):
                reports, calls = 0, []
                while records.peek().startswith(('GGML_RISCV_QUANT_KV', 'GGML_RISCV_QBS_CALL')):
                    if records.peek().startswith('GGML_RISCV_QBS_CALL'):
                        call = records.take(CALL)
                        for field in ('k', 'input_rows', 'output_rows', 'split_k'):
                            call[field] = int(call[field])
                        require(all(0 < call[field] < 1 << 31 for field in ('k', 'input_rows', 'output_rows')),
                                'Invalid projection dimensions')
                        calls.append(call)
                        all_calls.append(call)
                        continue
                    start_line = records.lines[records.position][0]
                    report = unsigned_fields(records.take(KV_PATTERN), KV_FIELDS)
                    values = (1, 5, 0, 0, 0, 0, 0, 0) if step == 0 else (0, 0, 1, 1, 4, 2, 2 * (4 + step), 0)
                    require(report == dict(zip(KV_FIELDS, values)), 'Wrong quantized Attention work/fallback')
                    records.take(f'GGML_RISCV_QUANT_KV_LAYOUT selection=0 key_panels={2 if step else 0} '
                                 f'key_bytes={2 * (4 + step) * row if step else 0} workspace=13120 '
                                 f'k_token_stride={2 * row} k_head_stride={row}')
                    records.take(f'GGML_RISCV_QUANT_KV_PV grouped={grouped} completed_groups={2 if step else 0}')
                    require(records.lines[records.position - 2][0] == start_line + 1 and
                            records.lines[records.position - 1][0] == start_line + 2, 'Nonadjacent Attention trace')
                    reports += 1
                    require(reports <= 28, 'Extra Attention layer')
                    if step:
                        native_calls += 1
                        commands += 4
                        panels += 2
                        copied += 2 * (4 + step) * row
                        decodes += 2 * (4 + step)
                    else:
                        prefill += 1
                require(reports == 28 if step else reports in (0, 28), 'Missing Attention layers')
                require({'q4_K', 'q6_K'}.issubset({call['type'] for call in calls}), 'Missing native projection calls')
                jobs.append(calls)
                csr = records.take(f'GROUPED_MODEL_CSR kind={kind} mode={mode} step={step} '
                                   rf'flags=(?P<flags>{UINT}) vcsr=(?P<vcsr>{UINT})')
                flags = int(csr['flags'])
                require(flags <= 31 and flags & 8, 'Caller CSR rounding/sticky preservation failure')
                csrs.append(flags)
                vector_state = int(csr['vcsr'])
                require(vector_state <= 7, 'Invalid VCSR value')
                vstate.append(vector_state)
                token = records.take(f'GROUPED_MODEL_TOKEN kind={kind} mode={mode} step={step} '
                                     rf'token=(?P<token>{UINT}) piece_hex=(?P<piece>[0-9a-f]{{0,1024}})')
                require(len(token['piece']) % 2 == 0, 'Odd token-piece encoding')
                tokens.append(int(token['token']))
                pieces.append(token['piece'])
            end = records.take(f'GROUPED_MODEL_END kind={kind} mode={mode} generated=3 vocab=(?P<vocab>{UINT})')
            vocab = int(end['vocab'])
            require(1 < vocab < 1 << 31 and all(token < vocab for token in tokens), 'Invalid vocabulary/token')
            if vocabulary is None:
                vocabulary = vocab
            require(vocabulary == vocab, 'Vocabulary changed')
            generation = dict(kind=kind, mode=mode, tokens=tokens, piece_hex=pieces, caller_fcsr=csrs, caller_vcsr=vstate)
            generations.append(generation)
            pair.append((generation, jobs))
        require(pair[0][0]['tokens'] == pair[1][0]['tokens'] and pair[0][0]['piece_hex'] == pair[1][0]['piece_hex'],
                'Greedy trajectory changed')
        require(pair[0][0]['caller_fcsr'] == pair[1][0]['caller_fcsr'], 'Paired caller CSR changed')
        require(pair[0][0]['caller_vcsr'] == pair[1][0]['caller_vcsr'], 'Paired caller VCSR changed')
        require(pair[0][1] == pair[1][1], 'Paired projection invocation sequence/work changed')
        for step in range(3):
            metrics = records.take(f'GROUPED_MODEL_COMPARE kind={kind} step={step} common_prefix=1 '
                                   f'top1_equal=1 outputs={vocabulary} bitwise=1 csr_equal=1 '
                                   rf'max_abs=(?P<max_abs>{FLOAT}) rmse=(?P<rmse>{FLOAT}) kl=(?P<kl>{FLOAT})')
            require(all(float(value) == 0 for value in metrics.values()), 'Nonzero/nonfinite paired logits metric')
            comparisons.append(dict(kind=kind, step=step, outputs=vocabulary, bitwise=True))
    records.take(re.escape(SUITE))
    summaries = {}
    while records.peek().startswith('GGML_RISCV_QBS_EXEC'):
        record = records.take(QBS_PATTERN)
        kind = record['type']
        require(kind not in summaries, 'Duplicate projection summary')
        counters = unsigned_fields(record, QBS_FIELDS)
        calls = [call for call in all_calls if call['type'].upper() == kind]
        require(calls and counters['emulated_commands'] == 0 and counters['native_qbexec'] > 0,
                'Missing projection work or emulated projection')
        expected = dict(gemv_calls=sum(c['mode'] == 'gemv' for c in calls),
                        gemm_calls=sum(c['mode'] == 'gemm' for c in calls),
                        input_rows=sum(c['input_rows'] for c in calls),
                        output_rows=sum(c['output_rows'] for c in calls),
                        activation_elements=sum(c['k'] * c['input_rows'] for c in calls),
                        output_elements=sum(c['input_rows'] * c['output_rows'] for c in calls),
                        dot_elements=sum(c['k'] * c['input_rows'] * c['output_rows'] for c in calls),
                        split_calls=sum(c['split_k'] for c in calls))
        require(all(counters[key] == value for key, value in expected.items()), 'Projection calls/summary mismatch')
        summaries[kind] = counters
    require({'Q4_K', 'Q6_K'}.issubset(summaries) and
            {c['type'].upper() for c in all_calls} == set(summaries), 'Missing projection summaries')
    records.take('GUEST_TEST_EXIT=0')
    require(records.position == len(records.lines), 'Extra protocol records')
    require((native_calls, commands, panels, copied, decodes) == (224, 896, 448, 256256, 2464),
            'Wrong total Attention work')
    return dict(status='PASS', baseline='qbs_attention_grouped_default_off', profiles=2,
                generations=generations, comparisons=comparisons, vocab=vocabulary,
                native_calls=native_calls, native_command_attempts=commands, key_panels=panels,
                key_bytes=copied, value_decodes=decodes, prefill_fallback_reports=prefill,
                projection_calls=len(all_calls), projection_summaries=summaries,
                whole_model=True, rtl_performance=False, performance='not_measured')
