#!/usr/bin/env python3
"""Count emitted loop instructions and read existing gap49 trace; no execution."""
import argparse
import bisect
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
OLD = OUT / 'gap49-payload-preflight-20261004-01'
RUN = OUT / 'gap48-current-20261004-01/results/qbs_gap49_payload_skew'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def disassembly(path):
    instructions, symbols = {}, []
    for line in path.read_text().splitlines():
        match = re.match(r'([0-9a-f]+):', line)
        if match:
            instructions[int(match[1], 16)] = line
        match = re.fullmatch(r'([0-9a-f]+) <([^>]+)>:', line)
        if match:
            symbols.append((int(match[1], 16), match[2]))
    return instructions, symbols


def analyze(preflight):
    summary = RUN / 'summary.json'
    directory = Path(read(summary)[0]['artifact_dir'])
    trace, trace_summary = directory / 'commit_trace.csv', directory / 'trace_summary.json'
    old_dump = OLD / 'dut.disassembly.log'
    new_dump = preflight / 'dut.disassembly.log'
    elf_proof = preflight / 'elf-proof.json'
    rows = list(csv.DictReader(trace.open()))
    retired = [r for r in rows if r['event'] == 'retire']
    counts = Counter(int(r['pc'], 16) for r in retired)
    old_instructions, old_symbols = disassembly(old_dump)
    addresses = [p for p, _ in old_symbols]
    functions = Counter()
    for pc, count in counts.items():
        functions[old_symbols[bisect.bisect_right(addresses, pc) - 1][1]] += count
    measured = read(trace_summary)
    assert len(retired) == measured['retire_count'] == 73320
    elapsed = read(summary)[0]['elapsed_s']
    assert read(summary)[0]['status'] == 'PASS' and measured['status'] == 'VALID'
    old_groups = []
    for name, start, end in [
            ('VRF_seed', 0x800011a2, 0x800011ac),
            ('full_VRF_checks', 0x800012dc, 0x8000139e),
            ('weight_byte_checks', 0x8000147e, 0x80001494),
            ('activation_byte_checks', 0x800014ca, 0x800014de),
            ('descriptor_byte_checks', 0x80001514, 0x80001528)]:
        old_groups.append(dict(name=name, first_pc=hex(start), last_pc=hex(end),
            retired=sum(n for pc, n in counts.items() if start <= pc <= end)))
    events = {r['event']: int(r['cycle']) for r in rows if r['insn'] == '00b5045b'}
    instructions, symbols = disassembly(new_dump)
    terms = []
    # These closed straight-line loop bodies are reviewed for this exact ELF.
    for name, start, end, body, trips in [
            ('VRF_initial_expected_poison', 0x8000178e, 0x800017a2, 10, 4 * 512),
            ('active_output_overlay', 0x800017f2, 0x80001814, 14, 28),
            ('VRF_guard_setup', 0x80001830, 0x80001852, 13, 4 * 16),
            ('full_output_VRF_OR_XOR', 0x80001aec, 0x80001afe, 8, 4 * 512),
            ('full_initial_VRF_OR_XOR', 0x80001b62, 0x80001b72, 8, 4 * 512),
            ('all_VRF_guards', 0x80001bc0, 0x80001bf6, 21, 4 * 16),
            ('full_weight_image_OR_XOR', 0x80001cee, 0x80001cfc, 7, 4 * 100),
            ('full_activation_image_OR_XOR', 0x80001d3e, 0x80001d4c, 7, 4 * 312),
            ('aligned_copies_including_descriptor', 0x8000123e, 0x8000124a, 6, 4 * (100 + 312 + 18)),
            ('descriptor_CSR_and_narrow_expected_memset', 0x8000128a, 0x80001292, 4,
             4 * (18 + 12) + (4 + 3 + 2) * 16)]:
        actual = [(pc, line) for pc, line in instructions.items() if start <= pc <= end]
        assert len(actual) == body, (name, len(actual), body)
        assert re.search(hex(start) + r'\b', instructions[end]), name
        terms.append(dict(name=name, first_pc=hex(start), last_pc=hex(end),
            instructions_per_trip=body, trips=trips, retired_model=body * trips))
    loop_retired = sum(t['retired_model'] for t in terms)
    main_start = next(pc for pc, name in symbols if name == 'main')
    next_start = min((pc for pc, _ in symbols if pc > main_start), default=max(instructions) + 4)
    # Deliberately loose allowance: count all emitted main instructions four times,
    # including failure-only branches and one extra copy of every loop body.
    main_allowance = 4 * sum(main_start <= pc < next_start for pc in instructions)
    printf_retired = sum(functions[n] for n in ('printf_', '_vsnprintf', '_ntoa_format', '_out_char', '_putchar'))
    lower = loop_retired + 2000 + 6 * printf_retired
    upper = loop_retired + main_allowance + 1200 + 12 * printf_retired
    # Retirement is not latency. Apply the observed gap49 CPI and a separate
    # 8x-per-command compute allowance, then a 20% host-throughput sensitivity.
    compute_allowance = 4 * 8 * (events['uop_done'] - events['arch_start'])
    cycles_per_retired = measured['last_cycle'] / measured['retire_count']
    seconds_per_cycle = elapsed / measured['last_cycle']
    seconds_low = lower * elapsed / measured['retire_count']
    seconds_high = (upper * cycles_per_retired + compute_allowance) * seconds_per_cycle * 1.20
    protected = [Path(__file__).resolve(), trace, trace_summary, summary, old_dump, new_dump, elf_proof,
                 preflight / 'host-app.log', ROOT / 'apps/common/string.c']
    return dict(status='STATIC_GAP51_COST_MODEL_CALIBRATED_TO_EXISTING_GAP49_NOT_A_BENCHMARK',
        no_simulation_or_ISA_execution=True, gap51_elf_sha256=read(elf_proof)['elf_sha256'],
        gap49_observed=dict(elapsed_s=elapsed, retired=len(retired), last_cycle=measured['last_cycle'],
            retired_by_symbol=dict(functions), source_loop_counts=old_groups,
            custom_event_cycles=events, arch_start_to_uop_done=events['uop_done'] - events['arch_start'],
            note='Existing completed trace/summary read only; this is not a full VDB/source re-admission.'),
        gap51_loop_terms=terms, loop_retired_subtotal=loop_retired,
        allowances=dict(lower_nonloop=2000, upper_all_main_times_four=main_allowance,
            upper_helpers_startup_and_custom=1200, measured_gap49_one_printf=printf_retired,
            lower_printf_multiplier=6, upper_printf_multiplier=12,
            extra_compute_cycles=compute_allowance, host_throughput_sensitivity=1.20),
        retired_review_range=[lower, upper], conditional_seconds_review_range=[seconds_low, seconds_high],
        timeout_s=600, decision='Keep one four-command app; no evidence-backed need to split after full aggregation/templates.',
        unchanged_inspection=dict(actual_vrf_words=4096, initial_vrf_words=4096,
            complete_source_bytes=13760, csr_values=48, host_checks=77, dut_checks=72,
            source_snapshots='Complete immutable ELF templates; runtime descriptor snapshot'),
        limitations=['No measured gap51 latency/retirement or VDB gain.',
            'Loop counts are exact for the reviewed straight-line bodies and PASS-path trip counts.',
            'Nonloop/printf/compute allowances are estimates, not formal worst-case bounds.',
            'Retirement-rate/CPI calibration assumes comparable instrumentation and host contention.',
            'Twenty percent sensitivity is not a guarantee against different scheduling or DUT stalls.',
            'Gap49 and gap48 artifacts were not modified; final parent checkpoint admission remains separate.'],
        input_hashes={str(p): sha(p) for p in protected})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = analyze(args.preflight.resolve())
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in
        ('loop_retired_subtotal', 'retired_review_range', 'conditional_seconds_review_range', 'timeout_s')}, indent=2))


if __name__ == '__main__':
    main()
