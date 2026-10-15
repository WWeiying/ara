#!/usr/bin/env python3
"""One frozen four-module discriminator, two fixed cases; no SoC build or retry."""
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
RTL = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources')
OLD = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources')
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
    parser.add_argument('--variant',choices=['m6','candidate'],required=True)
    parser.add_argument('--vstu-sha256')
    args=parser.parse_args()
    vstu=RTL/'hardware/src/vlsu/vstu.sv' if args.variant=='m6' else ROOT/'hardware/src/vlsu/vstu.sv'
    if args.variant=='candidate':
        assert args.vstu_sha256 and sha(vstu)==args.vstu_sha256, 'Actual candidate binding'
    out = HERE / ('measurement_'+args.variant+'01')
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
        b = (vstu if p=='hardware/src/vlsu/vstu.sv' else RTL/p).read_bytes()
        if p == 'hardware/src/vlsu/vstu.sv':
            assert sha(vstu)==(args.vstu_sha256 if args.variant=='candidate' else '139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2'), 'Exact VSTU variant source'
        dst = frozen / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b)
        dst.chmod(0o444)
        pins[p] = sha(dst)
    for name in ('suite_tb.sv','fault_tb.sv','index_tb.sv','normal_tb.sv','run.py'):
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
               '-top', 'suite_tb', '+incdir+' + str(frozen),
               '+incdir+' + str(frozen / 'hardware/include'),
               '+incdir+' + str(frozen / 'hardware/deps/common_cells/include'),
               '+incdir+' + str(frozen / 'hardware/deps/axi/include'),
               *[str(frozen / p) for p in files], *[str(frozen/n) for n in ('suite_tb.sv','fault_tb.sv','index_tb.sv','normal_tb.sv')],
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
        tests=[('normal','normal',4,'NORMAL_PATH_W_B_COMPLETE_NOT_SOC_ACCEPTANCE')]
        if args.variant=='candidate':
            tests=[('indexed_delayed_W','index',2,'GOOD_PREFIX_W_B_PRESERVED_NOT_SOC_ACCEPTANCE')]+[
                ('fault_vl'+str(vl),'fault',vl,'BOUNDARY_MASK_DRAIN_GLOBAL_IDLE')
                for vl in (1,4,5,8,9,12,16)]+tests
        for name,kind,vl,marker in tests:
            case=out/name;case.mkdir()
            cmd=[str(out/'simv'),'-no_save','+KIND='+kind,'+VL='+str(vl)]
            save(case/'command.json',cmd)
            start=time.monotonic()
            with (case/'run.log').open('x') as f:
                result=bounded(cmd,case,env,f,case/'actual_exit_unvalidated.json',60)
            log=(case/'run.log').read_text()
            records=[x for x in log.splitlines() if x.startswith(('OBSERVATION ','PREFIX_ACCEPTANCE ','NORMAL_ACCEPTANCE '))]
            record=dict(name=name,kind=kind,vl=vl,variant=args.variant,returncode=result.returncode,
                elapsed_s=time.monotonic()-start,expected_marker=marker,marker_count=log.count(marker),
                observations=records,full_SOC_acceptance=False)
            status['cases'].append(record);save(case/'result.json',record)
            assert result.returncode==0 and not result.timed_out and log.count(marker)==1,'Acceptance failed; no retry'
            assert not any(x in log for x in ('Fatal:','Error:','[ASSERT FAILED]')),'Probe assertion failed'
        assert len(status['cases'])==(9 if args.variant=='candidate' else 1),'Complete suite membership'
        assert all(sha(frozen / p) == h for p, h in pins.items()), 'Frozen drift'
        assert all(sha(vstu if p=='hardware/src/vlsu/vstu.sv' else RTL/p)==h for p,h in pins.items() if p.startswith('hardware/')),'Consumed source drift'
        status.update(state='SUITE_ACCEPTED_NOT_SOC_ACCEPTANCE', pins_unchanged=True, variant=args.variant, vstu_sha256=sha(vstu), sole_override_vstu=args.variant=='candidate', RTL_edits=False,
                      host_budget_per_compile_or_case_s=60, rtl_watchdog_cycles=200,
                      measured_result_cycle=100, no_internal_state_injection=True)
    except Exception as e:
        status['error'] = repr(e)
    save(out / 'result.json', status)
    print(json.dumps(status, indent=2), flush=True)
    return int(status['state'] != 'SUITE_ACCEPTED_NOT_SOC_ACCEPTANCE')


if __name__ == '__main__':
    raise SystemExit(main())
