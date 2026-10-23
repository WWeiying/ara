#!/usr/bin/env python3
"""Build current signoff half-scale SoC with VCS and run checked integration.

Run this foreground worker directly under the owning service, not through a
short-lived background launcher. No app builds are performed: --elf-dir must
contain current-source signoff ELFs, or a prior run's frozen elf directory for
paired replay. --tools-root supplies tools only, never application binaries.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CASES = (
    'qbs_akv_handoff_smoke',
    'rv64uv-ara-vfmacc',
    'llama_qwen25_q8_0_decode_attn_q_qbs',
    'llama_qwen25_q8_0_prefill_tile_qbs',
    'llama_qwen25_q8_0_segmented_qbs',
)
PROJECTION_CASES = (
    'llama_qwen25_q8_0_prefill_m4_direct_qbs',
    'llama_qwen25_q8_0_prefill_m4_context_qbs',
)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def hashes(paths):
    return {str(path): digest(path) for path in sorted(paths)}


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.partial')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def seal_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)
    return digest(path)


def script_files():
    return [Path(__file__).resolve(), ROOT / 'verification/Makefile',
            ROOT / 'verification/uvm/run_real_dut_case.sh',
            *sorted((ROOT / 'verification/ara_verify').glob('*.py'))]


def image_files(simv):
    libraries = sorted(Path(str(simv) + '.daidir').rglob('*.so'))
    files = [simv, simv.parent / 'simulator.conf',
             simv.parent / 'vcs_source_manifest.json', *libraries]
    if not os.access(simv, os.X_OK) or not libraries or not all(
            path.is_file() for path in files):
        raise RuntimeError('Complete executable VCS image, config and manifest required')
    return files


def build_command(tools_root, build, l2_mb=1):
    return ['make', '-C', str(ROOT / 'verification'), 'real-ara-uvm-compile',
            f'REAL_UVM_OUT={build}', f'REAL_UVM_SIM_L2_MB={l2_mb}',
            'REAL_UVM_QBS=1', 'REAL_UVM_AKV_V2=1', 'REAL_UVM_AXI_DELAY=0',
            'config=default', 'nr_lanes=4', 'vlen=1024',
            f'BENDER={tools_root}/hardware/bender',
            f'INSTALL_DIR={tools_root}/install',
            # Legacy DPI header dependency only; this target invokes VCS.
            f'VERILATOR_INCLUDE={tools_root}/install/verilator/share/verilator/include/vltstd']


def run_command(argv, log, timeout, env, started):
    with log.open('x') as stream:
        # A separate process group permits bounded cleanup, not service escape.
        process = subprocess.Popen(argv, cwd=ROOT, stdout=stream,
                                   stderr=subprocess.STDOUT, env=env,
                                   start_new_session=True)
        try:
            started(process.pid)
            return process.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
            finally:
                # Kill remaining descendants even if the direct child exited.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            raise


def check_result(record, elf_hash, image):
    result = json.loads(record.read_text())
    design = {path: value for path, value in image.items()
              if Path(path).name not in ('simulator.conf', 'vcs_source_manifest.json')}
    if (result.get('status') != 'PASS' or result.get('issues') != []
            or result.get('elf_sha256') != elf_hash
            or result.get('sim_image_sha256') != design):
        raise RuntimeError('Independent DUT check failed or input identity mismatched')


def check_projection_app(text, case):
    short = case.removeprefix('llama_qwen25_')
    def record(prefix):
        rows = re.findall(r'^' + prefix + r' case=' + re.escape(short) + r' (.*)$', text, re.M)
        if len(rows) != 1:
            raise RuntimeError('Missing or duplicate app record: ' + prefix)
        return dict(re.findall(r'(\w+)=([^\s]+)', rows[0]))
    preflight = record('QBS_REAL_PREFLIGHT')
    oracle = record('QBS_REAL_ORACLE')
    result = record('QBS_REAL_BENCH')
    expected = dict(k='896', rows='896', inputs='4', outputs='3584', tiles='28',
                    operations='1', quantizations='1', cross_op_reuse='0', mismatches='0',
                    result='PASS', qbs_status='0', setup_included='1',
                    activation_context='1' if 'context' in case else '0')
    if any(result.get(k) != v for k, v in expected.items()):
        raise RuntimeError('Wrong projection geometry/result/timing scope')
    if (oracle.get('outputs') != '3584' or oracle.get('quant_byte_mismatches') != '0'
            or oracle.get('mismatches') != '0' or oracle.get('kind') != 'scalar_fp64_offline'
            or preflight.get('layout') != '2' or preflight.get('packed_bytes') != '3808'
            or preflight.get('context_capacity') != '4672' or preflight.get('tiles') != '28'):
        raise RuntimeError('Projection oracle/preflight failed')
    timings = {key: int(result[key]) for key in
               ('compute_cycles', 'quantize_cycles', 'pack_cycles', 'matmul_cycles')}
    if (any(value <= 0 for value in timings.values()) or
            timings['compute_cycles'] != timings['quantize_cycles'] +
            timings['pack_cycles'] + timings['matmul_cycles'] or
            int(result['timed_cycles']) != timings['compute_cycles']):
        raise RuntimeError('Inconsistent projection cycle accounting')
    expected_reads = 852992 + 3808 * (1 if 'context' in case else 28)
    if int(result['logical_read_bytes']) != expected_reads:
        raise RuntimeError('Projection activation traffic differs from contract')
    return dict(preflight=preflight, oracle=oracle, result=result)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New output directory')
    parser.add_argument('--tools-root', type=Path, required=True,
                        help='ara_dsa tool installation root (not an ELF source)')
    parser.add_argument('--elf-dir', type=Path, required=True,
                        help='Current signoff apps/bin, or frozen ELFs for paired replay')
    parser.add_argument('--simv', type=Path,
                        help='Reuse complete manifest-gated VCS image; do not build')
    parser.add_argument('--cases', nargs='+', choices=CASES + PROJECTION_CASES, default=list(CASES))
    parser.add_argument('--l2-mb', type=int, choices=(1, 16), default=1,
                        help='Simulation-only L2 size; must match the application link bound')
    parser.add_argument('--timeout', type=int, default=1800, help='Seconds per case')
    parser.add_argument('--build-timeout', type=int, default=7200)
    args = parser.parse_args(argv)
    if min(args.timeout, args.build_timeout) < 1:
        parser.error('timeouts must be positive')
    if len(set(args.cases)) != len(args.cases):
        parser.error('duplicate cases are not allowed')
    return args


def main(argv=None):
    args = parse_args(argv)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = dict(schema_version=1, state='preparing', pid=os.getpid(),
                 started=now(), source_root=str(ROOT), mode='reuse' if args.simv else 'build',
                 tools_root=str(args.tools_root.resolve()), elf_dir=str(args.elf_dir.resolve()),
                 selected_cases=args.cases, simulation_l2_mb=args.l2_mb,
                 cases={case: {'state': 'pending'} for case in args.cases})

    def save():
        state['updated'] = now()
        atomic_json(out / 'status.json', state)

    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=str(ROOT / 'verification'),
               ARA_VCS_TIMEOUT_SECONDS=str(args.timeout), ARA_VCS_CODE_COVERAGE='0')
    # Do not inherit unrelated make overrides from an enclosing campaign.
    for key in ('MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES'):
        env.pop(key, None)

    def run(command, log, timeout, phase):
        state.update(state=phase, command=command, log=str(log), child_pid=None)
        save()

        def started(pid):
            state['child_pid'] = pid
            save()

        try:
            return run_command(command, log, timeout, env, started)
        finally:
            state['child_pid'] = None
            save()

    def interrupted(signum, _frame):
        raise InterruptedError(f'worker received signal {signum}')

    handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
    save()
    try:
        tools_root = args.tools_root.resolve(strict=True)
        elf_dir = args.elf_dir.resolve(strict=True)
        state['revision'] = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        frozen = out / 'elf'
        frozen.mkdir()
        scripts = hashes(script_files())
        elfs = {}
        for case in args.cases:
            source = elf_dir / case
            target = frozen / case
            original = digest(source)
            shutil.copyfile(source, target)
            target.chmod(0o444)
            if digest(target) != original or digest(source) != original:
                raise RuntimeError(f'ELF changed while copying: {source}')
            elfs[str(target)] = original
            state['cases'][case].update(input_path=str(source), elf=str(target),
                                        elf_sha256=original)
        inputs = dict(scripts=scripts, elfs=elfs,
                      sources={case: state['cases'][case]['input_path'] for case in args.cases})
        input_pin = out / 'input-pins.json'
        input_hash = seal_json(input_pin, inputs)
        state['input_pins_sha256'] = input_hash

        def check_inputs():
            if (digest(input_pin) != input_hash or hashes(script_files()) != scripts
                    or hashes(map(Path, elfs)) != elfs):
                raise RuntimeError('ELF/script/pin drift; stopping dispatch')

        check_inputs()
        if args.simv:
            simv = args.simv.resolve(strict=True)
        else:
            command = build_command(tools_root, out / 'build', args.l2_mb)
            state['build_command'] = command
            code = run(command, out / 'build.log', args.build_timeout, 'building')
            if code:
                raise RuntimeError(f'VCS compilation failed: {code}')
            simv = out / 'build/sim/simv'
        check_inputs()
        image = hashes(image_files(simv))
        configuration = dict(line.split('=', 1) for line in
                             (simv.parent / 'simulator.conf').read_text().splitlines()
                             if '=' in line)
        if configuration.get('sim_l2_mb') != str(args.l2_mb):
            raise RuntimeError('Simulator L2 configuration differs from requested size')
        image_pin = out / 'image-pins.json'
        image_hash = seal_json(image_pin, dict(simv=str(simv), files=image))
        state.update(simv=str(simv), image_pins_sha256=image_hash)
        manifest = simv.parent / 'vcs_source_manifest.json'
        if not args.simv:
            metadata = json.loads(manifest.read_text())
            half_scale = str(ROOT / 'hardware/src/vlsu/qbs/qbs_half_scale.sv')
            if (Path(metadata['repo_root']).resolve() != ROOT
                    or half_scale not in {row['path'] for row in metadata['files']}):
                raise RuntimeError('New build must use current signoff half-scale sources')

        def gate(label):
            check_inputs()
            if digest(image_pin) != image_hash or hashes(image_files(simv)) != image:
                raise RuntimeError('Simulator image/configuration/manifest drift')
            command = [sys.executable, '-m', 'ara_verify.vcs_source_manifest',
                       '--output', str(manifest), '--check']
            if run(command, out / f'manifest-{label}.log', 300, 'checking_manifest'):
                raise RuntimeError('VCS source manifest gate failed; stopping dispatch')
            check_inputs()
            if hashes(image_files(simv)) != image:
                raise RuntimeError('Simulator image changed during manifest check')

        gate('ready')
        for case in args.cases:
            state['active_case'] = case
            gate(f'{case}-before')
            entry = state['cases'][case]
            entry.update(state='running', started=now())
            command = ['bash', str(ROOT / 'verification/uvm/run_real_dut_case.sh'),
                       str(simv), str(frozen / case), case, str(out / case)]
            entry['command'] = command
            # This PID belongs to the host flow, not necessarily the simulator.
            code = run(command, out / f'{case}.log', args.timeout + 120, 'running_host_flow')
            entry['returncode'] = code
            gate(f'{case}-after')
            if code:
                entry['state'] = 'timeout' if code == 124 else 'failed'
                entry['finished'] = now()
                raise RuntimeError(f'{case}: host flow exited {code}')
            record = out / case / 'uvm_result.json'
            check_result(record, entry['elf_sha256'], image)
            if case in PROJECTION_CASES:
                entry['projection'] = check_projection_app(
                    (out / case / 'work/run.vcs.log').read_text(), case)
            if digest(out / case / 'work/input.elf') != entry['elf_sha256']:
                raise RuntimeError(f'{case}: executed ELF differs from frozen ELF')
            entry.update(state='passed', finished=now(), result=str(record),
                         result_sha256=digest(record))
            state['active_case'] = None
            save()
        gate('final')
        state['state'] = 'passed'
    except (Exception, KeyboardInterrupt) as error:
        state.update(state='interrupted' if isinstance(error, (InterruptedError, KeyboardInterrupt))
                     else 'failed', error=repr(error))
        for entry in state['cases'].values():
            if entry['state'] == 'running':
                entry.update(state='timeout' if isinstance(error, subprocess.TimeoutExpired)
                             else state['state'], error=repr(error), finished=now())
            elif entry['state'] == 'pending':
                entry.update(state='not_run', reason='stopped before dispatch')
    finally:
        state.update(finished=now(), child_pid=None)
        save()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    return 0 if state['state'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
