#!/usr/bin/env python3
"""Snapshot-only by default workflow; build/run require explicit launch gates."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

from prepare import ROOT, check, save, sha

VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')
VERDI = Path('/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1')
# Same full SoC capabilities as the latest 20261009 image; no coverage/UVM probes.
SETTINGS = ['config=default', 'nr_lanes=4', 'vlen=1024', 'qbs=1', 'akv=1',
            'akv_v2=1', 'sim_l2_mb=2', 'mc=0', 'code_coverage=0',
            'fail_on_assert=1', 'store_b_ab_baseline=0', 'no_fsdb=1',
            'verify_axi_delay=1', 'verify_uvm_cvxif=0', 'verify_source_manifest=1',
            'verify_extra_sources=', 'ideal_dispatcher=0']
BENDER_ARGS = ['script', 'verilator', '--no-default-target', '-t', 'verilator',
               '-t', 'rtl', '-t', 'cv64a6_imafdcv_sv39',
               '-t', 'tech_cells_generic_include_tc_sram',
               '-t', 'tech_cells_generic_include_tc_clk', '-t', 'exclude_first_pass_decoder',
               '-t', 'ara_test', '-t', 'cva6_test', '-t', 'notsynthesis']
for define in ('NR_LANES=4', 'VLEN=1024', 'ARIANE_ACCELERATOR_PORT=1',
               'ARA_QBS_ENABLE=1', 'ARA_AKV_ENABLE=1', 'ARA_AKV_ENABLE=1',
               'ARA_AKV_V2_ENABLE=1', 'SIM_L2_SIZE_BYTES=2097152',
               'COMMON_CELLS_ASSERTS_OFF', 'FOR_VERIFY'):
    BENDER_ARGS += ['--define', define]


def environment():
    # Do not inherit MAKEFLAGS, compiler overrides, simulator flags, or ZCC paths.
    env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
    env.update(PATH=f'{VCS}/bin:/usr/bin:/bin', VCS_HOME=str(VCS), VERDI_HOME=str(VERDI),
               VCS_TARGET_ARCH='linux64', SNPSLMD_LICENSE_FILE='27000@t7920',
               LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
    return env


def oracle_complete(entry, text):
    needed = entry.get('pass_markers')
    if needed is None:
        needed = ['BOARD_REPLAY_PASS', *[f'BOARD_CASE_PASS {n}' for n in entry['cases']]]
    return bool(needed) and all(n in text for n in needed) and 'SKIP' not in text


def snapshot(out):
    """Copy actual filelist inputs, dereference files, and remove write permission.

    A frozen Bender adapter emits the captured, relocated list. It does not
    resolve dependencies again while other agents edit the live worktree.
    """
    sys.path.insert(0, str(ROOT / 'verification'))
    from ara_verify.vcs_source_manifest import collect
    out.mkdir(parents=True, exist_ok=False)
    repo = out / 'sources'
    repo.mkdir()
    source_list = out / 'original.filelist'
    command = [str(ROOT / 'hardware/bender'), *BENDER_ARGS]
    listing = subprocess.check_output(command, cwd=ROOT, text=True, env=environment())
    source_list.write_text(listing)
    records = collect(source_list, ROOT, [])
    paths = {Path(r['path']) for r in records} - {source_list}
    paths.update((ROOT / 'hardware/tb/dpi').rglob('*.cc'))
    paths.update((ROOT / 'verification/ara_verify').glob('*.py'))
    paths.add(ROOT / 'verification/verify.py')
    # These are headers only. No Verilator executable/build is invoked.
    for directory in ('install/riscv-isa-sim/include',
                      'install/verilator/share/verilator/include/vltstd'):
        paths.update(p for p in (ROOT / directory).rglob('*') if p.is_file())
    before = {str(p): sha(p) for p in sorted(paths)}
    for source in sorted(paths):
        try:
            relative = source.relative_to(ROOT)
        except ValueError as error:
            raise ValueError('unexpected external design input: ' + str(source)) from error
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target) != before[str(source)]:
            raise ValueError('source changed during snapshot: ' + str(source))
    after = {str(p): sha(p) for p in paths}
    if before != after or listing != subprocess.check_output(command, cwd=ROOT, text=True, env=environment()):
        raise ValueError('live sources changed during snapshot; discard this unsealed attempt')
    frozen_list = repo / 'frozen.filelist'
    frozen_list.write_text(listing.replace(str(ROOT) + '/', str(repo) + '/'))
    for line in frozen_list.read_text().splitlines():
        if line.startswith('/') and not line.startswith(str(repo) + '/'):
            raise ValueError('filelist escapes snapshot: ' + line)
        if line.startswith('+incdir+') and not line[8:].startswith(str(repo) + '/'):
            raise ValueError('include directory escapes snapshot: ' + line)
    adapter = repo / 'hardware/bender'
    adapter.write_text('#!/bin/sh\nset -eu\n'
                       'test "$1" = script\nexec /bin/cat ' + shlex.quote(str(frozen_list)) + '\n')
    adapter.chmod(0o555)
    pins = {str(p.relative_to(repo)): sha(p) for p in sorted(repo.rglob('*')) if p.is_file()}
    save(out / 'snapshot.json', dict(schema_version=1, source_root=str(ROOT), root=str(repo),
         settings=SETTINGS, bender_command=command, live_source_sha256=before,
         files=pins, state='SEALED', build_started=False))
    for path in repo.rglob('*'):
        path.chmod(0o555 if path.is_dir() or path == adapter else 0o444)
    repo.chmod(0o555)
    print(f'SEALED {len(pins)} files; no VCS build started: {out}')


def sealed(path):
    data = json.loads((path / 'snapshot.json').read_text())
    repo = Path(data['root'])
    if data['state'] != 'SEALED' or data['settings'] != SETTINGS:
        raise ValueError('incompatible snapshot')
    for name, digest in data['files'].items():
        source = repo / name
        if source.is_symlink() or sha(source) != digest or source.stat().st_mode & 0o222:
            raise ValueError('snapshot drift or writable source: ' + name)
    return repo


def framework(repo):
    sys.path.insert(0, str(repo / 'verification'))
    from ara_verify.runner import RegressionRunner, RunOptions
    from ara_verify.model import TestCase
    from ara_verify.artifacts import simulation_image
    return RegressionRunner, RunOptions, TestCase, simulation_image


def build_image(args):
    repo = sealed(args.snapshot)
    RegressionRunner, RunOptions, _, simulation_image = framework(repo)

    class ImageBuilder(RegressionRunner):
        def _build_commands(self):
            command = super()._build_commands()[1]
            command += SETTINGS + [f'ARA_DIR={repo}', 'CXX=/usr/bin/g++']
            # Software is built separately with GCC, never the apps default compiler.
            return [['/usr/bin/true'], command]

    options = RunOptions(repo, args.out, 'default', 1, 1, not args.authorize_build,
                         True, False, None, False, None)
    start = time.time()
    ImageBuilder(options, [], sys.argv).run()
    sealed(args.snapshot)
    if args.authorize_build:
        simv = args.out / '_build/vcs/simv'
        save(args.out / 'image.json', dict(schema_version=1, simv=str(simv),
             snapshot=str(args.snapshot), snapshot_sha256=sha(args.snapshot / 'snapshot.json'),
             files=simulation_image(simv), elapsed_s=time.time() - start,
             configuration_sha256=sha(simv.parent / 'simulator.conf'),
             manifest_sha256=sha(simv.parent / 'vcs_source_manifest.json')))


def run_programs(args):
    ledger = json.loads((args.image / 'image.json').read_text())
    snap = Path(ledger['snapshot'])
    if sha(snap / 'snapshot.json') != ledger['snapshot_sha256']:
        raise ValueError('snapshot identity drift')
    repo = sealed(snap)
    RegressionRunner, RunOptions, TestCase, simulation_image = framework(repo)
    simv = Path(ledger['simv'])
    if simulation_image(simv) != ledger['files']:
        raise ValueError('image drift')
    if sha(simv.parent / 'simulator.conf') != ledger['configuration_sha256']:
        raise ValueError('configuration drift')
    manifest = simv.parent / 'vcs_source_manifest.json'
    if sha(manifest) != ledger['manifest_sha256']:
        raise ValueError('source manifest drift')
    from ara_verify.vcs_source_manifest import collect
    capture = json.loads(manifest.read_text())
    if collect(Path(capture['filelist']), repo, [Path(p) for p in capture['extra_sources']]) != capture['files']:
        raise ValueError('compiled-source drift')
    programs = json.loads((args.programs / 'programs.json').read_text())
    if programs['backend'] != 'vcs-soc':
        raise ValueError('refuse Spike HTIF ELF on SoC')
    prepared = Path(programs['prepared'])
    check(prepared)
    if sha(prepared / 'provenance.json') != programs['provenance_sha256']:
        raise ValueError('program provenance drift')
    tests = []
    names = args.case or ['all']
    for name in names:
        entry = programs['programs'][name]
        elf = Path(entry['path'])
        if sha(elf) != entry['sha256']:
            raise ValueError('program drift: ' + name)
        tests.append(TestCase(name, 'app', '', elf, name, args.timeout))
    options = RunOptions(repo, args.out, 'default', args.jobs, 1, not args.execute,
                         False, True, simv, True, args.timeout)

    class CheckedRunner(RegressionRunner):
        def _run_test(self, test, image):
            if self.cancel_event.is_set():
                return super()._run_test(test, image)
            result = super()._run_test(test, image)
            if result.status == 'PASS':
                text = (result.artifact_dir / 'console.log').read_text()
                if not oracle_complete(programs['programs'][test.name], text):
                    result.status, result.reason = 'FAIL', 'missing architectural oracle completion'
            if result.status not in ('PASS', 'DRY_RUN') and test.name not in ('gather_original', 'gather_prestart'):
                self.cancel_event.set()
            return result

    results = CheckedRunner(options, tests, sys.argv).run()
    sealed(snap)
    if simulation_image(simv) != ledger['files']:
        raise ValueError('image changed during replay')
    return int(any(r.status not in ('PASS', 'DRY_RUN') for r in results))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    snap = sub.add_parser('snapshot')
    snap.add_argument('--out', type=Path, required=True)
    snap.add_argument('--authorize-freeze', action='store_true')
    build = sub.add_parser('build-image')
    build.add_argument('--snapshot', type=Path, required=True)
    build.add_argument('--out', type=Path, required=True)
    build.add_argument('--authorize-build', action='store_true')
    run = sub.add_parser('run')
    run.add_argument('--image', type=Path, required=True)
    run.add_argument('--programs', type=Path, required=True)
    run.add_argument('--out', type=Path, required=True)
    run.add_argument('--case', action='append')
    run.add_argument('--jobs', type=int, choices=range(1, 9), default=4,
                     help='parallel VCS program executions (default: 4, maximum: 8)')
    run.add_argument('--timeout', type=int, default=300)
    run.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(args, 'timeout') and args.timeout <= 0:
        parser.error('timeout must be positive')
    for key in ('out', 'snapshot', 'image', 'programs'):
        if hasattr(args, key):
            setattr(args, key, getattr(args, key).resolve())
    if args.command == 'snapshot' and not args.authorize_freeze:
        parser.error('snapshot requires --authorize-freeze after parent approval')
    return args


def main():
    args = parse_args()
    env = environment()
    os.environ.clear()
    os.environ.update(env)
    if args.command == 'snapshot':
        snapshot(args.out)
    elif args.command == 'build-image':
        build_image(args)
    else:
        return run_programs(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
