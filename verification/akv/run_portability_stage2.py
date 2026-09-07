#!/usr/bin/env python3
"""Run isolated real-model and native-RTL portability evidence collection."""

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import signal
import select
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
LLAMA = Path('/home/wangwy/llama/llama.cpp')
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
QEMU = Path('/tmp/qbs-current-qemu-20260907/qemu-10.2.0-build/qemu-system-riscv64')
REFACT = {
    'id': 'refact_1p6b_q4km', 'name': 'Refact-1.6B-fim-Q4_K_M',
    'model': '/home/wangwy/llama/models/portability/refact-1_6b-Q4_K_M.gguf',
    'expected_sha256': '241741c3bb51c99d53ecb2e1891b66e8058e99876e07e82d21f050deb2f090c9',
    'source': {'repo': 'oblivious/Refact-1.6B-fim-GGUF',
               'revision': 'b7f7deb2cdb47de16f808d9c334b9b34e10543f6',
               'file': 'refact-1_6b-Q4_K_M.gguf'},
    'qemu': {'guest_path': '/model/models/refact-1_6b-Q4_K_M.gguf', 'memory': '4G'},
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def command(argv, log, env=None, timeout=3600, cwd=ROOT):
    log.parent.mkdir(parents=True, exist_ok=True)
    argv = [str(v) for v in argv]
    # These launchers derive the repository from $0, not BASH_SOURCE. Reading
    # once prevents later edits from changing the shell's post-simulation tail.
    if len(argv) >= 2 and argv[0] == 'bash' and Path(argv[1]).name in (
            'run-qemu-model-check.sh', 'run-ara-attention-core.sh'):
        script = Path(argv[1]).read_text()
        log.with_suffix('.launcher.sh').write_text(script)
        argv = ['bash', '-c', script, *argv[1:]]
    with log.open('w') as stream:
        try:
            proc = subprocess.Popen([str(v) for v in argv], cwd=cwd,
                                    env={**os.environ, **(env or {})},
                                    stdout=stream, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            return 124


def specs():
    result = []
    for filename in ('model-generality-manifest.json', 'qwen3-model-manifest.json'):
        result += json.loads((ROOT / 'hardware/scripts/akv' / filename).read_text())['models']
    selected = {'qwen25_1p5b_q4km', 'qwen3_1p7b_q4km', 'gemma3_1b_q4km'}
    return [m for m in result if m['id'] in selected] + [dict(REFACT)]


def prepare(out):
    model = Path(REFACT['model'])
    model.parent.mkdir(parents=True, exist_ok=True)
    if not model.exists():
        source = REFACT['source']
        url = f"https://huggingface.co/{source['repo']}/resolve/{source['revision']}/{source['file']}"
        partial = out / 'refact.download'
        size = 968337696
        def get_part(index):
            first = size * index // 8
            last = size * (index + 1) // 8 - 1
            path = out / f'download.part{index}'
            expected = last - first + 1
            have = path.stat().st_size if path.exists() else 0
            if have == expected:
                return path
            if have > expected:
                raise RuntimeError(f'download range {index} has invalid length')
            tail = out / f'download.tail{index}'
            rc = command(['curl', '-fLsS', '--retry', '2', '--retry-all-errors',
                          '--max-time', '1800', '--range', f'{first + have}-{last}',
                          '-o', tail, url], out / f'download{index}.resume.log', timeout=5500)
            if rc or not tail.exists() or tail.stat().st_size != expected - have:
                raise RuntimeError(f'download range {index} failed')
            with path.open('ab') as target, tail.open('rb') as source_stream:
                for block in iter(lambda: source_stream.read(4 * 1024 * 1024), b''):
                    target.write(block)
            tail.unlink()
            return path
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            parts = list(pool.map(get_part, range(8)))
        with partial.open('wb') as target:
            for path in parts:
                with path.open('rb') as source_stream:
                    for block in iter(lambda: source_stream.read(4 * 1024 * 1024), b''):
                        target.write(block)
        if sha(partial) != REFACT['expected_sha256']:
            raise RuntimeError('Refact download or SHA-256 check failed')
        partial.replace(model)
        for path in parts:
            path.unlink()
    if sha(model) != REFACT['expected_sha256']:
        raise RuntimeError('Refact model hash mismatch')
    disk = out / 'refact.ext4'
    if disk.exists():
        raise FileExistsError(disk)
    rc = command(['bash', ROOT / 'hardware/scripts/akv/create-model-disk.sh', model,
                  disk, model.name], out / 'disk.log')
    if rc:
        raise RuntimeError('model disk failed')


def build(out):
    rc = command(['bash', ROOT / 'hardware/scripts/akv/build-llama.sh'],
                 out / 'build.log', {'AKV_LLAMA_BUILD_DIR': str(out / 'llama-build'),
                                     'AKV_BUILD_JOBS': '8'}, timeout=3600)
    if rc:
        raise RuntimeError(f'llama build failed: {rc}')
    write_json(out / 'build.json', {
        'hardware_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'llama_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=LLAMA, text=True).strip(),
        'llama_binary_sha256': sha(out / 'llama-build/bin/llama-simple'),
        'qemu_binary_sha256': sha(QEMU), 'models': specs(),
    })
    command(['git', 'diff', '--binary', 'HEAD'], out / 'hardware.patch')
    command(['git', 'diff', '--binary', 'HEAD'], out / 'llama.patch', cwd=LLAMA)


def select_specs(selection):
    available = {s['id']: s for s in specs()}
    ids = list(available) if selection == 'all' else selection.split(',')
    if len(set(ids)) != len(ids) or any(i not in available for i in ids):
        raise ValueError('unknown or duplicate model selection')
    return [available[i] for i in ids]


def models(out, selection='all'):
    def run(spec):
        if sha(spec['model']) != spec['expected_sha256']:
            raise RuntimeError(f"model hash mismatch: {spec['id']}")
        name = spec['id']
        run_dir = out / 'models' / name
        run_dir.mkdir(parents=True, exist_ok=False)
        env = {
            'AKV_MODEL_MODE': 'combined-fallback' if name.startswith('gemma') else 'combined',
            'AKV_LLAMA_BINARY': str(out / 'llama-build/bin/llama-simple'),
            'AKV_QEMU_BINARY': str(QEMU), 'AKV_MODEL_PORTABLE': '1',
            'AKV_MODEL_DISK': str(out / 'refact.ext4') if name.startswith('refact') else spec['qemu']['disk'],
            'AKV_MODEL_GUEST_PATH': spec['qemu']['guest_path'],
            'AKV_QEMU_MEMORY': spec['qemu']['memory'], 'AKV_RUN_DIR': str(run_dir),
            'AKV_MODEL_DIGEST': 'MUL_MAT,FLASH_ATTN_EXT',
            'AKV_MODEL_DYNAMIC_ONLY': '1',
            'AKV_MODEL_TOKENS': '3', 'AKV_MODEL_PROMPT': 'The answer is',
        }
        write_json(run_dir / 'stage.json', {'status': 'RUNNING', 'environment': env})
        rc = command(['bash', ROOT / 'hardware/scripts/akv/run-qemu-model-check.sh'],
                     run_dir / 'worker.log', env, timeout=7200)
        write_json(run_dir / 'stage.json', {'status': 'PASS' if rc == 0 else 'FAIL',
                                          'return_code': rc, 'environment': env})
        return {'model': name, 'return_code': rc}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, select_specs(selection)))
    write_json(out / f'model_results_{selection}.json', results)
    return all(item['return_code'] == 0 for item in results)


