#!/usr/bin/env python3
"""Prepare a pinned SoC build; stage 2 is the only baseline/candidate difference."""
import argparse
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
TEMPLATE = OUT / 'shared_fma_tagpack_acceptance_20261105_02/soc'
HELPER = ROOT / 'verification/performance/chain_profile/build_soc.py'
BORROW = 'hardware/src/lane/qbs_lane_mul_borrow.sv'


def helper(path):
    spec = importlib.util.spec_from_file_location('stage2_soc_helpers', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def insert_borrow(text, source):
    marker = str(source / 'hardware/src/lane/vmfpu.sv')
    borrow = str(source / BORROW)
    if text.splitlines().count(marker) != 1 or borrow in text.splitlines():
        raise ValueError('Unexpected VMFPU source list or duplicate borrower')
    if not Path(borrow).is_file():
        raise ValueError('Revision does not contain the stage-2 borrower')
    return text.replace(marker + '\n', borrow + '\n' + marker + '\n', 1)


def prepare(out, revision, enabled):
    base = helper(HELPER)
    base.require(out.parent == OUT and not out.exists(), 'Fresh direct signoff output required')
    revision = subprocess.check_output(['git', '-C', ROOT, 'rev-parse', revision + '^{commit}'], text=True).strip()
    accepted = json.loads((TEMPLATE / 'report.json').read_text())
    base.require(accepted['state'] == 'PASS', 'Dependency template was not accepted')
    inherited = json.loads((TEMPLATE / 'source-pins.json').read_text())
    original = TEMPLATE / 'shared/source'
    dependencies = {p: sha for p, sha in inherited.items() if Path(p).is_relative_to(original)}
    base.require(len(dependencies) >= 400, 'Incomplete dependency template')
    base.verify(dependencies)
    base.require(inherited.get(str(TEMPLATE / 'elfloader.o')) == base.digest(TEMPLATE / 'elfloader.o'),
                 'DPI loader identity differs')
    out.mkdir()
    source = out / 'source'
    shutil.copytree(original, source, symlinks=False,
                    ignore=lambda directory, names: ['install'] if Path(directory) == original else [])
    archive = subprocess.check_output(['git', '-C', ROOT, 'archive', revision, *base.ARCHIVE_PATHS])
    (out / 'source.tar').write_bytes(archive)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for item in tar:
            path = Path(item.name)
            base.require(not path.is_absolute() and '..' not in path.parts and
                         (item.isfile() or item.isdir() or item.issym()), 'Unsafe Git archive entry')
            target = source / path
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.issym():
                resolved = (target.parent / item.linkname).resolve()
                base.require(path.as_posix() == 'hardware/tb/dpi/elfloader.cc' and
                             resolved.is_relative_to(source / 'hardware/deps') and resolved.is_file(),
                             'Unexpected/unsealed symlink')
                if target.exists() or target.is_symlink():
                    target.unlink()
                target.symlink_to(item.linkname)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(item).read())
    base.require('EnableQbsLaneMul' in (source / 'hardware/src/ara.sv').read_text(),
                 'Revision lacks stage-2 SoC routing; commit the reviewed integration first')
    base.require("localparam bit EnableSharedFma = 1'b0;" in
                 (source / 'hardware/include/ara_pkg.sv').read_text(), 'Unexpected shared-FMA configuration')
    text = base.freeze_filelist((TEMPLATE / 'shared/sources.f').read_text(), original, source)
    text = insert_borrow(text, source)
    base.require('ARA_QBS_LANE_MUL_ENABLE' not in text, 'Template already enables stage 2')
    (out / 'sources.f').write_text(text)
    shutil.copy2(TEMPLATE / 'elfloader.o', out / 'elfloader.o')
    inputs = out / 'inputs'
    inputs.mkdir()
    shutil.copy2(Path(__file__), inputs / 'build_soc.py')
    shutil.copy2(HELPER, inputs / 'base_build.py')
    shutil.copy2(HERE / 'soc_loan_monitor.sv', inputs / 'soc_loan_monitor.sv')
    sim = out / 'sim'
    sim.mkdir()
    config = dict(schema_version=1, config='stage2_lane_coexecution', revision=revision,
                  nr_lanes=4, vlen=1024, qbs_enabled=1, akv_enabled=1, akv_v2_enabled=1,
                  sim_l2_bytes=16777216, shared_simd_multiplier=1, shared_fma=0,
                  qbs_lane_multiplier=enabled, ideal_dispatcher=0)
    (sim / 'simulator.conf').write_text(''.join(f'{key}={value}\n' for key, value in config.items()))
    vcs = Path(shutil.which('vcs') or '/missing-vcs').resolve()
    base.require(vcs.is_file(), 'Host VCS unavailable')
    command = [str(vcs), '-full64', '-sverilog', '+v2k', '-Mlib=./incremental_db', '-Mupdate',
               '-j8', '-lca', '+nospecify', '+notimingchecks', '+lint=TFIPC-L', '+vpi',
               '+lint=PCWM', '+error+30', '-ntb_opts', 'uvm-1.2', '-top', 'ara_tb',
               '-timescale=1ns/100fs', '+define+SIMULATION', '+define+no_warning',
               '+define+TSMC_NO_WARNING', '+define+ARA_NO_FSDB', '+define+ARA_FAIL_FAST_ASSERTS',
               '+define+ARA_VERIFY_UVM_CVXIF', '+define+ARA_SHARED_SIMD_MUL',
               '-f', str(out / 'sources.f'), str(out / 'elfloader.o'),
               *(str(source / path) for path in base.UVM), str(inputs / 'soc_loan_monitor.sv'),
               '-l', 'comp.vcs.log']
    if enabled:
        command.append('+define+ARA_QBS_LANE_MUL_ENABLE')
    base.save(out / 'plan.json', dict(state='PREPARED_NOT_COMPILED', command=command,
              configuration=config, template=str(TEMPLATE), raw_dirty_sources_used=False,
              dependencies='Previously accepted frozen dependency snapshot',
              full_soc_executed=False, performance_measured=False))
    pins = dict(dependencies)
    for path in (Path(__file__), HERE / 'soc_loan_monitor.sv', HELPER,
                 TEMPLATE / 'report.json', TEMPLATE / 'source-pins.json',
                 TEMPLATE / 'shared/sources.f', TEMPLATE / 'elfloader.o', vcs):
        pins[str(path)] = base.digest(path)
    for path in out.rglob('*'):
        if path.is_file():
            pins[str(path)] = base.digest(path)
    base.save(out / 'source-pins.json', pins)
    base.verify(pins)
    print(inputs / 'build_soc.py', flush=True)


