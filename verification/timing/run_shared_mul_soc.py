#!/usr/bin/env python3
"""Build a matched complete SoC pair and run independently checked firmware.

Run directly under a systemd user service. Never changes production build dirs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, indent=2)+'\n')
    tmp.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    status = dict(state='PREPARING',started=datetime.now(timezone.utc).isoformat())
    def state(**changes):
        status.update(changes)
        save(out/'status.json',status)
    selection=json.loads((ROOT/'verification/timing/shared_mul_selected.json').read_text())
    for rel,sha in selection['source_sha256'].items():
        if digest(ROOT/rel) != sha:
            raise RuntimeError('Selected multiplier source drift: '+rel)
    names=['rv64uv-ara-'+n for n in ('vmul','vmulh','vmulhu','vmulhsu',
        'vsmul','vmacc','vmadd','vnmsac','vnmsub','vwmul','vwmulu','vwmulsu',
        'vwmacc','vwmaccu','vwmaccsu','vwmaccus')]+['dotproduct','imatmul']
    inputs=out/'inputs'; inputs.mkdir()
    for name in names:
        source=ROOT/'apps/bin'/name
        if not source.is_file(): raise RuntimeError('Missing ELF: '+str(source))
        shutil.copy2(source,inputs/name)
    save(out/'elf_hashes.json',{n:digest(inputs/n) for n in names})
    monitor=ROOT/'verification/timing/shared_mul_soc_monitor.sv'
    pins={str(f):digest(f) for f in (Path(__file__).resolve(),monitor,
          ROOT/'hardware/Makefile', ROOT/'hardware/src/lane/vmfpu.sv',
          *(ROOT/r for r in selection['source_sha256']))}
    save(out/'source-pins.json',pins)
    def check_pins():
        for f,sha in pins.items():
            if digest(Path(f))!=sha: raise RuntimeError('Source drift: '+f)
    def build(variant):
        folder=out/variant; folder.mkdir()
        defs='+define+SIMULATION +define+no_warning +define+TSMC_NO_WARNING +define+ARA_NO_FSDB +define+ARA_FAIL_FAST_ASSERTS'
        if variant=='shared': defs+=' +define+ARA_SHARED_SIMD_MUL'
        cmd=['make','-C',str(ROOT/'hardware'),'compile','config=default','nr_lanes=4',
             'vlen=1024','qbs=1','akv=1','akv_v2=1','sim_l2_mb=2','mc=0',
             'code_coverage=0','no_fsdb=1','verify_source_manifest=1',
             'fail_on_assert=1',f'buildpath={folder}/build',f'sim_dir={folder}/sim',
             f'verify_extra_sources={monitor}',f'SIMULATOR_DEF={defs}',
             'SIMULATOR_OPT=-full64 -sverilog +v2k -Mlib=./incremental_db -Mupdate -j8 -lca -kdb -debug_access+all +nospecify +notimingchecks +lint=TFIPC-L +vpi +lint=PCWM +error+30']
        save(folder/'command.json',dict(command=cmd,cwd=str(ROOT)))
        with (folder/'build.log').open('w') as log:
            subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=7200)
        check_pins()
        save(folder/'image.json',dict(simv_sha256=digest(folder/'sim/simv'),
             shared_define=variant=='shared'))
        return variant
    try:
        state(state='BUILDING')
        with ThreadPoolExecutor(max_workers=2) as pool:
            for result in as_completed([pool.submit(build,v) for v in ('baseline','shared')]):
                print('BUILD_PASS '+result.result(),flush=True)
        # Validate that both builds consumed identical source contents. Filelist
        # and separately compiled DPI objects have variant-specific paths.
        manifests=[json.loads((out/v/'sim/vcs_source_manifest.json').read_text()) for v in ('baseline','shared')]
        common=[]
        for m in manifests:
            common.append({r['path']:r['sha256'] for r in m['files']
                           if not Path(r['path']).is_relative_to(out)})
        if common[0]!=common[1]: raise RuntimeError('SoC build source mismatch')
        state(state='RUNNING',completed=0,total=2*len(names))
        rows=[]
        def run(variant,name):
            work=out/variant/'cases'/name; work.mkdir(parents=True)
            simv=out/variant/'sim/simv'
            cmd=[str(simv),'-no_save','-l','run.vcs.log',f'+PRELOAD={inputs/name}',
                 f'+TESTCASE={name}','+NO_FSDB','+ntb_random_seed=1']
            save(work/'command.json',dict(command=cmd,cwd=str(work),timeout=1800,elf_sha256=digest(inputs/name)))
            with (work/'console.log').open('w') as log:
                try:
                    rc=subprocess.run(cmd,cwd=work,stdout=log,stderr=subprocess.STDOUT,timeout=1800).returncode
                except subprocess.TimeoutExpired:
                    rc=124
            text=(work/'console.log').read_text(errors='replace')
            mode='MUL_SOC_MODE '+variant
            activity=re.findall(r'MUL_SOC_ACTIVITY .*accepted=(\d+),(\d+),(\d+),(\d+) completed=(\d+),(\d+),(\d+),(\d+) blocked=(\d+)',text)
            fail=bool(re.search(r'Fatal:|Error:|\*\*\* FAILED|\bFAILED\b',text))
            passed=rc==0 and 'Core Test *** SUCCESS ***' in text and not fail and text.count(mode)==4 and len(activity)==4
            if passed:
                passed=all(list(map(int,r[:4]))==list(map(int,r[4:8])) for r in activity) and sum(int(x) for r in activity for x in r[:4])>0
            result=dict(variant=variant,case=name,status='PASS' if passed else 'FAIL',
                        returncode=rc,activity=activity,
                        cycles=re.findall(r'^\[PERF\] total_cycles\s*:\s*(\d+)',text,re.M),
                        kernel_cycles=re.findall(r'The execution took (\d+) cycles',text))
            save(work/'result.json',result)
            return result
        # Each pair completes before the next firmware is dispatched. Stop on
        # failure, preserve both logs, and do not repair a running campaign.
        for name in names:
            check_pins()
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda v:run(v,name),('baseline','shared')))
            rows.extend(results)
            save(out/'results.json',rows)
            if any(r['status']!='PASS' for r in results):
                state(state='CASE_FAILED',case=name,completed=len(rows))
                return 1
            state(completed=len(rows))
        state(state='INITIAL_MATRIX_PASS',completed=len(rows),
              remaining='Dedicated mixed-SEW/dependency stimulus and performance acceptance review')
        return 0
    except Exception as exc:
        state(state='ERROR',error=str(exc))
        raise


if __name__=='__main__':
    raise SystemExit(main())