def rtl_base(out):
    sim = out / 'sim'
    if not (sim / 'simv').exists():
        rc = command(['make', '-C', ROOT / 'hardware', 'compile', 'qbs=1', 'akv_v2=1',
                      'no_fsdb=1', 'sim_l2_mb=16', 'nr_lanes=4', 'vlen=1024',
                      f'sim_dir={os.path.relpath(sim, ROOT / "hardware")}',
                      f'buildpath={out / "rtl-build"}'], out / 'rtl-compile.log')
        if rc:
            raise RuntimeError('RTL simulator build failed')
    if not (sim / 'simv').is_file() or not (sim / 'simulator.conf').is_file():
        raise RuntimeError('simulator output path or manifest missing')
    tasks = []
    captures = Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-latest')
    for kv in (16, 128):
        for mode in ('rvv', 'akv_v2', 'akv_v2_portable'):
            tasks.append((f'qwen_kv{kv}', captures / f'kv{kv}', mode, kv))
    return rtl_tasks(out, tasks)


def rtl_tasks(out, tasks):
    def run(task):
        name, capture_root, mode, kv = task
        directory = out / 'rtl' / name / mode
        directory.mkdir(parents=True, exist_ok=False)
        env = {'Q4KM_CAPTURE_ROOT': str(capture_root),
               'LLAMA_ATTN_SIM_DIR': str(out / 'sim'),
               'LLAMA_ATTN_RUN_ROOT': str(directory),
               'LLAMA_ATTN_ARA_TIMEOUT': '10800',
               'LLAMA_ATTN_AKV_PERF_MODE': 'detail'}
        write_json(directory / 'stage.json', {'status': 'RUNNING', 'environment': env})
        rc = command(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh',
                      mode, str(kv), '--ara-only'], directory / 'worker.log', env, timeout=11100)
        write_json(directory / 'stage.json', {'status': 'PASS' if rc == 0 else 'FAIL',
                                             'return_code': rc, 'environment': env})
        return {'case': name, 'mode': mode, 'return_code': rc}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, tasks))
    write_json(out / ('rtl_base_results.json' if tasks[0][0].startswith('qwen') else 'rtl_refact_results.json'), results)
    return all(item['return_code'] == 0 for item in results)


