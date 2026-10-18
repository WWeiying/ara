#!/usr/bin/env python3
"""Test-only ordinary-result consumer stall on the frozen packet-egress SoC."""
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
    source=root/'hardware/build/production_tail_integrated_soc_20261017_v1'
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    harness=root/'hardware/tb/reduction_normal_packet_stall_test.sv'
    frozen=out/harness.name;shutil.copy2(harness,frozen)
    fl=out/'filelist';fl.write_text((source/'production/filelist').read_text()+str(frozen)+'\n')
    prepared=json.loads((source/'manifest.json').read_text())
    compile_cmd=list(prepared['candidates']['production']['compile_command'])
    compile_cmd[compile_cmd.index('-f')+1]=str(fl)
    compile_cmd[compile_cmd.index('-j4')]='-j2'
    elf=root/'hardware/build/normal_packet_app_v1/perf_packet_normal_overlap'
    assert sha(elf)=='9dadb70f7603e2e05f2f876bf25f143630fa4b601e21fd43a1cfc5b053c36019'
    runtime=[str(out/'simv'),'-no_save','+PRELOAD='+str(elf),'+TESTCASE=perf_packet_normal_overlap',
             '+NO_FSDB','+PERF_WATCHDOG_CYCLES=200000','+PACKET_WB_PROFILE','+PACKET_NORMAL_WB_STALL_TEST','-l','run.log']
    manifest={'pass':False,'compile_command':compile_cmd,'runtime_command':runtime,
              'filelist':{'path':str(fl),'sha256':sha(fl)},
              'harness':{'path':str(frozen),'sha256':sha(frozen)},
              'original_filelist':{'path':str(source/'production/filelist'),'sha256':sha(source/'production/filelist')},
              'elf':{'path':str(elf),'sha256':sha(elf)},
              'assumptions':['Only Lane0 operand_requester consumer request INPUT NET is forced low. Producer request must remain asserted (no alias back-propagation), grant stays zero and queue head stays stable; after release consumer net must immediately return to producer request before the first younger exact packet sampling edge.',
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
    dual=sum(int(re.search(r'normal_packet_both_fire=(\d+)',s).group(1)) for s in summaries)
    drains=sum(int(re.search(r'normal_drain_fire=(\d+)',s).group(1)) for s in summaries)
    distinct=sum(int(re.search(r'normal_distinct_data=(\d+)',s).group(1)) for s in summaries)
    gate=re.search(r'^PACKET_NORMAL_STALL_SUMMARY used=1 released=1 hold=(\d+) queue_hold=(\d+).*$',text,re.M)
    marker='PACKET_NORMAL_DRAIN_DONE vl=32 checked=32 exact=420c0000 expected=420c0000 flags=0 PASS'
    manifest.update(normal_packet_both_fire=dual,normal_drain_fire=drains,normal_distinct_data=distinct,
                    gate_summary=gate.group(0) if gate else None,
                    simulator_sha256=sha(out/'simv'))
    manifest['pass']=bool(dual>0 and distinct>0 and gate and int(gate.group(2))>0 and
                          marker in text and 'Core Test *** SUCCESS *** (tohost = 0)' in text)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ['pass','normal_packet_both_fire','normal_drain_fire','normal_distinct_data','gate_summary']},indent=2))
    if not manifest['pass']:raise SystemExit('Required nonzero ordinary/packet concurrent transfer or self-check missing; preserved logs')


if __name__=='__main__':main()
