#!/usr/bin/env python3
"""Build a frozen current-area-baseline VCS image with passive diagnostics."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
TEMPLATE = OUT / 'shared_fma_tagpack_acceptance_20261105_02/soc'
UVM = tuple('verification/uvm/' + n for n in (
    'ara_cvxif_if.sv', 'ara_cvxif_uvm_pkg.sv', 'ara_acc_contract_monitor.sv',
    'ara_cvxif_dut_bind.sv'))
ARCHIVE_PATHS = ('hardware/src', 'hardware/include', 'hardware/tb',
                 'hardware/Makefile', 'Bender.yml', 'Bender.lock',
                 'config/default.mk', 'config/sram.mk', *UVM)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def verify(pins):
    for path, sha in pins.items():
        require(Path(path).is_file() and digest(path) == sha, 'Sealed input drift: ' + path)


def execute(argv, cwd, log, seconds, status, status_path, phase):
    argv = list(map(str, argv))
    save(log.with_suffix('.command.json'), dict(argv=argv, cwd=str(cwd), timeout_seconds=seconds))
    with log.open('x') as stream:
        process = subprocess.Popen(argv, cwd=cwd, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        status.update(state=phase, child_pid=process.pid)
        save(status_path, status)
        try:
            rc = process.wait(timeout=seconds)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except ProcessLookupError:
                pass
            raise
        finally:
            status['child_pid'] = None
            save(status_path, status)
    require(rc == 0, 'Command exit ' + str(rc) + ': ' + str(log))


def freeze_filelist(text, old_root, new_root):
    text = text.replace(str(old_root) + '/', str(new_root) + '/')
    text = re.sub(r'(?m)^\+incdir\+' + re.escape(str(old_root)) + r'$',
                  '+incdir+' + str(new_root), text)
    old_sizes = re.findall(r'^\+define\+SIM_L2_SIZE_BYTES=(\d+)$', text, re.M)
    require(old_sizes and set(old_sizes) == {'2097152'}, 'Unexpected template memory configuration')
    text = re.sub(r'^\+define\+SIM_L2_SIZE_BYTES=2097152$',
                  '+define+SIM_L2_SIZE_BYTES=16777216', text, flags=re.M)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('+incdir+'):
            for p in line[len('+incdir+'):].split('+'):
                path = Path(p)
                require(path.is_relative_to(new_root) and path.is_dir(), 'Unsealed include: ' + p)
        elif not line.startswith(('+', '#')):
            path = Path(line)
            require(path.is_absolute() and path.is_relative_to(new_root) and path.is_file(),
                    'Unsealed source: ' + line)
    for token in ('+define+NR_LANES=4', '+define+VLEN=1024',
                  '+define+ARA_QBS_ENABLE=1', '+define+ARA_AKV_ENABLE=1',
                  '+define+ARA_AKV_V2_ENABLE=1', '+define+FOR_VERIFY'):
        require(token in text.splitlines(), 'Missing configuration: ' + token)
    require('IDEAL_DISPATCHER' not in text and 'ARA_SHARED_FMA' not in text,
            'Unexpected alternative datapath')
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepare-only', action='store_true')
    a = p.parse_args()
    out = a.output.resolve()
    require(not out.exists() and out.is_relative_to(OUT.resolve()), 'Fresh verification output required')
    out.mkdir(parents=True)
    status_path = out / 'status.json'
    status = dict(state='PREPARING', owner_pid=os.getpid(), child_pid=None,
                  started=datetime.now(timezone.utc).isoformat(), performance_measured=False)
    save(status_path, status)
    pins = {}
    try:
        require(json.loads((TEMPLATE / 'report.json').read_text())['state'] == 'PASS',
                'Source-template acceptance is missing')
        inherited = json.loads((TEMPLATE / 'source-pins.json').read_text())
        original = TEMPLATE / 'shared/source'
        sources = {f: sha for f, sha in inherited.items() if Path(f).is_relative_to(original)}
        require(len(sources) >= 400, 'Incomplete dependency snapshot')
        verify(sources)
        require(inherited.get(str(TEMPLATE / 'elfloader.o')) == digest(TEMPLATE / 'elfloader.o'),
                'Unpinned DPI loader')
        source = out / 'source'
        shutil.copytree(original, source, symlinks=False,
                        ignore=lambda directory, names: ['install'] if Path(directory) == original else [])
        revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        archive = subprocess.check_output(['git', '-C', str(ROOT), 'archive', revision, *ARCHIVE_PATHS])
        (out / 'current-source.tar').write_bytes(archive)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for item in tar:
                path = Path(item.name)
                require(not path.is_absolute() and '..' not in path.parts and
                        (item.isfile() or item.isdir() or item.issym()),
                        'Unsafe/nonregular Git archive entry')
                target = source / path
                if item.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif item.issym():
                    resolved = (target.parent / item.linkname).resolve()
                    require(path.as_posix() == 'hardware/tb/dpi/elfloader.cc' and
                            resolved.is_relative_to(source / 'hardware/deps') and resolved.is_file(),
                            'Unsealed source symlink: ' + item.name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() or target.is_symlink():
                        target.unlink()
                    target.symlink_to(item.linkname)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(item).read())
        require("localparam bit EnableSharedFma = 1'b0;" in
                (source / 'hardware/include/ara_pkg.sv').read_text(), 'Default FMA selector differs')
        filelist = out / 'sources.f'
        filelist.write_text(freeze_filelist((TEMPLATE / 'shared/sources.f').read_text(), original, source))
        dpi = out / 'elfloader.o'
        shutil.copy2(TEMPLATE / 'elfloader.o', dpi)
        monitor = out / 'boundary_monitor.sv'
        shutil.copy2(HERE / 'boundary_monitor.sv', monitor)
        sim = out / 'sim'
        sim.mkdir()
        vcs = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')
        require(vcs.is_file(), 'Host VCS is unavailable')
        command = [str(vcs), '-full64', '-sverilog', '+v2k', '-Mlib=./incremental_db',
                   '-Mupdate', '-j8', '-lca', '+nospecify', '+notimingchecks',
                   '+lint=TFIPC-L', '+vpi', '+lint=PCWM', '+error+30',
                   '-ntb_opts', 'uvm-1.2', '-top', 'ara_tb', '-timescale=1ns/100fs',
                   '+define+SIMULATION', '+define+no_warning', '+define+TSMC_NO_WARNING',
                   '+define+ARA_NO_FSDB', '+define+ARA_FAIL_FAST_ASSERTS',
                   '+define+ARA_VERIFY_UVM_CVXIF', '+define+ARA_SHARED_SIMD_MUL',
                   '-f', str(filelist), str(dpi),
                   *(str(source / path) for path in UVM), str(monitor), '-l', 'comp.vcs.log']
        config = dict(schema_version=2, config='chain_profile_area_baseline', nr_lanes=4, vlen=1024,
                      qbs_enabled=1, akv_enabled=1, akv_v2_enabled=1, sim_l2_bytes=16777216,
                      shared_simd_multiplier=1, shared_fma=0, ideal_dispatcher=0,
                      memory_note='Simulation-only capacity; no memory latency or interface-width change')
        (sim / 'simulator.conf').write_text(''.join(f'{k}={v}\n' for k, v in config.items()))
        save(out / 'plan.json', dict(revision=revision, template=str(TEMPLATE), configuration=config,
             dependencies='Frozen previously accepted snapshot, never unchecked local deps',
             production_dirty_inputs_excluded=True, current_tracked_rtl=True,
             current_software_benchmarks_required=True, new_microarchitecture=False,
             command=command, rtl_compile_only=not a.prepare_only))
        pins.update(sources)
        for path in (Path(__file__), HERE / 'boundary_monitor.sv', TEMPLATE / 'report.json',
                     TEMPLATE / 'source-pins.json', TEMPLATE / 'shared/sources.f',
                     TEMPLATE / 'elfloader.o', vcs):
            pins[str(path)] = digest(path)
        for path in out.rglob('*'):
            if path.is_file() and path.name != 'status.json':
                pins[str(path)] = digest(path)
        save(out / 'source-pins.json', pins)
        verify(pins)
        if a.prepare_only:
            status.update(state='PREPARED_NOT_COMPILED')
            save(status_path, status)
            return
        execute(command, sim, out / 'compile.log', 7200, status, status_path, 'BUILDING')
        text = (out / 'compile.log').read_text(errors='replace')
        require(not re.search(r'(?m)^(Error-|Error:|Fatal:)', text) and (sim / 'simv').is_file(),
                'RTL compilation did not succeed')
        verify(pins)
        artifacts = {str(path): digest(path) for path in sim.rglob('*') if path.is_file()}
        result = dict(state='CURRENT_AREA_SOC_BUILT_NOT_EXECUTED', simv=str(sim / 'simv'),
                      revision=revision, configuration=config, source_pins_sha256=digest(out / 'source-pins.json'),
                      post_pins_match=True, image_pins=artifacts, performance_measured=False,
                      execution='NOT_RUN', dependencies_from_accepted_snapshot=True)
        save(out / 'build.json', result)
        status.update(state=result['state'], finished=datetime.now(timezone.utc).isoformat())
        save(status_path, status)
        print(json.dumps(dict(state=result['state'], output=str(out)), flush=True))
    except BaseException as exc:
        status.update(state='FAIL', error=repr(exc), child_pid=None,
                      finished=datetime.now(timezone.utc).isoformat())
        save(status_path, status)
        raise


if __name__ == '__main__':
    def interrupted(sig, _frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    main()
