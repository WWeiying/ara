#!/usr/bin/env python3
"""Collect exact run directories without substituting an older passing result."""

import argparse
import csv
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


attention = import_file('attention_summary', ROOT / 'hardware/scripts/llama_q4km_extract/summarize-ara-attention-core.py')


def collect_rtl(root):
    results, metrics = [], []
    for state in sorted(root.glob('rtl/*/*/stage.json')):
        status = json.loads(state.read_text())
        row = {'cohort': root.name, 'case': state.parent.parent.name,
               'implementation': state.parent.name, 'status': status['status'],
               'worker_status': status['status'],
               'stage': str(state)}
        results.append(row)
        if status['status'] == 'RUNNING':
            continue
        runs = [p for p in state.parent.glob('decode_attention_core_*')
                if p.is_dir() and not p.is_symlink()]
        if len(runs) != 1:
            row.update(status='INVALID', error='expected exactly one run directory')
            continue
        run = runs[0]
        worker_log = state.parent / 'worker.log'
        shell_tail_error = (status['status'] == 'FAIL' and worker_log.exists() and
                            'unexpected EOF while looking for matching' in worker_log.read_text())
        if status['status'] != 'PASS' and not shell_tail_error:
            row['run_dir'] = str(run)
            continue
        config = attention.parse_key_values((run / 'run.conf').read_text().replace('\n', ' '))
        logs = list(run.glob('llm_perf_report_*.log'))
        log = run / 'ara.log'
        text = log.read_text(errors='replace')
        match = attention.OPERATOR_RE.search(text)
        native = row['implementation'].startswith('akv_v2')
        if ((not (run / 'complete').is_file() and not shell_tail_error) or len(logs) != 1 or not match or
                match.group(1) != 'PASS' or int(match.group(3)) != 0 or
                config['implementation'] != row['implementation'] or
                'Core Test *** SUCCESS' not in text or
                (native and 'ATTENTION_DISPATCH native_v2=1' not in text)):
            row.update(status='INVALID', error='incomplete or mismatched success evidence')
            continue
        if shell_tail_error:
            row.update(status='PASS_REVALIDATED', error='shell tail failed; completed simulation log revalidated')
        phases = attention.parse_run(row['implementation'], int(config['effective_kv']), run, log, logs[0])
        totals = [p for p in phases if p['phase'] == 'total']
        if len(totals) != 1:
            row.update(status='INVALID', error='expected exactly one total counter record')
            continue
        for phase in phases:
            metrics.append({'cohort': root.name, 'case': row['case'], **phase})
        total = totals[0]
        row.update({key: total.get(key, '') for key in (
            'run_dir', 'effective_kv', 'kernel_cycles', 'mismatches',
            'capture_manifest_sha256', 'simv_sha256', 'ara_elf_sha256',
            'cycles', 'nr_lanes', 'retired_vector_inst_count', 'retired_scalar_inst_count',
            'axi_ar_bytes', 'fp_exec_lane_fires', 'akv_q_external_bytes',
            'akv_kv_external_bytes', 'akv_replay_bytes', 'akv_command_count')})
        denominator = int(row['cycles']) * int(row['nr_lanes'])
        if denominator:
            row['fp_issue_activity'] = int(row['fp_exec_lane_fires']) / denominator
    return results, metrics


def comparison_key(row):
    return (row['case'], row['effective_kv'], row['capture_manifest_sha256'], row['simv_sha256'])


def add_comparisons(rows):
    baselines = {}
    for row in rows:
        if row['status'] not in ('PASS', 'PASS_REVALIDATED') or row['implementation'] not in ('rvv', 'akv_v2'):
            continue
        key = (*comparison_key(row), row['implementation'])
        if key in baselines and baselines[key]['kernel_cycles'] != row['kernel_cycles']:
            raise ValueError('ambiguous baseline; provide one baseline cohort')
        baselines[key] = row
    for row in rows:
        if row['status'] not in ('PASS', 'PASS_REVALIDATED'):
            continue
        for mode in ('rvv', 'akv_v2'):
            baseline = baselines.get((*comparison_key(row), mode))
            if baseline:
                row[f'speedup_vs_{mode}'] = int(baseline['kernel_cycles']) / int(row['kernel_cycles'])
                row[f'baseline_{mode}'] = baseline['run_dir']