def rtl_refined(out):
    captures = Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-latest')
    if not (out / 'sim/simv').is_file():
        raise RuntimeError('link the unchanged baseline simulator into output/sim first')
    return rtl_tasks(out, [(f'qwen_kv{kv}', captures / f'kv{kv}', 'akv_v2_portable', kv)
                          for kv in (16, 128)])


def rtl_refact(out):
    capture_root = out / 'captures' / REFACT['id']
    manifest = json.loads((capture_root / 'replay/manifest.json').read_text())
    kv = manifest['topology']['active_kv']
    return rtl_tasks(out, [('refact', capture_root, mode, kv)
                           for mode in ('rvv', 'akv_v2_portable')])


def capture(out, selection='all'):
    binary = PLATFORM / 'build/llama-format-capture-host/bin/llama-completion'
    selected = [s for s in select_specs(selection) if not s['id'].startswith('gemma')]
    for spec in selected:
        directory = out / 'captures' / spec['id']
        directory.mkdir(parents=True, exist_ok=False)
        env = {'LLAMA_Q4KM_CAPTURE_DIR': str(directory), 'LLAMA_Q4KM_CAPTURE_LAYER': '0',
               'LLAMA_Q4KM_CAPTURE_PHASE': 'decode', 'LLAMA_Q4KM_CAPTURE_PROFILE': 'attention_core'}
        rc = command([binary, '-m', spec['model'], '-p',
                      'Explain why low-bit vector inference benefits from packed arithmetic and data reuse.', '-n', '2',
                      '-c', '256', '-t', '8', '-tb', '8', '-fa', 'on', '-no-cnv',
                      '--load-mode', 'mmap', '--no-warmup', '--seed', '1', '--temp', '0'],
                     directory / 'capture.log', env, timeout=900)
        if rc:
            raise RuntimeError(f"capture failed: {spec['id']}")
        rc = command([sys.executable, ROOT / 'hardware/scripts/llama_q4km_extract/package_attention_capture.py',
                      directory, '--model', spec['name']], directory / 'package.log')
        if rc:
            raise RuntimeError(f"capture packaging failed: {spec['id']}")
        files = list((directory / 'decode/block').glob('*.json')) + list((directory / 'decode/block').glob('*.bin'))
        write_json(directory / 'provenance.json', {'model': spec, 'model_sha256': sha(spec['model']),
                   'binary': str(binary), 'binary_sha256': sha(binary),
                   'files': {str(p.relative_to(directory)): sha(p) for p in sorted(files)}})


def recheck_models(out, selection='all'):
    results = []
    for spec in select_specs(selection):
        directory = out / 'models' / spec['id']
        state = json.loads((directory / 'stage.json').read_text())
        if state['status'] == 'RUNNING':
            raise RuntimeError('do not revalidate an active model run')
        env = {**state['environment'], 'AKV_MODEL_DYNAMIC_ONLY': '1'}
        rc = command(['bash', ROOT / 'hardware/scripts/akv/run-qemu-model-check.sh',
                      '--check-log', directory / 'qemu.log'],
                     directory / 'recheck.log', env, timeout=120)
        result = {'status': 'PASS' if rc == 0 else 'FAIL', 'return_code': rc,
                  'original_status': state['status'], 'method': 'strict log validation, dynamic coverage only',
                  'qemu_log_sha256': sha(directory / 'qemu.log')}
        write_json(directory / 'revalidation.json', result)
        results.append(rc)
    return all(rc == 0 for rc in results)


