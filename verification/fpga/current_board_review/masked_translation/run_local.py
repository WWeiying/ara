#!/usr/bin/env python3
"""Freeze and run only the real AddrGen and its local dependency closure."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
R = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')
FILES = [
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/include/rvv_pkg.sv', 'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/include/ara_pkg.sv',
    'hardware/deps/common_cells/src/spill_register_flushable.sv',
    'hardware/deps/common_cells/src/lzc.sv',
    'hardware/deps/common_cells/src/fifo_v3.sv',
    'hardware/src/vlsu/addrgen.sv',
    str((HERE / 'addrgen_translation_tb.sv').relative_to(ROOT)),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def provenance():
    release = C / 'rvv_small_exceptions01'
    manifest = json.loads((release / 'manifest.json').read_text())
    case = next(c for c in manifest['cases'] if c['name'] == 'rvv_small_exceptions_e16_scenario3')
    paths = {
        release / 'binaries' / case['name']: case['sha256'],
        C / 'rvv_recovery08_202/resume/binaries' / case['original_name']: case['original_elf_sha256'],
        release / (case['original_name'] + '.original.elf'): case['original_elf_sha256'],
        R / 'exception_oracle.c': 'af36b5d8475b2949e09957ad742bbb863d0b5a59c5cf9cd959edc2dc6bc86794',
        release / 'manifest.json': 'c6d7c465085cf029c57136a7b09e79d3c232e3db2582dcfba3b2f4254b60b26c',
    }
    for name, sha in case['scenario_sources'].items():
        paths[release / case['name'] / name] = sha
    for path, sha in paths.items():
        require(digest(path) == sha, 'Original input drift: ' + str(path))
    return dict(scope='Linux original/reduced inputs read and rehashed only; not executed by this local fixture',
                case=case, files={str(p): s for p, s in paths.items()})


def environment():
    env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
    env.update(PATH=f'{VCS}/bin:/usr/bin:/bin', VCS_HOME=str(VCS),
               VCS_TARGET_ARCH='linux64', SNPSLMD_LICENSE_FILE='27000@t7920',
               LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
    return env


def analyze(path, fault):
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    events = {}
    for field in ('mmu_valid', 'push', 'desc_valid', 'ar_valid', 'ack', 'ack_exception'):
        events[field] = [int(r['cycle']) for r in rows if r[field] == '1']
    requests = [int(r['cycle']) for r in rows if r['mmu_req'] == '1']
    require(requests and len(events['mmu_valid']) == 1, 'No uniquely bound MMU response')
    response = events['mmu_valid'][0]
    require(response == requests[0] + 3, 'Response delay differs')
    require(events['push'] == [response] and events['desc_valid'] == [response + 1], 'Descriptor order')
    require(events['ack'] == [response + int(fault)], 'Ack order')
    require(events['ack_exception'] == ([response + 1] if fault else []), 'Exception propagation')
    require(events['ar_valid'] == ([] if fault else [response]), 'Physical transaction order')
    return dict(request_high_cycles=requests, events=events,
                architectural_pass=None,
                interpretation='Unexpected all-off fault reproduced' if path.parent.name == 'alloff_fault'
                else 'Active fault control' if fault else 'All-off still translates and issues AR; no architectural completion oracle here')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    require(out.is_relative_to(HERE) and out != HERE, 'Owned output directory required')
    out.mkdir(parents=True, exist_ok=False)
    original = provenance()
    save(out / 'linux_provenance.json', original)
    paths = set(FILES) | {str(Path(__file__).resolve().relative_to(ROOT))}
    for directory in ('hardware/include/ara', 'hardware/deps/common_cells/include/common_cells',
                      'hardware/deps/axi/include/axi'):
        paths.update(str(p.relative_to(ROOT)) for p in (ROOT / directory).glob('*.svh'))
    before = {p: digest(ROOT / p) for p in sorted(paths)}
    frozen = out / 'frozen'
    for p, sha in before.items():
        target = frozen / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / p).read_bytes())
        require(digest(target) == sha, 'Source changed during copy: ' + p)
        target.chmod(0o444)
    require(before == {p: digest(ROOT / p) for p in before}, 'Live snapshot drift')
    pins = dict(files=before, rtl_modified=False, top='addrgen_translation_tb',
                nr_lanes=4, vlen=1024, axi_data_width=256, mmu_model_response_delay_cycles=3)
    save(out / 'pins.json', pins)
    command = [str(VCS / 'bin/vcs'), '-full64', '-sverilog', '-timescale=1ns/1ps',
               '-top', 'addrgen_translation_tb',
               '+incdir+' + str(frozen / 'hardware/deps/common_cells/include'),
               '+incdir+' + str(frozen / 'hardware/deps/axi/include'),
               '+incdir+' + str(frozen / 'hardware/include'),
               *[str(frozen / p) for p in FILES], '-o', str(out / 'simv'),
               '-l', str(out / 'compile.log')]
    save(out / 'command.json', command)
    status = dict(state='STARTED', scope='EXPECTED_REPRODUCTION_NOT_ARCHITECTURAL_PASS', cases=[])
    save(out / 'status.json', status)
    try:
        begin = time.monotonic()
        with (out / 'compile.console.log').open('w') as log:
            subprocess.run(command, cwd=out, env=environment(), stdout=log,
                           stderr=subprocess.STDOUT, timeout=180, check=True)
        status['compile_seconds'] = time.monotonic() - begin
        for variant, name in enumerate(('alloff_fault', 'active_fault', 'alloff_valid')):
            run = out / name
            run.mkdir()
            cmd = [str(out / 'simv'), '-no_save', f'+CASE={variant}']
            start = time.monotonic()
            with (run / 'run.log').open('w') as log:
                result = subprocess.run(cmd, cwd=run, env=environment(), stdout=log,
                                        stderr=subprocess.STDOUT, timeout=20)
            text = (run / 'run.log').read_text()
            markers = [line for line in text.splitlines() if line.startswith('DISCRIMINATOR_EXPECTATION_PASS ')]
            require(result.returncode == 0 and len(markers) == 1 and 'Fatal:' not in text, 'Fixture failed: ' + name)
            evidence = analyze(run / 'cycles.csv', variant != 2)
            evidence.update(name=name, command=cmd, exit_code=result.returncode,
                            expected_reproduction_pass=True, elapsed_seconds=time.monotonic() - start,
                            marker=markers[0], wave_bytes=(run / 'window.vcd').stat().st_size)
            require(0 < evidence['wave_bytes'] < 4 * 1024 * 1024, 'Unbounded/empty waveform')
            status['cases'].append(evidence)
            save(out / 'status.json', status)
            print(name, 'EXPECTED_REPRODUCTION_PASS (not architecture PASS)', flush=True)
        require(before == {p: digest(frozen / p) for p in before}, 'Frozen input drift')
        require(original == provenance(), 'Original Linux provenance drift')
        status['state'] = 'EXPECTED_REPRODUCTION_PASS'
        status['frozen_verified_after_run'] = True
        status['original_linux_verified_after_run'] = True
        status['artifacts'] = {str(p.relative_to(out)): digest(p) for p in out.rglob('*')
                               if p.is_file() and p.suffix in ('.csv', '.vcd', '.log')}
    except Exception as error:
        status.update(state='ERROR', error=repr(error))
    save(out / 'status.json', status)
    print(json.dumps(status, indent=2))
    return status['state'] != 'EXPECTED_REPRODUCTION_PASS'


if __name__ == '__main__':
    raise SystemExit(main())
