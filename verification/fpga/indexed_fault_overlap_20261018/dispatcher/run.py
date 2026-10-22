#!/usr/bin/env python3
"""Actual dispatcher fault0 ordering fixture; deliberately no numerical VRF model."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE / 'out01')
    parser.add_argument('--expect-fixed', action='store_true',
                        help='Require full m1 initial reshape=1 and retry delta=2 (fix1)')
    parser.add_argument('--uniform-index-eew8', action='store_true',
                        help='Also prove fix1 captures uniform EW8 source without normalization')
    parser.add_argument('--expect-normalized', action='store_true',
                        help='Require fix2 uniform-EW8 normalization and fault0 retry ordering')
    parser.add_argument('--dispatcher-source', type=Path,
                        help='Pin a dispatcher snapshot instead of concurrent live RTL')
    args = parser.parse_args()
    if args.expect_normalized:
        args.expect_fixed = True
        args.uniform_index_eew8 = True
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    template = ROOT / 'verification/fpga/current_board_review/dispatcher/run.py'
    spec = importlib.util.spec_from_file_location('template', template)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pins = {}

    def snapshot(relative, source=None):
        src = source or ROOT / relative
        dst = out / 'inputs' / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        pins[relative] = {'source': str(src), 'sha256': sha(dst)}
        return str(dst)

    sources = [snapshot(p) for p in module.PACKAGES]
    ara = Path(snapshot('hardware/src/ara.sv')).read_text()
    start = ara.index("  // Interfaces between Ara's dispatcher and Ara's backend\n")
    end = ara.index('  } ara_resp_t;', start) + len('  } ara_resp_t;')
    package = out / 'inputs/dispatcher_check_pkg.sv'
    package.write_text('''package dispatcher_check_pkg;
  import ara_pkg::*; import rvv_pkg::*;
  localparam config_pkg::cva6_cfg_t CVA6Cfg = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  localparam int VLEN=1024, NrLanes=4;
  typedef logic[$clog2(VLEN+1)-1:0] vlen_t;
  `include "ara/intf_typedef.svh"
  `CVA6_TYPEDEF_EXCEPTION(exception_t, CVA6Cfg)
  `CVA6_INTF_TYPEDEF_ACC_REQ(accelerator_req_t, CVA6Cfg, fpnew_pkg::roundmode_e)
  `CVA6_INTF_TYPEDEF_ACC_RESP(accelerator_resp_t, CVA6Cfg, exception_t)
''' + ara[start:end] + '\n  `include "ara/ara_typedef.svh"\nendpackage\n')
    sources.append(str(package))
    for name in ['popcount', 'delta_counter', 'counter', 'lzc']:
        sources.append(snapshot(f'hardware/deps/common_cells/src/{name}.sv'))
    sources += [snapshot('hardware/src/segment_sequencer.sv'),
                snapshot('hardware/src/ara_dispatcher.sv', args.dispatcher_source),
                snapshot(str((HERE / 'dispatcher_tb.sv').relative_to(ROOT)))]
    for directory in ['hardware/include/ara', 'hardware/deps/common_cells/include/common_cells']:
        for p in sorted((ROOT / directory).glob('*.svh')):
            snapshot(str(p.relative_to(ROOT)))
    snapshot(str(Path(__file__).resolve().relative_to(ROOT)))
    snapshot(str(template.relative_to(ROOT)))
    dump(out / 'pins.json', pins)
    diff = subprocess.check_output(['git', 'diff', 'adbc41505', '--',
                                   'hardware/src', 'hardware/include'], cwd=ROOT)
    (out / 'board_vs_current.diff').write_bytes(diff)
    dump(out / 'generated.json', {'package_sha256': sha(package)})
    vcs = '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
    env = dict(os.environ, VCS_HOME=vcs, SNPSLMD_LICENSE_FILE='27000@t7920')
    command = [vcs + '/bin/vcs', '-full64', '-sverilog', '-assert', 'svaext',
               '-timescale=1ns/1ps', '-debug_access+all', '-top', 'dispatcher_tb',
               '+incdir+' + str(out / 'inputs/hardware/deps/common_cells/include'),
               '+incdir+' + str(out / 'inputs/hardware/include'), *sources,
               '-o', str(out / 'simv')]
    run = [str(out / 'simv'), '-no_save']
    if args.expect_fixed:
        run.append('+EXPECT_FIXED')
    if args.uniform_index_eew8:
        run.append('+UNIFORM_INDEX_EEW8')
    if args.expect_normalized:
        run.append('+EXPECT_NORMALIZED')
    status = {'state': 'STARTED', 'scope': 'Actual dispatcher and segment sequencer; modeled backend acceptance/completion; no VRF or numerical claim',
              'board_source_commit': 'adbc41505d4659e779b20f39de700fedec5f4384',
              'current_rtl_differs_from_board_commit': bool(diff),
              'expect_fixed': args.expect_fixed,
              'uniform_index_eew8': args.uniform_index_eew8,
              'expect_normalized': args.expect_normalized,
              'dispatcher_source_override': str(args.dispatcher_source) if args.dispatcher_source else None,
              'partial_control': 'Legal e32/m1 VL16; vs2=v2, index EEW64/EMUL2; active source register v2',
              'historical_m2_limit': 'Historical out03/out_fixed01 m2 and pre-legal-partial runs used unaligned v2 with index EMUL4; layout negative controls only, not legal-instruction regression evidence',
              'start': time.time()}
    try:
        for name, argv, timeout in [('compile', command, 180), ('run', run, 30)]:
            dump(out / f'{name}.command.json', {'argv': argv, 'cwd': str(out),
                 'timeout_seconds': timeout, 'wait': 'Popen.wait / OS waitpid'})
            start_time = time.time()
            with (out / f'{name}.log').open('w') as log:
                proc = subprocess.Popen(argv, cwd=out, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    rc = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    raise
            dump(out / f'{name}.wait.json', {'returncode': rc,
                 'elapsed_seconds': time.time()-start_time, 'wait_completed': True})
            if rc:
                raise RuntimeError(f'{name} failed with {rc}')
        output = (out / 'run.log').read_text()
        status['results'] = [line for line in output.splitlines() if line.startswith(('RESULT ', 'DISPATCHER_'))]
        status['state'] = 'PASS' if 'DISPATCHER_PASS' in output and 'FAIL ' not in output else 'FAIL'
        for relative, pin in pins.items():
            if sha(out / 'inputs' / relative) != pin['sha256']:
                raise RuntimeError('Frozen source drift: ' + relative)
    except Exception as error:
        status.update(state='ERROR', error=repr(error))
    status['finish'] = time.time()
    dump(out / 'status.json', status)
    print(json.dumps(status, indent=2))
    return 0 if status['state']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
