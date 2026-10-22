#!/usr/bin/env python3
"""Frozen real-VSTU public-port checks; no production edits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')
FILES = [
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/include/rvv_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/include/ara_pkg.sv',
    'hardware/deps/common_cells/src/fifo_v3.sv',
    'hardware/deps/common_cells/src/fall_through_register.sv',
    'hardware/deps/common_cells/src/spill_register_flushable.sv',
    'hardware/src/vlsu/vstu.sv',
    str((HERE / 'vstu_public_tb.sv').relative_to(ROOT)),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--rtl-root', type=Path, default=ROOT)
    args = parser.parse_args()
    out = args.out.resolve()
    if out == HERE or not out.is_relative_to(HERE):
        raise ValueError('Output must be a new owned subdirectory')
    out.mkdir(parents=True, exist_ok=False)
    source_root = args.rtl_root.resolve()
    paths = set(FILES) | {str(Path(__file__).resolve().relative_to(ROOT)),
                          str((HERE / 'README.md').relative_to(ROOT))}
    for directory in ('hardware/include/ara', 'hardware/deps/common_cells/include/common_cells',
                      'hardware/deps/axi/include/axi'):
        paths.update(str(p.relative_to(source_root))
                     for p in (source_root / directory).glob('*.svh'))
    def source(path):
        return (source_root if path.startswith('hardware/') else ROOT) / path
    pins = {p: sha(source(p)) for p in sorted(paths)}
    frozen = out / 'frozen'
    for path, digest in pins.items():
        target = frozen / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source(path).read_bytes())
        assert sha(target) == digest, path
        target.chmod(0o444)
    assert pins == {p: sha(source(p)) for p in pins}, 'Snapshot drift'
    save(out / 'pins.json', dict(files=pins, rtl_root=str(source_root),
                                 scope='real VSTU unit, modeled public peers, not SoC'))
    env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
    env.update(PATH=f'{VCS}/bin:/usr/bin:/bin', VCS_HOME=str(VCS),
               VCS_TARGET_ARCH='linux64', SNPSLMD_LICENSE_FILE='27000@t7920',
               LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
    cmd = [str(VCS / 'bin/vcs'), '-full64', '-sverilog', '-timescale=1ns/1ps',
           '-top', 'vstu_public_tb',
           '+incdir+' + str(frozen / 'hardware/deps/common_cells/include'),
           '+incdir+' + str(frozen / 'hardware/include'),
           *[str(frozen / p) for p in FILES], '-o', str(out / 'simv'),
           '-l', str(out / 'compile.log')]
    save(out / 'command.json', cmd)
    status = dict(state='STARTED')
    save(out / 'status.json', status)
    try:
        start = time.monotonic()
        with (out / 'compile.console.log').open('w') as log:
            subprocess.run(cmd, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                           timeout=180, check=True)
        status['compile_seconds'] = time.monotonic() - start
        command = [str(out / 'simv'), '-no_save']
        save(out / 'run.command.json', command)
        start = time.monotonic()
        with (out / 'run.log').open('w') as log:
            result = subprocess.run(command, cwd=out, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=30)
        status.update(run_seconds=time.monotonic() - start, returncode=result.returncode)
        logtext = (out / 'run.log').read_text()
        status['cases'] = re.findall(r'^CASE_PASS .*$', logtext, re.M)
        status['stores'] = re.findall(r'^STORE_PASS .*$', logtext, re.M)
        status['state'] = ('PASS' if result.returncode == 0 and len(status['cases']) == 6
                           and len(status['stores']) == 12 and 'SUITE_PASS cases=6 stores=12' in logtext
                           and not re.search(r'(?im)^(?:Error|Fatal|Assertion failed)', logtext)
                           else 'FAIL')
        assert pins == {p: sha(frozen / p) for p in pins}, 'Frozen drift'
        status['frozen_verified'] = True
    except Exception as error:
        status.update(state='ERROR', error=repr(error))
    save(out / 'status.json', status)
    print(json.dumps(status, indent=2), flush=True)
    return status['state'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
