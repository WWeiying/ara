#!/usr/bin/env python3
"""Collect only independently accepted, completed contiguous-entry inquiries."""
import argparse
from pathlib import Path

from audit_common_attention import checked_run, s


def checked_summary(audit):
    saved = s.read_json(audit / 'result.json')
    s.require(saved.get('state') == 'INDEPENDENT_COMMON_ATTENTION_ACCEPTED' and
              saved.get('current_inputs_match') is True, 'Audit is not accepted')
    s.require(s.digest(audit / 'source-pins.json') == saved.get('source_pins_sha256'), 'Audit receipt drift')
    run = Path(saved['run']).resolve(strict=True)
    accepted, pins = checked_run(run)
    s.require(all(saved.get(key) == value for key, value in accepted.items()), 'Audit/raw replay differs')
    s.require(s.read_json(audit / 'source-pins.json') == pins, 'Audit source inventory differs')
    cycles = accepted['cycles']
    s.require(len(cycles) == 4 and all(type(c) is int and c > 0 for c in cycles), 'Wrong ABBA cycle data')
    ordinary, candidate = cycles[0] + cycles[3], cycles[1] + cycles[2]
    s.require(accepted['sums'] == {'0': ordinary, '1': candidate} and
              accepted['speedup'] == ordinary / candidate, 'Incorrect cycle arithmetic')
    comparison = accepted['comparison']
    return dict(kind=accepted['kind'], variant=comparison['variant'],
                ordinary_decoder=comparison['ordinary_value_decode'],
                candidate_decoder=comparison['candidate_value_decode'],
                decoder_implementation_matched=comparison['decoder_implementation_matched'],
                cycles=cycles, ordinary_cycle_sum=ordinary, candidate_cycle_sum=candidate,
                speedup=ordinary / candidate, cycle_reduction_percent=100 * (1 - candidate / ordinary),
                paired_outputs_exact=accepted['paired_outputs_exact'],
                paired_csr_exact=accepted['paired_csr_exact'], native_commands=16,
                mapping_timed=True, admission_timed=True, gather_timed=False,
                backend_allocation_queries_timed=False, hardware_only=False, whole_model=False,
                run=str(run), audit=str(audit),
                audit_result_sha256=s.digest(audit / 'result.json'),
                audit_source_pins_sha256=saved['source_pins_sha256'],
                original_worker_result_sha256=saved['original_worker_result_sha256'])


def combine(rows):
    identities = [(row['kind'], row['variant']) for row in rows]
    allowed = {(kind, variant) for kind in ('q8_0', 'q4_0') for variant in
               ('ORIGINAL_DECODERS', 'CANDIDATE_RVV_DECODE', 'BOTH_RVV_DECODE')}
    s.require(rows and len(set(identities)) == len(rows) and set(identities) <= allowed,
              'Duplicate or unsupported comparison identities')
    return dict(state='COMPLETED_COMMON_ATTENTION_REPLAYED', expected_comparisons=6,
                accepted_comparisons=len(rows), complete_family=len(rows) == 6,
                scope='Contiguous captured six-Query-head KV-head-0 group, D128, visible128; '
                      'not the live strided cache or model latency',
                missing_comparisons=[dict(kind=kind, variant=variant)
                                     for kind, variant in sorted(allowed - set(identities))],
                cross_elf_cost_subtraction_supported=False, rows=rows)


def markdown(result):
    lines = ['# Completed Public-Entry Attention Comparisons', '',
             'All cycle columns are sums of two measured trials within the same ELF.', '',
             '| K Format | Comparison | Ordinary Cycles | Candidate Cycles | Speedup |',
             '| --- | --- | ---: | ---: | ---: |']
    for row in result['rows']:
        lines.append(f'| {row["kind"]} | {row["variant"]} | {row["ordinary_cycle_sum"]:,} | '
                     f'{row["candidate_cycle_sum"]:,} | {row["speedup"]:.6f}x |')
    lines.extend(['', f'Accepted comparisons: {result["accepted_comparisons"]}/6. '
                  'Missing entries are not classified as failed or accepted.', '',
                  'These contiguous-operand results include mapping and admission, not K gathering '
                  'or backend allocation queries. Both-RVV uses the same V decoder on each side; '
                  'V reuse and QBS still change together. Do not label it a pure hardware ablation '
                  'or a whole-model speedup. Do not subtract cycles across different ELF layouts.', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audits, out = [path.resolve(strict=True) for path in args.audit], args.output.resolve()
    s.require(not any(out.is_relative_to(path) for path in audits), 'Independent output required')
    result = combine([checked_summary(path) for path in audits])
    pins = s.hashes([Path(__file__), Path(__file__).with_name('test_summarize_common_attention.py'),
                     *[path / name for path in audits for name in ('result.json', 'source-pins.json')]])
    out.mkdir(parents=True, exist_ok=False)
    s.atomic_json(out / 'source-pins.json', pins)
    result.update(source_pins_sha256=s.digest(out / 'source-pins.json'))
    s.atomic_json(out / 'result.json', result)
    (out / 'summary.md').write_text(markdown(result))
    print('COMPLETED_COMMON_ATTENTION_REPLAYED', result['accepted_comparisons'], 'of6')


if __name__ == '__main__':
    main()
