#!/usr/bin/env python3
"""Candidate VLDU drain: seven real-module fault boundaries, no SoC build/retry."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
RTL = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources')
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, v):
    with p.open('x') as f:
        json.dump(v, f, indent=2)
        f.write('\n')


def main():
    out = HERE / 'measurement01'
    out.mkdir(exist_ok=False)
    frozen = out / 'frozen'
    files = ['hardware/deps/common_cells/src/cf_math_pkg.sv',
             'hardware/deps/axi/src/axi_pkg.sv',
             'hardware/deps/cva6/core/include/config_pkg.sv',
             'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
             'hardware/deps/cva6/core/include/riscv_pkg.sv',
             'hardware/deps/cva6/core/include/build_config_pkg.sv',
             'hardware/include/rvv_pkg.sv', 'hardware/deps/fpnew/src/fpnew_pkg.sv',
             'hardware/include/ara_pkg.sv']
    files += ['hardware/deps/common_cells/src/' + n + '.sv' for n in
              ('spill_register_flushable', 'spill_register', 'stream_register',
               'lzc', 'popcount', 'delta_counter', 'counter', 'fifo_v3')]
    files += ['hardware/src/' + n + '.sv' for n in
              ('masku/masku_operands', 'masku/masku', 'vlsu/addrgen', 'vlsu/vldu', 'ara_sequencer')]
    paths = set(files) | {'hardware/src/ara.sv', 'hardware/src/ara_dispatcher.sv'}
    for d in ('hardware/include/ara', 'hardware/deps/common_cells/include/common_cells',
              'hardware/deps/axi/include/axi'):
        paths.update(str(p.relative_to(RTL)) for p in (RTL / d).glob('*.svh'))
    pins = {}
    for p in sorted(paths):
        source = ROOT / p if p == 'hardware/src/vlsu/vldu.sv' else RTL / p
        b = source.read_bytes()
        assert b == (ROOT / p).read_bytes(), 'Current/frozen drift: ' + p
        dst = frozen / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b)
        dst.chmod(0o444)
        pins[p] = sha(dst)
    for name in ('probe_tb.sv', 'run.py'):
        dst = frozen / name
        dst.write_bytes((HERE / name).read_bytes())
        dst.chmod(0o444)
        pins[name] = sha(dst)
    source = (frozen / 'hardware/src/ara.sv').read_text()
    types = []
    for name in ('ara_req_t', 'ara_resp_t'):
        matches = re.findall(r'typedef struct packed \{[^}]*\} ' + name + ';', source)
        assert len(matches) == 1, name
        types.append(matches[0])
    dst = frozen / 'sequencer_types.svh'
    dst.write_text('\n'.join(types) + '\n')
    dst.chmod(0o444)
    pins[dst.name] = sha(dst)
    save(out / 'pins.json', dict(rtl_root=str(RTL), files=pins,
        candidate_source=str(ROOT / 'hardware/src/vlsu/vldu.sv'),
        baseline_vldu_sha256=sha(RTL / 'hardware/src/vlsu/vldu.sv')))
    env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
    env.update(PATH=f'{VCS}/bin:/usr/bin:/bin', VCS_HOME=str(VCS), VCS_TARGET_ARCH='linux64',
               SNPSLMD_LICENSE_FILE='27000@t7920', LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
    command = [str(VCS / 'bin/vcs'), '-full64', '-sverilog', '-timescale=1ns/1ps',
               '-top', 'probe_tb', '+incdir+' + str(frozen),
               '+incdir+' + str(frozen / 'hardware/include'),
               '+incdir+' + str(frozen / 'hardware/deps/common_cells/include'),
               '+incdir+' + str(frozen / 'hardware/deps/axi/include'),
               *[str(frozen / p) for p in files], str(frozen / 'probe_tb.sv'),
               '-o', str(out / 'simv'), '-l', str(out / 'compile.log')]
    save(out / 'compile_command.json', command)
    status = dict(scope='Real AddrGen/VLDU/MASKU/sequencer; modeled MMU and lane predicate source; not Linux/SoC',
                  pid=os.getpid(), cases=[], state='ERROR',
                  case_scope='e64m4 vm0 start0 stride0 cause13 first-element fault; VL1/4/5/8/9/12/16',
                  host_run_timeout_s=60, rtl_watchdog_ns=2000)
    try:
        start = time.monotonic()
        with (out / 'compile_console.log').open('x') as f:
            result = subprocess.run(command, cwd=out, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=90)
        status['compile_returncode'] = result.returncode
        status['compile_seconds'] = time.monotonic() - start
        assert result.returncode == 0, 'Compile failed; no automatic retry'
        for vl in (8, 9, 1, 4, 5, 12, 16):
            marker = 'PREDICATE_DRAIN_IDLE_PASS'
            case = out / f'vl{vl}'
            case.mkdir()
            cmd = [str(out / 'simv'), '-no_save', f'+VL={vl}']
            save(case / 'command.json', cmd)
            start = time.monotonic()
            with (case / 'run.log').open('x') as f:
                result = subprocess.run(cmd, cwd=case, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=60)
            log = (case / 'run.log').read_text()
            record = dict(vl=vl, returncode=result.returncode, elapsed_s=time.monotonic()-start,
                          expected_marker=marker, observed=log.count(marker)==1,
                          observations=[x for x in log.splitlines() if x.startswith('OBSERVATION ')])
            status['cases'].append(record)
            save(case / 'result.json', record)
            assert result.returncode == 0 and record['observed'] and len(record['observations']) == 1, 'Probe failed'
            assert not any(x in log for x in ('Fatal:', 'Error:', '[ASSERT FAILED]')), 'Probe assertion failed'
        assert all(sha(frozen / p) == h for p, h in pins.items()), 'Frozen drift'
        assert all(sha(ROOT / p) == h and
                   (p == 'hardware/src/vlsu/vldu.sv' or sha(RTL / p) == h)
                   for p, h in pins.items() if p.startswith('hardware/')), 'Input drift'
        status.update(state='SEVEN_MASKED_FIRST_FAULT_BOUNDARIES_PASS_NOT_SOC', pins_unchanged=True)
    except Exception as e:
        status['error'] = repr(e)
    save(out / 'result.json', status)
    print(json.dumps(status, indent=2), flush=True)
    return int(status['state'] != 'SEVEN_MASKED_FIRST_FAULT_BOUNDARIES_PASS_NOT_SOC')


if __name__ == '__main__':
    raise SystemExit(main())