def execute(out):
    if Path(__file__).resolve() != out / 'inputs/build_soc.py':
        raise ValueError('Execute the frozen builder')
    base = helper(out / 'inputs/base_build.py')
    pins = json.loads((out / 'source-pins.json').read_text())
    plan = json.loads((out / 'plan.json').read_text())
    status = dict(state='PREFLIGHT', child_pid=None, started=datetime.now(timezone.utc).isoformat())
    result = dict(state='FAIL', full_soc_executed=False, performance_measured=False)
    try:
        base.verify(pins)
        base.execute(plan['command'], out / 'sim', out / 'compile.log', 7200,
                     status, out / 'status.json', 'BUILDING')
        log = (out / 'compile.log').read_text(errors='replace')
        base.require(not any(line.startswith(('Error-', 'Error:', 'Fatal:')) for line in log.splitlines()),
                     'Compilation diagnostics contain errors')
        simv = out / 'sim/simv'
        base.require(simv.is_file(), 'No simulator image')
        base.verify(pins)
        result.update(state='STAGE2_SOC_BUILT_NOT_EXECUTED', simv=str(simv),
                      configuration=plan['configuration'], post_pins_match=True,
                      source_pins_sha256=base.digest(out / 'source-pins.json'),
                      image_pins={str(p): base.digest(p) for p in (out / 'sim').rglob('*') if p.is_file()})
    except BaseException as exc:
        result['error'] = repr(exc)
    base.save(out / 'build.json', result)
    status.update(state=result['state'], child_pid=None, finished=datetime.now(timezone.utc).isoformat())
    base.save(out / 'status.json', status)
    print(result['state'] + ' ' + str(out / 'build.json'), flush=True)
    return int(result['state'] == 'FAIL')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('output', type=Path)
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--enabled', type=int, choices=(0, 1), default=0)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        def interrupted(sig, _frame):
            raise InterruptedError('Signal ' + str(sig))
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, interrupted)
        raise SystemExit(execute(args.output.resolve()))
    prepare(args.output.resolve(), args.revision, args.enabled)
