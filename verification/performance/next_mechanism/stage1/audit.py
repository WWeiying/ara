#!/usr/bin/env python3
"""Reconcile archived measurements without promoting observations to acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path('/home/wangwy/fpga_runs')
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
UNIFIED = ROOT / 'fpga_unified_board_20261108_01/acceptance_report_07'
REPLAY = ROOT / 'qbs_akv_mechanism_stage1_20261108_01/evidence_01/campaign'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def checked_manifest(root, rows):
    pins = {}
    for row in rows:
        path = (root / row['path']).resolve(strict=True)
        require(path.is_relative_to(root.resolve()), 'Manifest escapes evidence root')
        require(str(path) not in pins, 'Duplicate manifest entry')
        require(sha(path) == row['sha256'], 'Evidence changed: ' + str(path))
        pins[str(path)] = row['sha256']
    require(pins, 'Empty manifest')
    return pins


def phases(metrics, stdout):
    require(metrics['kind'] == 'fixed_history_replay_not_free_generation', 'Wrong workload')
    require(metrics['worker_count'] == 1 and metrics['kv'] == 'f16/f16', 'Wrong configuration')
    count = metrics['single_token_evaluations']
    rows = metrics['phases']
    require(count > 0 and len(rows) == count + 1, 'Incomplete phase records')
    require(rows[0]['phase'] == 'prefill' and rows[0]['eval_tokens'] == metrics['prompt_tokens'],
            'Missing prompt interval')
    require([r.get('step') for r in rows[1:]] == list(range(count)) and
            all(r['phase'] == 'decode' for r in rows[1:]), 'Missing or duplicate decode')
    expected = [f"STAGE1_PROGRESS prefill tokens={metrics['prompt_tokens']} ns={rows[0]['compute_ns']}"]
    expected += [f"STAGE1_PROGRESS decode={i+1}/{count} ns={r['compute_ns']}"
                 for i, r in enumerate(rows[1:])]
    require([r for r in stdout.splitlines() if r.startswith('STAGE1_PROGRESS ')] == expected,
            'Raw phase timing mismatch')
    require(stdout.splitlines().count('STAGE1_MODEL_COMPLETED') == 1, 'No unique completion')
    prefill, decode = rows[0]['compute_ns'], sum(r['compute_ns'] for r in rows[1:])
    require(all(r['compute_ns'] > 0 for r in rows) and
            prefill == metrics['prefill_compute_ns'] and decode == metrics['decode_compute_ns'],
            'Inconsistent time totals')
    require(metrics['inference_window_ns'] >= prefill + decode, 'Impossible inference window')
    return dict(prefill_seconds=prefill / 1e9, decode_seconds=decode / 1e9,
                compute_seconds=(prefill + decode) / 1e9,
                non_compute_window_seconds=(metrics['inference_window_ns'] - prefill - decode) / 1e9,
                model_load_seconds=metrics['model_load_ns'] / 1e9,
                context_init_seconds=metrics['context_init_ns'] / 1e9,
                prompt_tokens=metrics['prompt_tokens'], decode_evaluations=count,
                operator_times_measured=False)


def pv_boundary(log, worker):
    matches = re.findall(r'^PV_BOUNDARY_DONE cases=(\d+) successes=(\d+) rejected=(\d+) compat=(\d+) errors=(\d+)$',
                         log, re.MULTILINE)
    require(len(matches) == 1, 'Missing boundary terminal record')
    values = dict(zip(('cases', 'success_attempts', 'reject_attempts', 'compat', 'firmware_errors'),
                      map(int, matches[0])))
    require(worker['state'] == 'FAIL' and values['firmware_errors'] > 0 and
            'Core Test *** FAILED ***' in log, 'Unexpected boundary state; review evidence')
    return dict(**values, state='FAIL', deployment_approved=False,
                root_cause='not established by this planning audit',
                note='success_attempts is the firmware attempt counter, not 21 verified PASS cases')


def collect():
    manifest = UNIFIED / 'SHA256SUMS'
    rows = [dict(sha256=line[:64], path=line[66:]) for line in manifest.read_text().splitlines()]
    pins = checked_manifest(UNIFIED, rows)
    pins[str(manifest)] = sha(manifest)
    replay_manifest = REPLAY / 'MANIFEST.json'
    pins.update(checked_manifest(REPLAY, read(replay_manifest)))
    pins[str(replay_manifest)] = sha(replay_manifest)
    observations = {}
    for arm in ('qbs_only', 'qbs_akv'):
        directory = REPLAY / 'qwen3' / arm
        require((directory / 'exit_code').read_text().strip() == '0', 'Replay exit failure')
        observations[arm] = phases(read(directory / 'metrics.json'), (directory / 'stdout.log').read_text())
    require(read(REPLAY / 'qwen3/qbs_only/inputs.json') == read(REPLAY / 'qwen3/qbs_akv/inputs.json'),
            'Replay input mismatch')
    numeric = read(REPLAY / 'qwen3/numerical_comparison.json')
    require(numeric['bitwise_equal'] is False and numeric['differing_values'] > 0,
            'Numerical review state changed; review rather than automatically accept')
    qbs_work = []
    for arm in ('qbs_only', 'qbs_akv'):
        coverage = read(REPLAY / 'qwen3' / arm / 'result.json')['coverage']
        work = {}
        for fmt in ('Q4_K', 'Q6_K'):
            row = coverage['GGML_RISCV_QBS_EXEC:' + fmt]
            require(row['emulated_commands'] == 0 and row['dot_elements'] == row['command_dot_elements'],
                    'QBS work or native-mode mismatch')
            work[fmt] = {k: row[k] for k in ('native_qbexec', 'command_dot_elements')}
        qbs_work.append(work)
    require(qbs_work[0] == qbs_work[1], 'Different projection work in replay arms')
    unified = read(UNIFIED / 'analysis/summary.json')
    boundary = OUT / 'resident_pv_soc_boundary_vcs_20261109_01'
    pv = OUT / 'resident_pv_soc_abba_vcs_20261109_01/result.json'
    attr = OUT / 'resident_pv_soc_attribute_20261109_01/report.json'
    evidence = [boundary / 'result.json', boundary / 'work/run.vcs.log', pv, attr]
    pins.update({str(p): sha(p) for p in evidence})
    accepted = read(pv)
    require(accepted['state'] == 'PASS' and accepted['numerical_checked'] and
            accepted['independent_protocol_checked'], 'PV focused performance evidence not accepted')
    return dict(schema_version=1, state='AUDITED_STAGE1_INCOMPLETE',
        accepted_unified_phase_means={arm: {phase: unified['groups'][arm][phase]['mean']
            for phase in ('prefill_seconds', 'decode_seconds', 'inference_seconds')}
            for arm in ('accepted', 'generic', 'auto')},
        fixed_history_observations=observations,
        fixed_history_numerics=numeric, fixed_history_qbs_work=qbs_work[0],
        fixed_history_quality_acceptance=False,
        numerical_note='Differences need an independent numerical contract; neither automatic PASS nor proof of an RTL bug.',
        resident_pv_focused=accepted['numerical'],
        resident_pv_boundary=pv_boundary((boundary / 'work/run.vcs.log').read_text(), read(boundary / 'result.json')),
        source_pins=pins, model_operator_time_ranking=None,
        open_gates=['Current optimized model operator times, separately for prefill/decode',
                    'Low-overhead probe ON/OFF identity, numerical and measurement validation',
                    'Use measured fractions to finalize the second-mechanism priority'],
        no_new_rtl_or_simulation=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = collect()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('state', 'fixed_history_observations', 'resident_pv_boundary', 'open_gates')}, indent=2))


if __name__ == '__main__':
    main()
