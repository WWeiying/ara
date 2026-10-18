#!/usr/bin/env python3
"""Test-only legal completion-consumer stall on the frozen packet-egress SoC."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    source=root/'hardware/build/production_packet_egress_soc_20261017_v1'
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    harness=root/'hardware/tb/reduction_packet_writeback_stall_test.sv'
    frozen=out/harness.name;shutil.copy2(harness,frozen)
    fl=out/'filelist';fl.write_text((source/'production/filelist').read_text()+str(frozen)+'\n')
    execution=json.loads((source/'execution.json').read_text())
    compile_cmd=list(execution['candidates']['production']['compile']['command'])
    compile_cmd[compile_cmd.index('-f')+1]=str(fl)
    compile_cmd[compile_cmd.index('-j4')]='-j2'
    elf=root/'hardware/build/exact_dense_seed_compare_20261017_v2/seedfold/inputs/perf_exact_dense_seed_latency'
    assert sha(elf)=='1f80e6a9fb17f0afb9febcdb36290e105ab58540b011be6d81fd6f41405f68d8'
    runtime=[str(out/'simv'),'-no_save','+PRELOAD='+str(elf),'+TESTCASE=perf_exact_dense_seed_latency',
             '+NO_FSDB','+PERF_WATCHDOG_CYCLES=200000','+PACKET_WB_PROFILE','+PACKET_WB_STALL_TEST','-l','run.log']
    manifest={'pass':False,'compile_command':compile_cmd,'runtime_command':runtime,
              'filelist':{'path':str(fl),'sha256':sha(fl)},
              'harness':{'path':str(frozen),'sha256':sha(frozen)},
              'original_filelist':{'path':str(source/'production/filelist'),'sha256':sha(source/'production/filelist')},
              'elf':{'path':str(elf),'sha256':sha(elf)},
              'assumptions':['Only the SLDU completion-valid consumer boundary is forced; the checker requires resulting RCE-ready=0 and stable RCE result.',
                             'This simulation injects legal consumer backpressure and does not measure production performance.']}
    for stage,cmd,timeout in [('compile',compile_cmd,1800),('run',runtime,1800)]:
        log=out/(stage+'.stdout.log')
        with log.open('w') as stream:
            proc=subprocess.run(cmd,cwd=out,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
        text=log.read_text(errors='replace')
        failures=re.findall(r'^.*(?:Error-|Error:|Fatal:|\bFAIL\b|failed at|watchdog_timeout: 1).*$',text,re.M)
        manifest[stage]={'returncode':proc.returncode,'failures':failures,'log_sha256':sha(log)}
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if proc.returncode or failures:raise SystemExit('Failed: '+str(log))
    summaries=re.findall(r'^PACKET_WB_PROFILE_SUMMARY kind=mfpu_exact .*$',text,re.M)
    dual=sum(int(re.search(r'overlap_both_fire=(\d+)',s).group(1)) for s in summaries)
    distinct=sum(int(re.search(r'distinct_data=(\d+)',s).group(1)) for s in summaries)
    cases=re.findall(r'^EXACT_DENSE_(?:SEED|SERIAL) .* PASS$',text,re.M)
    gate=re.search(r'^PACKET_WB_STALL_SUMMARY used=1 released=1 hold=(\d+) blocked_result=(\d+).*$',text,re.M)
    manifest.update(dual_fire=dual,distinct_data_overlap=distinct,cases=len(cases),
                    gate_summary=gate.group(0) if gate else None,
                    simulator_sha256=sha(out/'simv'))
    manifest['pass']=bool(dual>0 and distinct>0 and len(cases)==8 and gate and int(gate.group(2))>0 and
                          'EXACT_DENSE_LATENCY_DONE cases=8 PASS' in text and
                          'Core Test *** SUCCESS *** (tohost = 0)' in text)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ['pass','dual_fire','distinct_data_overlap','cases','gate_summary']},indent=2))
    if not manifest['pass']:raise SystemExit('Required nonzero concurrent transfer/complete 8-case coverage missing; preserved logs')


if __name__=='__main__':main()
