#!/usr/bin/env python3
"""Snapshot and execute the complete dispatcher with host VCS, not a decode model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
HANDOFF = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_verification_handoff02')
PACKAGES = [
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/include/rvv_pkg.sv', 'hardware/include/ara_pkg.sv',
    'hardware/include/qbs_pkg.sv', 'hardware/include/akv_pkg.sv',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--dispatcher', type=Path)
    parser.add_argument('--focused', action='store_true')
    parser.add_argument('--fsdb', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pins = {}

    def snapshot(relative, source=None):
        src = source or ROOT / relative
        dst = out / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        pins[relative] = {'source': str(src), 'sha256': sha(dst)}
        return str(dst)

    # Reuse the package ordering, host setup and interface extraction approach
    # from run_units.py and generate_dispatcher_check.py without editing either.
    sources = [snapshot(path) for path in PACKAGES]
    ara = Path(snapshot('hardware/src/ara.sv')).read_text()
    start = ara.index("  // Interfaces between Ara's dispatcher and Ara's backend\n")
    end = ara.index('  } ara_resp_t;', start) + len('  } ara_resp_t;')
    package = out / 'dispatcher_check_pkg.sv'
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
    pins[package.name] = {'source': 'generated from pinned ara.sv interface', 'sha256': sha(package)}
    sources += [str(package)]
    for name in ['popcount', 'delta_counter', 'counter', 'lzc']:
        sources.append(snapshot(f'hardware/deps/common_cells/src/{name}.sv'))
    sources += [snapshot('hardware/src/segment_sequencer.sv'),
                snapshot('hardware/src/ara_sequencer.sv'),
                snapshot('hardware/src/ara_dispatcher.sv', args.dispatcher),
                snapshot(str((HERE / 'dispatcher_tb.sv').relative_to(ROOT)))]
    for directory in ['hardware/include/ara', 'hardware/deps/common_cells/include/common_cells']:
        for path in sorted((ROOT / directory).glob('*.svh')):
            snapshot(str(path.relative_to(ROOT)))
    snapshot(str(Path(__file__).resolve().relative_to(ROOT)))
    evidence = json.loads((HANDOFF / 'hashes.json').read_text())
    for name, digest in evidence.items():
        if sha(HANDOFF / name) != digest:
            raise RuntimeError('Historical handoff hash mismatch: ' + name)
    (out / 'historical_pins.json').write_text(json.dumps(evidence, indent=2) + '\n')
    (out / 'pins.json').write_text(json.dumps(pins, indent=2) + '\n')
    vcs = '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
    verdi = '/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1'
    env = dict(os.environ, VCS_HOME=vcs, VERDI_HOME=verdi, SNPSLMD_LICENSE_FILE='27000@t7920')
    env['PATH'] = f'{vcs}/bin:{verdi}/bin:' + env['PATH']
    command = ['vcs', '-full64', '-sverilog', '-assert', 'svaext', '-timescale=1ns/1ps',
               '-debug_access+all', '-top', 'dispatcher_tb',
               '+incdir+' + str(out / 'hardware/deps/common_cells/include'),
               '+incdir+' + str(out / 'hardware/include'), *sources,
               '-o', str(out / 'simv'), '-l', str(out / 'compile.log')]
    if args.fsdb:
        pli = Path(verdi) / 'share/PLI/VCS/LINUX64'
        command += ['-P', str(pli / 'novas.tab'), str(pli / 'pli.a'), '+define+TRACE_FSDB']
    run = [str(out / 'simv'), '-no_save', '-l', str(out / 'run.log')]
    if args.focused:
        run += ['+FOCUSED']
    (out / 'commands.json').write_text(json.dumps([command, run], indent=2) + '\n')
    status = {'state': 'STARTED', 'start': time.time(), 'scope':
              'Complete dispatcher, segment and sequencer RTL; PE acceptance fixture, no numerical execution'}
    try:
        with (out / 'compile.console.log').open('w') as log:
            result = subprocess.run(command, cwd=out, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=240)
        status['compile_exit'] = result.returncode
        if result.returncode:
            raise RuntimeError('VCS compilation failed')
        status['image'] = {str(p.relative_to(out)): sha(p) for p in
                           [out / 'simv', *sorted((out / 'simv.daidir').rglob('*.so'))]}
        with (out / 'run.console.log').open('w') as log:
            result = subprocess.run(run, cwd=out, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=60)
        status['run_exit'] = result.returncode
        output = (out / 'run.log').read_text()
        status['results'] = [line for line in output.splitlines()
                             if line.startswith(('RESULT ', 'FAIL ', 'DISPATCHER_'))]
        status['state'] = 'PASS' if result.returncode == 0 and 'DISPATCHER_PASS' in output and not re.search(
            r'(?m)^(Error|Fatal)(-|:|\[)', output) else 'FAIL'
        for name, pin in pins.items():
            if sha(out / name) != pin['sha256']:
                raise RuntimeError('Snapshot drift: ' + name)
        for name, digest in status['image'].items():
            if sha(out / name) != digest:
                raise RuntimeError('Executable drift: ' + name)
    except Exception as error:
        status.update(state='ERROR', error=repr(error))
    status['finish'] = time.time()
    (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(status, indent=2))
    return 0 if status['state'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
