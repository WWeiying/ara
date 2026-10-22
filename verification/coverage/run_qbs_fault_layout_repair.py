#!/usr/bin/env python3
"""Independent image and bounded fault-layout regression; never merge old VDBs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import audit_gap71_custom as gap71
import audit_gap73_akv as gap73
import build_memory_vl0_repair as builder
import custom_backend_lifetime

base = builder.base
ROOT = base.ROOT
OLD = ROOT / 'verification/out/closure92-current-20261005-01'
PREFLIGHT = ROOT / 'verification/out/gap71-custom-preflight-20261005-08'
NAMES = ['gap71_qbs_fault', 'gap71_qbs_read', 'gap71_akv_fault',
         'gap71_akv_read', 'akv_gap73_v1_onehot']


def audit(directory, name):
    elf = directory / 'input.elf'
    log = (directory / 'run.vcs.log').read_text()
    commit = directory / 'commit_trace.csv'
    vector = directory / 'vector_trace.csv'
    if name.startswith('gap71_'):
        record = base.read(PREFLIGHT / 'execution-proof.json')[name]['dut']
        base.check({str(elf): record['elf_sha256']})
        return dict(stdout=gap71.validate_log(log,name,'custom-dut'),
                    traces=gap71.runtime_traces(commit,vector,name,record['metadata']),
                    perf=gap71.runtime_perf(log,name))
    info = gap73.elf_audit(elf.read_bytes())
    result = gap73.commit_audit(commit.read_text(),info)
    return dict(stdout=gap73.stdout_audit(log,info),commit=result,
                vector=gap73.vector_audit(vector.read_text(),result['commands']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = base.checked_output(args.output)
    base.check_service()
    output.mkdir(exist_ok=False)
    state = dict(status='PREPARING',phase='offline checker replay',
                 formal_coverage_collected=False,old_vdb_reuse=False,cases={})
    def save(): base.save(output / 'status.json',state)
    save()
    try:
        old = OLD / 'results/akv_gap73_v1_onehot/tests/app_akv_gap73_v1_onehot'
        replay = output / 'old-akv-checker-replay'
        replay.mkdir()
        for src,dst in [('input.elf','input.elf'),('commit_trace.csv','commit_trace.csv'),
                        ('work/vector_trace.csv','vector_trace.csv'),('work/run.vcs.log','run.vcs.log')]:
            shutil.copyfile(old / src,replay / dst)
        base.save(replay / 'audit.json',dict(status='PASS',result=audit(replay,NAMES[-1]),
                    files=base.pins(replay.iterdir()),scope='existing-image checker replay only'))
        state.update(status='BUILDING',phase='independent VCS image');save()
        original_argv = sys.argv
        sys.argv = [builder.__file__,'--output',str(output / 'image'),
                    '--approved-dispatcher-sha256',base.sha256(builder.DISPATCHER)]
        try: builder.main()
        finally: sys.argv = original_argv
        image = output / 'image/sim/simv'
        pins = base.read(output / 'image/build-source-pins.json')
        pins.update(base.pins([Path(__file__),Path(gap71.__file__),Path(gap73.__file__),
                               Path(custom_backend_lifetime.__file__)]))
        base.check(pins)
        base.save(output / 'regression-source-pins.json',pins)
        state.update(status='RUNNING',phase='five parallel bounded regressions');save()

        def run(name):
            directory = output / 'results' / name
            directory.mkdir(parents=True)
            old = OLD / 'results' / name / 'tests' / ('app_' + name)
            shutil.copyfile(old / 'input.elf',directory / 'input.elf')
            base.check({str(directory / 'input.elf'):base.sha256(old / 'input.elf')})
            command = [str(image),'-l','run.vcs.log','+ntb_random_seed=1',
                '+PRELOAD='+str(directory / 'input.elf'),'+TESTCASE='+name,'+NO_FSDB',
                '+COMMIT_TRACE='+str(directory / 'commit_trace.csv'),
                '+VECTOR_TRACE='+str(directory / 'vector_trace.csv'),
                '+QBS_PERF' if 'qbs' in name else '+AKV_PERF',
                '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(directory / 'code.vdb'),
                '-cm_name',name]
            if name == 'gap71_qbs_fault': command.append('+ARA_DEBUG_EEW')
            base.save(directory / 'command.json',dict(command=command,cwd=str(directory),timeout_s=1800))
            result = dict(status='RUNNING',directory=str(directory))
            try:
                with (directory / 'console.log').open('w') as stream:
                    subprocess.run(command,cwd=directory,stdout=stream,stderr=subprocess.STDOUT,
                                   timeout=1800,check=True)
                base.check(pins)
                result.update(status='PASS',evidence=audit(directory,name))
            except Exception as error:
                result.update(status='FAIL',reason=f'{type(error).__name__}: {error}')
            base.save(directory / 'audit.json',result)
            return name,result

        with ThreadPoolExecutor(max_workers=5) as pool:
            from concurrent.futures import as_completed
            for future in as_completed([pool.submit(run,name) for name in NAMES]):
                name,result = future.result()
                state['cases'][name]=result
                save()
        base.check(pins)
        state.update(status='PASS' if all(r['status']=='PASS' for r in state['cases'].values())
                     else 'FAIL',phase='regression complete',
                     scope='five focused tests only; not a full coverage recollection')
        save()
        return 0 if state['status']=='PASS' else 1
    except Exception as error:
        state.update(status='STOPPED',reason=f'{type(error).__name__}: {error}');save()
        raise


if __name__ == '__main__':
    raise SystemExit(main())
