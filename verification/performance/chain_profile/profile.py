#!/usr/bin/env python3
"""Reconcile checked RTL records into a scoped inference-chain profile.

This tool runs no simulator and changes no input. Historical measurements are
never promoted to a new current-SoC or whole-model performance result.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
RUNTIME = Path('/home/wangwy/llama/llama.cpp')
DEFAULT_EVIDENCE = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
PHASES = tuple('phase_' + name + '_cycles' for name in (
    'setup', 'activation', 'weight', 'compute', 'overlap', 'drain',
    'scheduler', 'commit', 'fault', 'terminal'))
COUNTS = (
    'busy_cycles', 'dot_active_cycles', 'useful_pairs', 'pair_capacity', 'tiles',
    'probe_compute_without_dot_issue_cycles', 'weight_prefetch_wait_cycles',
    'probe_context_start_blocked_cycles', 'probe_profile_result_blocked_cycles',
    'probe_fp_input_blocked_cycles', 'probe_read_ar_ready_blocked_cycles',
    'probe_read_ar_slot_blocked_cycles', 'probe_read_data_sink_blocked_cycles',
    'probe_profile_correction_pending_cycles', 'probe_profile_result_pending_cycles',
    'fp_table_full_cycles', 'activation_bytes', 'weight_bytes',
    'context_fill_count', 'context_reuse_count', *PHASES)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def numeric_fields(line, prefix):
    require(line.startswith(prefix), 'Wrong record prefix')
    result = {}
    for token in line[len(prefix):].split():
        key, value = token.split('=', 1)
        require(key not in result and value.isdecimal(), 'Invalid/duplicate field: ' + key)
        result[key] = int(value)
    return result


def checked_run(directory):
    receipt = json.loads((directory / 'result.json').read_text())
    require(receipt.get('state') == 'PASS' and receipt.get('post_pins_match') is True
            and receipt.get('performance_measured') is True, 'No checked RTL result')
    pins_file = directory / 'source-pins.json'
    require(digest(pins_file) == receipt['source_pins_sha256'], 'Original pins changed')
    pins = json.loads(pins_file.read_text())
    log = directory / 'work/run.vcs.log'
    trace = directory / 'work/vector_trace.csv'
    protocol_file = directory / 'work/uvm_result.json'
    protocol = json.loads(protocol_file.read_text())
    require(protocol.get('status') == 'PASS' and protocol.get('issues') == [],
            'Independent protocol result failed')
    require(protocol['elf_sha256'] == receipt['elf_sha256'], 'ELF identity disagreement')
    require(protocol['log_sha256'] == digest(log), 'Raw log changed')
    require(protocol['vector_trace_sha256'] == digest(trace), 'Vector trace changed')
    executables = [Path(p) for p, h in pins.items() if h == receipt['elf_sha256']]
    require(executables and all(p.is_file() and digest(p) == receipt['elf_sha256']
                               for p in executables), 'Measured ELF changed/missing')
    evidence = {str(p): digest(p) for p in
                (directory / 'result.json', pins_file, log, trace, protocol_file, *executables)}
    return receipt, pins, log.read_text(), evidence


def source_comparison(pins):
    """Report drift rather than relaxing or rewriting the original source pins."""
    rows = []
    for original, expected in pins.items():
        parts = original.split('/')
        target = None
        for checkout in ('ara_dsa_signoff_integration', 'ara_dsa'):
            if checkout in parts:
                relative = Path(*parts[parts.index(checkout) + 1:])
                if relative.parts[:2] in (('hardware', 'src'), ('hardware', 'include'),
                                          ('software', 'qbs'), ('software', 'akv')):
                    target = ROOT / relative
                break
        if original.startswith(str(RUNTIME / 'ggml') + '/'):
            target = Path(original)
        if target is None or target.suffix not in ('.sv', '.svh', '.v', '.h', '.c', '.cpp', '.S'):
            continue
        actual = digest(target) if target.is_file() else None
        rows.append(dict(original=original, current=str(target), expected_sha256=expected,
                         current_sha256=actual,
                         status='MATCH' if actual == expected else 'MISSING' if actual is None else 'DIFFERENT'))
    return dict(matched=sum(r['status'] == 'MATCH' for r in rows),
                different=sum(r['status'] == 'DIFFERENT' for r in rows),
                missing=sum(r['status'] == 'MISSING' for r in rows), files=rows,
                whole_soc_equivalence_established=False,
                note='Selected source identity only; not dependency/configuration/whole-image equivalence.')


def projection_profile(text, accepted_trials):
    pending, trials, sequence = [], [], 0
    for line in text.splitlines():
        if line.startswith('[QBS_PERF] '):
            p = numeric_fields(line, '[QBS_PERF] ')
            sequence += 1
            require(p['seq'] == sequence and (p['m'], p['n'], p['vlen'], p['lanes']) ==
                    (4, 32, 1024, 4), 'Command sequence/shape mismatch')
            require((p['success'], p['fault'], p['validation_fault'], p['read_fault']) ==
                    (1, 0, 0, 0), 'Failed native command')
            require(all(k in p for k in COUNTS), 'Missing required counter')
            require(sum(p[k] for k in PHASES) == p['busy_cycles'], 'Nonexclusive/incomplete phases')
            require(0 < p['useful_pairs'] <= p['pair_capacity'] == 32 * p['dot_active_cycles'],
                    'Invalid issue capacity')
            require(p['probe_compute_without_dot_issue_cycles'] + p['dot_active_cycles'] ==
                    p['phase_compute_cycles'] + p['phase_overlap_cycles'], 'Compute accounting')
            pending.append(p)
        elif line.startswith('M4_SUMS_QKV_TRIAL '):
            trial = numeric_fields(line, 'M4_SUMS_QKV_TRIAL ')
            index = len(trials)
            require(index < 4 and trial == accepted_trials[index] and len(pending) == 64,
                    'Trial does not reproduce checked result')
            require(trial['candidate'] == (0, 1, 1, 0)[index] and not trial['errors'],
                    'ABBA order/failure')
            counts = {k: sum(p[k] for p in pending) for k in COUNTS}
            require(counts['busy_cycles'] <= trial['execute'] <= trial['total'], 'ROI containment')
            require(sum(trial[k] for k in ('admit', 'prep', 'execute')) <= trial['total'],
                    'Phase intervals exceed total')
            trials.append(dict(trial=trial, commands=len(pending), counts=counts))
            pending = []
    require(not pending and len(trials) == 4 and sequence == 256, 'Incomplete/extra commands')
    selected = trials[1:3]
    mean = lambda values: sum(values) / len(values)
    timing = {k: mean([t['trial'][k] for t in selected]) for k in ('admit', 'prep', 'execute', 'total')}
    counts = {k: mean([t['counts'][k] for t in selected]) for k in COUNTS}
    exclusive = dict(admission=timing['admit'], preparation=timing['prep'],
                     native_engine_busy=counts['busy_cycles'],
                     execute_outside_engine_busy=timing['execute'] - counts['busy_cycles'],
                     other_timed_boundary=timing['total'] - timing['admit'] - timing['prep'] - timing['execute'])
    require(abs(sum(exclusive.values()) - timing['total']) < 0.01, 'Complete-slice partition')
    noissue = counts['probe_compute_without_dot_issue_cycles']
    return dict(scope='M4 K1536 full Q/V/K output slice; not a layer/model',
                selected_trials=[1, 2], timing_mean_cycles=timing, counts_mean=counts,
                complete_slice_partition=[dict(name=k, cycles=v, fraction=v / timing['total'])
                                          for k, v in exclusive.items()],
                dot_issue_per_busy=counts['dot_active_cycles'] / counts['busy_cycles'],
                issued_pair_fill=counts['useful_pairs'] / counts['pair_capacity'],
                compute_no_issue_per_tile=noissue / counts['tiles'],
                idealized_compute_no_issue_elimination_speedup=timing['total'] / (timing['total'] - noissue),
                hardware_context_capacity_bytes=4672,
                activation_payload_per_command_bytes=7008,
                hardware_context_eligible_for_this_shape=False,
                trials=trials,
                interpretation='Pending/full counters overlap activity, not additive stalls. '
                'execute-minus-busy is unclassified, not proven software/pre-drain cost. '
                'Idealized savings are conditional budgets, not measured gains.')


def attention_structure(heads, dim, tokens):
    require(0 < heads <= 8 and 32 <= dim <= 256 and dim % 32 == 0 and tokens > 0,
            'Unsupported structural geometry')
    return dict(heads=heads, dim=dim, tokens=tokens,
                output_update_read_write_bytes=2 * heads * dim * 4 * tokens,
                final_output_bytes=heads * dim * 4,
                q8_0_value_payload_bytes=tokens * (dim // 32) * 34,
                output_update_to_final_write_ratio=2 * tokens,
                classification='Source-derived logical work; NOT AXI/DDR byte measurements or cycle shares.')


def board_timing(cases):
    require(len(cases) == 4 and len({c['name'] for c in cases}) == 4,
            'Expected four distinct board cases')
    keys = ('prompt_eval_seconds', 'decode_eval_seconds',
            'inference_seconds', 'host_elapsed_seconds')
    totals = {mode: dict.fromkeys(keys, 0.0) for mode in ('baseline', 'candidate')}
    for case in cases:
        require(case['prompt_tokens'] > 0 and case['generated_tokens'] > 0, 'Empty model workload')
        for mode in totals:
            row = case['metrics'][mode]
            require(all(isinstance(row[k], (int, float)) and 0 < row[k] < 1e9 for k in keys),
                    'Invalid board elapsed time')
            require(row['host_elapsed_seconds'] >= row['inference_seconds'] >=
                    row['prompt_eval_seconds'] + row['decode_eval_seconds'], 'Nested board time disagreement')
            for key in keys:
                totals[mode][key] += row[key]
    speedups = {k: totals['baseline'][k] / totals['candidate'][k] for k in keys}
    residual = {mode: totals[mode]['host_elapsed_seconds'] - totals[mode]['inference_seconds']
                for mode in totals}
    return dict(totals=totals, aggregate_speedups=speedups,
                outside_inference_seconds=residual,
                candidate_outside_inference_fraction=residual['candidate'] /
                totals['candidate']['host_elapsed_seconds'],
                interpretation='Host-minus-inference includes unclassified loading/transport/setup work. '
                'It is not isolated model-loading time. Same-bitstream software pair, not no-QBS vs QBS.')


def board_profile(directory):
    receipt_file = directory / 'result.json'
    pins_file = directory / 'source-pins.json'
    receipt = json.loads(receipt_file.read_text())
    require(receipt.get('state') == 'FOUR_ORIGINAL_CASES_FINAL_SOFTWARE_AND_M4_CHECKED'
            and receipt.get('worker_source_pins_match') is True
            and receipt.get('measurement_environment') == 'FPGA'
            and receipt.get('hardware_rtl_unchanged') is True
            and receipt.get('all_four_answers_equal') is True
            and receipt.get('all_four_native_counts_equal') is True, 'Unaccepted board observation')
    pins = json.loads(pins_file.read_text())
    require(pins and all(Path(p).is_file() and digest(p) == h for p, h in pins.items()),
            'Original frozen board-observer input drift')
    timing = board_timing(receipt['cases'])
    require(timing['totals'] == receipt['totals'] and
            timing['aggregate_speedups'] == receipt['aggregate_speedups'], 'Board arithmetic mismatch')
    return dict(measured_run=str(directory), **timing, cases=receipt['cases'],
                original_frozen_inputs_rehashed=len(pins),
                current_software_or_rtl_equivalence_established=False,
                scope=receipt['scope'], limits=receipt['limits']), {
                    str(receipt_file): digest(receipt_file), str(pins_file): digest(pins_file), **pins}


def git_identity(directory):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(directory), *args], text=True).strip()
    return dict(directory=str(directory), branch=git('branch', '--show-current'),
                head=git('rev-parse', 'HEAD'), tree=git('rev-parse', 'HEAD^{tree}'),
                tracked_worktree_status=git('status', '--short', '--untracked-files=no'))


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--evidence-root', type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument('--board-observer', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    require(not out.exists() and out.is_relative_to(DEFAULT_EVIDENCE.resolve()),
            'Use a fresh directory in the sole verification worktree output')
    evidence_root = args.evidence_root.resolve(strict=True)
    result = dict(state='READ_ONLY_PROFILE_COMPLETE', new_simulations=0, production_changes=False,
                  current_full_soc_measurement=False, whole_model_cycle_attribution=False,
                  repositories=dict(ara=git_identity(ROOT), llama=git_identity(RUNTIME)))
    artifacts = {}
    projection_run = evidence_root / 'qbs-retire-projection-vcs-20261029-01'
    receipt, pins, text, checked = checked_run(projection_run)
    artifacts.update(checked)
    checker_path = ROOT / 'verification/qbs/m4_group_sums/projection/check.py'
    checker = load_module('chain_projection_check', checker_path)
    measured = checker.check_output(text)
    measured['traffic'] = checker.check_trace(projection_run / 'work/vector_trace.csv')
    require(measured == receipt['measured'], 'Projection acceptance replay differs')
    projection = projection_profile(text, measured['trials'])
    projection.update(measured_run=str(projection_run), source_comparison=source_comparison(pins))
    result['projection'] = projection

    attention_run = evidence_root / 'register-retirement-final-20261029-01'
    receipt, pins, text, checked = checked_run(attention_run)
    artifacts.update(checked)
    prefill = ROOT / 'verification/akv/quantized_kv/prefill'
    sys.path.insert(0, str(prefill))
    attention_checker = ROOT / 'verification/akv/quantized_kv/register_pv/check_native.py'
    checker = load_module('chain_attention_check', attention_checker)
    golden = evidence_root / 'quant-prefill-capture-20261028-01/q4_0/prefill/block/kqv_out-0.bin'
    require(pins.get(str(golden)) == digest(golden), 'Attention captured golden identity')
    measured = checker.check_log(text, golden.read_bytes(), 1)
    require(measured == receipt['measured'], 'Attention acceptance replay differs')
    offload_path = ROOT / 'verification/akv/quantized_kv/register_pv/analyze_trace.py'
    offload = load_module('chain_attention_offload', offload_path).analyze(text.splitlines(), 2000000)
    result['attention'] = dict(measured_run=str(attention_run), measured=measured,
                               source_comparison=source_comparison(pins), uart_window_offloads=offload,
                               structure=attention_structure(2, 128, 20),
                               qbs_busy_roi_available=False,
                               note='Quantized KV path, not F16 AKV. UART windows include setup/checking; '
                               'offloads are not timed-ROI IPC. No hardware-QK percentage is inferred.')
    if args.board_observer is not None:
        result['board'], checked = board_profile(args.board_observer.resolve(strict=True))
        artifacts.update(checked)
    artifacts[str(golden)] = digest(golden)
    for path in (Path(__file__), checker_path, attention_checker,
                 prefill / 'check_selector_native.py', offload_path):
        artifacts[str(path)] = digest(path)
    result['evidence_sha256'] = artifacts
    out.mkdir(parents=True)
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    with (out / 'projection_partition.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=('name', 'cycles', 'fraction'))
        writer.writeheader()
        writer.writerows(projection['complete_slice_partition'])
    with (out / 'source_comparison.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=('scope', 'original', 'current', 'status',
                                                   'expected_sha256', 'current_sha256'))
        writer.writeheader()
        for scope in ('projection', 'attention'):
            writer.writerows(dict(scope=scope, **row) for row in result[scope]['source_comparison']['files'])
    print(json.dumps(dict(state=result['state'], output=str(out), new_simulations=0,
                          projection_mean=projection['timing_mean_cycles'],
                          attention_candidate=measured['candidate_cycles']), indent=2))


if __name__ == '__main__':
    main()
