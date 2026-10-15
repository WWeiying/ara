#!/usr/bin/env python3
"""Seven source-pinned VSTU drain boundaries, sole override, no RTL edits/retry."""
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
RTL = HERE.parent/'vstu_multiword_fault_liveness01/measurement01/frozen'
VSTU = ROOT/'hardware/src/vlsu/vstu.sv'
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, v):
    with p.open('x') as f:
        json.dump(v, f, indent=2)
        f.write('\n')


def bounded(command, cwd, env, log, receipt, timeout):
    from types import SimpleNamespace
    start=time.monotonic()
    process=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
    timed_out=False
    try: code=process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True
        process.kill()
        code=process.wait()
    save(receipt,dict(actual_returncode=code,actual_elapsed_s=time.monotonic()-start,
         child_pid=process.pid,timed_out=timed_out,command=command,cwd=str(cwd),timeout_s=timeout,
         architectural_acceptance=False))
    return SimpleNamespace(returncode=code,timed_out=timed_out)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-after-rtl-complete',action='store_true',required=True)
    parser.add_argument('--vstu-sha256',required=True)
    args=parser.parse_args()
    assert sha(VSTU)==args.vstu_sha256, 'Actual notified VSTU SHA required'
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
               'lzc', 'popcount', 'delta_counter', 'counter', 'fifo_v3', 'fall_through_register')]
    files += ['hardware/src/' + n + '.sv' for n in
              ('masku/masku_operands', 'masku/masku', 'vlsu/addrgen', 'vlsu/vstu', 'ara_sequencer')]
    paths = set(files) | {'hardware/src/ara.sv', 'hardware/src/ara_dispatcher.sv'}
    for d in ('hardware/include/ara', 'hardware/deps/common_cells/include/common_cells',
              'hardware/deps/axi/include/axi'):
        paths.update(str(p.relative_to(RTL)) for p in (RTL / d).glob('*.svh'))
    pins = {}
    for p in sorted(paths):
        b = (VSTU if p=='hardware/src/vlsu/vstu.sv' else RTL/p).read_bytes()
        if p == 'hardware/src/vlsu/vstu.sv':
            assert sha(VSTU)==args.vstu_sha256 and args.vstu_sha256!='139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2', 'Actual successor VSTU must differ from retained baseline'
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
    save(out / 'pins.json', dict(rtl_root=str(RTL), files=pins))
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
    status = dict(scope='Real AddrGen/VSTU/MASKU/sequencer; modeled MMU and lane predicate source; not Linux/SoC',
                  pid=os.getpid(), cases=[], state='ERROR')
    try:
        start = time.monotonic()
        with (out / 'compile_console.log').open('x') as f:
            result = bounded(command, out, env, f, out/'compile_actual_exit_unvalidated.json', 60)
        status['compile_returncode'] = result.returncode
        status['compile_seconds'] = time.monotonic() - start
        assert result.returncode == 0 and not result.timed_out, 'Compile failed; no automatic retry'
        for vl in (1,4,5,8,9,12,16):
            marker='BOUNDARY_MASK_DRAIN_GLOBAL_IDLE'
            case = out / f'vl{vl}'
            case.mkdir()
            cmd = [str(out / 'simv'), '-no_save', f'+VL={vl}']
            save(case / 'command.json', cmd)
            start = time.monotonic()
            with (case / 'run.log').open('x') as f:
                result = bounded(cmd, case, env, f, case/'actual_exit_unvalidated.json', 60)
            log = (case / 'run.log').read_text()
            record = dict(vl=vl, returncode=result.returncode, elapsed_s=time.monotonic()-start,
                          expected_marker=marker, observed=log.count(marker)==1,
                          observations=[x for x in log.splitlines() if x.startswith('OBSERVATION ')])
            status['cases'].append(record)
            save(case / 'result.json', record)
            assert result.returncode == 0 and record['observed'] and len(record['observations']) == 1, 'Probe failed'
            assert not any(x in log for x in ('Fatal:', 'Error:', '[ASSERT FAILED]')), 'Probe assertion failed'
        assert all(sha(frozen / p) == h for p, h in pins.items()), 'Frozen drift'
        assert all(sha(VSTU if p=='hardware/src/vlsu/vstu.sv' else RTL/p)==h for p,h in pins.items() if p.startswith('hardware/')), 'Consumed baseline/sole override drift'
        status.update(state='SEVEN_BOUNDARIES_DRAINED_NOT_SOC_ACCEPTANCE', pins_unchanged=True, sole_override_vstu=True, vstu_sha256=args.vstu_sha256,
                      first_active_fault=True, AW_W_B_traffic=0,
                      pending_B_nonzero_coverage=False, RTL_edits=False,
                      host_budget_per_compile_or_case_s=60, rtl_watchdog_cycles=200,
                      measured_result_cycle=100, no_internal_state_injection=True)
    except Exception as e:
        status['error'] = repr(e)
    save(out / 'result.json', status)
    print(json.dumps(status, indent=2), flush=True)
    return int(status['state'] != 'DISCRIMINATOR_COMPLETE_NOT_ARCH_PASS')


if __name__ == '__main__':
    raise SystemExit(main())