def model_records(text):
    segment = None
    coverage, execution, qbs, fallback, numerical = [], [], [], Counter(), {}
    for line in text.splitlines():
        if line.startswith('AKV_TOKEN_RUN_BEGIN='):
            segment = line.split('=', 1)[1].strip()
        if line.startswith(('QBS_RVV_', 'AKV_LOGITS_', 'AKV_TOKEN_OUTPUT_EQUAL=', 'MODEL_NUMERICAL_', 'MODEL_LOGITS_')):
            numerical.update(attention.parse_key_values(line))
        if segment != 'QBS_AKV_V2':
            continue
        if line.startswith('GGML_RISCV_AKV_COVERAGE '):
            coverage.append(attention.parse_key_values(line))
        elif line.startswith('GGML_RISCV_AKV_EXEC '):
            execution.append(attention.parse_key_values(line))
        elif line.startswith('GGML_RISCV_AKV_FALLBACK '):
            values = attention.parse_key_values(line)
            fallback[f"{values['mode']}:{values['reason']}"] += 1
        elif line.startswith(('GGML_RISCV_QBS_COVERAGE ', 'GGML_RISCV_QBS_EXEC ')):
            qbs.append({'record': line.split()[0], **attention.parse_key_values(line)})
        if line.startswith('AKV_TOKEN_RUN_EXIT=QBS_AKV_V2:'):
            segment = None
    return {'coverage': coverage, 'execution': execution, 'qbs': qbs,
            'fallback_by_phase': dict(fallback), 'numerical': numerical}


def collect_models(root):
    rows = []
    for state in sorted(root.glob('models/*/stage.json')):
        status = json.loads(state.read_text())
        row = {'cohort': root.name, 'model': state.parent.name,
               'status': status['status'], 'worker_status': status['status'], 'stage': str(state)}
        log = state.parent / 'qemu.log'
        recheck = state.parent / 'revalidation.json'
        if recheck.is_file() and log.is_file() and status['status'] != 'RUNNING':
            result = json.loads(recheck.read_text())
            if result['qemu_log_sha256'] == hashlib.sha256(log.read_bytes()).hexdigest() and result['status'] == 'PASS':
                row['status'] = 'PASS_REVALIDATED'
        if status['status'] != 'RUNNING' and log.exists():
            row.update(model_records(log.read_text(errors='replace')))
        rows.append(row)
    return rows


def write_csv(path, rows, leading):
    columns = leading + sorted({k for r in rows for k in r} - set(leading))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-root', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows, metrics, models = [], [], []
    for root in args.run_root:
        if not root.is_dir():
            parser.error(f'missing run root: {root}')
        result, counters = collect_rtl(root.resolve())
        rows.extend(result)
        metrics.extend(counters)
        models.extend(collect_models(root.resolve()))
    add_comparisons(rows)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / 'rtl.csv', rows, ['cohort', 'case', 'implementation', 'status'])
    write_csv(args.output / 'rtl_all_metrics.csv', metrics, ['cohort', 'case', 'implementation', 'phase'])
    (args.output / 'models.json').write_text(json.dumps(models, indent=2) + '\n')
    report = ['# AKV Portability Stage 2', '',
              'Measured RTL cycles only. QEMU is functional evidence, not a speed estimate.', '',
              '| Cohort | Case | Mode | Status | Cycles | RVV speedup | Original AKV speedup |',
              '| --- | --- | --- | --- | ---: | ---: | ---: |']
    for row in rows:
        speedups = [f'{row[k]:.3f}x' if k in row else '-' for k in ('speedup_vs_rvv', 'speedup_vs_akv_v2')]
        report.append(f"| {row['cohort']} | {row['case']} | {row['implementation']} | {row['status']} | "
                      f"{row.get('kernel_cycles', '-')} | {' | '.join(speedups)} |")
    report += ['', '## Counter Boundaries', '',
               '- `fp_issue_activity = fp_exec_lane_fires / (monitor cycles * lanes)` counts accepted FP lane operations, not peak FLOP utilization.',
               '- `axi_ar_bytes` includes shared VLSU normal/AKV read traffic. Do not add AKV payload bytes again.',
               '- AKV Q/KV external bytes count accepted payload strobes, excluding descriptor bytes. Replay bytes are internal traffic.',
               '- Phase counters are inclusive diagnostics. AKV command totals are repeated on phase rows; sum them only once per run.',
               '- Kernel cycles and monitor cycles use different marker overheads. Ratios use the matching denominator.',
               '', '## Model Runs', '', '| Cohort | Model | Status |', '| --- | --- | --- |']
    for row in models:
        report.append(f"| {row['cohort']} | {row['model']} | {row['status']} |")
    (args.output / 'summary.md').write_text('\n'.join(report) + '\n')
    print(args.output / 'summary.md')


if __name__ == '__main__':
    main()