def finalize(out, pids, baselines, smoke):
    # pidfds refer to a specific process, even if its PID is later reused.
    waiting = []
    for pid in pids:
        try:
            waiting.append(os.pidfd_open(pid))
        except ProcessLookupError:
            pass
    try:
        while waiting:
            ready, _, _ = select.select(waiting, [], [])
            for fd in ready:
                os.close(fd)
                waiting.remove(fd)
    finally:
        for fd in waiting:
            os.close(fd)
    roots = baselines + [out]
    passed = True
    selected = {}
    for root in roots:
        for path in root.glob('models/*/stage.json'):
            selected[path.parent.name] = root
    write_json(out / 'selected_models.json', {name: str(root) for name, root in selected.items()})
    for root in roots:
        names = [name for name, selected_root in selected.items() if root == selected_root]
        if names:
            passed = recheck_models(root, ','.join(sorted(names))) and passed
    argv = [sys.executable, ROOT / 'verification/akv/summarize_portability_stage2.py']
    for root in roots:
        argv += ['--run-root', root]
    argv += ['--output', out / 'summary']
    if command(argv, out / 'summary.log', timeout=120):
        return False
    import csv
    with (out / 'summary/rtl.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    expected_cases = {(f'qwen_kv{kv}', mode) for kv in (16, 128)
                      for mode in ('rvv', 'akv_v2', 'akv_v2_portable')}
    expected_cases |= {('refact', mode) for mode in ('rvv', 'akv_v2_portable')}
    present_cases = {(r['case'], r['implementation']) for r in rows}
    missing_models = sorted({spec['id'] for spec in specs()} - set(selected))
    missing_cases = sorted(expected_cases - present_cases)
    write_json(out / 'inventory.json', {'missing_models': missing_models, 'missing_rtl_cases': missing_cases})
    passed = not missing_models and not missing_cases and passed
    passed = bool(rows) and all(r['status'] in ('PASS', 'PASS_REVALIDATED') for r in rows) and passed
    if smoke:
        passed = (smoke / 'status').read_text().strip() == 'PASS' and passed
    return passed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'build', 'models', 'recheck_models', 'capture', 'rtl_base', 'rtl_refined', 'rtl_refact', 'finalize'])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--models', default='all')
    parser.add_argument('--retry-failed-prepare', action='store_true')
    parser.add_argument('--wait-pids', default='')
    parser.add_argument('--baseline-root', action='append', type=Path, default=[])
    parser.add_argument('--smoke-root', type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    suffix = '' if args.models == 'all' else '_' + args.models.replace(',', '_')
    select_specs(args.models)
    state = out / f'{args.action}{suffix}.status.json'
    if args.retry_failed_prepare:
        if args.action != 'prepare' or not state.exists() or json.loads(state.read_text())['status'] != 'FAIL':
            raise ValueError('retry is only supported for a failed prepare action')
        state.rename(out / f'prepare.failed.{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")}.json')
    if state.exists():
        raise FileExistsError(state)
    write_json(state, {'status': 'RUNNING', 'pid': os.getpid(),
                       'started_at': datetime.now(timezone.utc).isoformat()})
    try:
        if args.action == 'finalize':
            pids = [int(p) for p in args.wait_pids.split(',') if p]
            result = finalize(out, pids,
                              [p.resolve() for p in args.baseline_root],
                              args.smoke_root.resolve() if args.smoke_root else None)
        else:
            result = (globals()[args.action](out, args.models) if args.action in ('models', 'capture', 'recheck_models')
                      else globals()[args.action](out))
        rc = 1 if result is False else 0
    except Exception as error:
        write_json(state, {'status': 'FAIL', 'error': str(error)})
        raise
    write_json(state, {'status': 'PASS' if rc == 0 else 'FAIL',
                       'finished_at': datetime.now(timezone.utc).isoformat()})
    return rc


if __name__ == '__main__':
    sys.exit(main())
