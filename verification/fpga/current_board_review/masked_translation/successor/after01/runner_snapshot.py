"""Independent frozen real-AddrGen successor; modeled MMU/masks/descriptor sink."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

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
    'hardware/include/rvv_pkg.sv', 'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/include/ara_pkg.sv',
    'hardware/deps/common_cells/src/spill_register_flushable.sv',
    'hardware/deps/common_cells/src/lzc.sv',
    'hardware/deps/common_cells/src/fifo_v3.sv', 'hardware/src/vlsu/addrgen.sv',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--rtl-root', type=Path, default=ROOT)
    parser.add_argument('--cases', default=','.join(map(str, range(32))))
    args = parser.parse_args()
    out, root = args.out.resolve(), args.rtl_root.resolve()
    if not out.is_relative_to(HERE) or out == HERE:
        parser.error('new output must be inside successor/')
    cases = [int(x) for x in args.cases.split(',')]
    if any(x not in range(32) for x in cases) or len(set(cases)) != len(cases):
        parser.error('unique cases 0..31 required')
    out.mkdir(parents=True, exist_ok=False)
    frozen = out / 'frozen'
    paths = set(FILES)
    for folder in ('hardware/include/ara', 'hardware/deps/common_cells/include/common_cells',
                   'hardware/deps/axi/include/axi'):
        paths.update(str(p.relative_to(root)) for p in (root / folder).glob('*.svh'))
    pins = {}
    for rel in sorted(paths):
        dest = frozen / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        original = sha(root / rel)
        shutil.copyfile(root / rel, dest)
        assert sha(dest) == original, 'input changed during freeze'
        pins[rel] = original
        dest.chmod(0o444)
    tb = frozen / 'addrgen_successor_tb.sv'
    shutil.copyfile(HERE / tb.name, tb)
    shutil.copyfile(Path(__file__), out / 'runner_snapshot.py')
    save(out / 'pins.json', dict(rtl_root=str(root), files=pins, tb_sha256=sha(tb),
        real_rtl=['AddrGen'], models=['MMU delayed response', 'mask windows', 'index source',
                                    'descriptor sink', 'parent lifetime'],
        no_force=True, original_case_replay=False, real_consumer_validation=False))
    env = os.environ.copy()
    env.update(VCS_HOME=str(VCS), VCS_TARGET_ARCH='linux64',
               SNPSLMD_LICENSE_FILE='27000@t7920', LM_LICENSE_FILE='27000@t7920')
    command = [str(VCS / 'bin/vcs'), '-full64', '-sverilog', '-timescale=1ns/1ps',
               '-top', 'addrgen_successor_tb',
               '+incdir+' + str(frozen / 'hardware/deps/common_cells/include'),
               '+incdir+' + str(frozen / 'hardware/deps/axi/include'),
               '+incdir+' + str(frozen / 'hardware/include'),
               *[str(frozen / p) for p in FILES], str(tb), '-o', str(out / 'simv')]
    save(out / 'compile-command.json', command)
    status = dict(state='FROZEN', cases=[], real_consumer_validation=False)
    save(out / 'status.json', status)
    print('FROZEN ' + str(out), flush=True)
    try:
        with (out / 'compile.log').open('w') as log:
            subprocess.run(command, cwd=out, env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=240)
        for case in cases:
            run = out / f'case{case:02d}'
            run.mkdir()
            cmd = [str(out / 'simv'), '-no_save', f'+CASE={case}']
            save(run / 'command.json', cmd)
            with (run / 'run.log').open('w') as log:
                result = subprocess.run(cmd, cwd=run, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=30)
            text = (run / 'run.log').read_text()
            markers = [line for line in text.splitlines() if line.startswith('LOCAL_PASS ')]
            passed = result.returncode == 0 and len(markers) == 1 and 'Fatal:' not in text
            status['cases'].append(dict(case=case, status='PASS' if passed else 'FAIL',
                                        marker=markers, returncode=result.returncode))
            save(out / 'status.json', status)
            print(f'case{case:02d} ' + ('PASS' if passed else 'FAIL'), flush=True)
        status['frozen_unchanged'] = all(sha(frozen / p) == h for p, h in pins.items())
        status['state'] = 'PASS' if status['frozen_unchanged'] and all(
            c['status'] == 'PASS' for c in status['cases']) else 'FAIL'
    except Exception as error:
        status.update(state='HARNESS_ERROR', error=repr(error))
    save(out / 'status.json', status)
    print('COMPLETE ' + status['state'], flush=True)
    return status['state'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
