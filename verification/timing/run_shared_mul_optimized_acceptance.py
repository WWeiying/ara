#!/usr/bin/env python3
"""Run three bounded VCS checks, then optionally dispatch matched local DC.

Own this worker directly with systemd-run. Source drift prevents acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--dc-output', type=Path)
    p.add_argument('--dc-timeout', type=int, default=10800)
    a = p.parse_args()
    root, out = a.root.resolve(), a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = out/'status.json'
    def status(value, **extra):
        temp = state.with_suffix('.tmp')
        temp.write_text(json.dumps(dict(state=value, **extra), indent=2)+'\n')
        temp.replace(state)
    files = list((root/'hardware/src/lane').glob('*.sv'))
    files += list((root/'hardware/include').glob('*.sv'))
    files += [f for f in (root/'verification/timing').iterdir() if f.is_file()]
    files += [root/r for r in (
        'hardware/deps/common_cells/src/cf_math_pkg.sv',
        'hardware/deps/common_cells/include/common_cells/registers.svh',
        'hardware/deps/axi/src/axi_pkg.sv', 'hardware/deps/fpnew/src/fpnew_pkg.sv',
        'hardware/deps/cva6/core/include/config_pkg.sv',
        'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
        'hardware/deps/cva6/core/include/riscv_pkg.sv',
        'backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env')]
    hashes = {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    (out/'manifest.json').write_text(json.dumps(hashes, indent=2)+'\n')
    for f in files:
        dest = out/'source_snapshot'/f.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f,dest)
    def check_pins():
        for rel, sha in hashes.items():
            if hashlib.sha256((root/rel).read_bytes()).hexdigest() != sha:
                raise RuntimeError('Source drift: '+rel)
    processes, logs = [], []
    try:
        status('PREPARING')
        subprocess.run([sys.executable,str(root/'verification/timing/test_booth_arithmetic.py')],check=True)
        subprocess.run([sys.executable,str(root/'verification/timing/extract_shared_mul_bank.py'),
                        str(root/'hardware/src/lane/vmfpu.sv'),str(out/'extracted')],check=True)
        common = ['make','-C',str(root/'verification/timing'),f'BUILD={out}',
                  'RUN_TIMEOUT=1200','REFERENCE=f636824e9b5a347666401bba40a6a17925b9a402']
        jobs = [('product', 'shared-mul-signed-product-check', [], 'Shared signed product PASS checks=425280'),
                ('mul','mul-check',['MUL_DEFINES=+define+TEST_FULL_SHARED_SIMD_MUL'],
                 'SIMD MUL equivalence PASS configurations=24'),
                ('bank','shared-mul-bank-check', ['MUL_DEFINES=+define+ARA_SHARED_SIMD_MUL',
                 'MUL_BANK_TOP=shared_mul_stream_tb',f'MUL_EXTRA_SOURCES={out}/extracted/bank.sv'],
                 'Shared MUL stream PASS')]
        for name,target,args,marker in jobs:
            log = (out/(name+'_console.log')).open('w')
            logs.append(log)
            processes.append(subprocess.Popen(common+[target]+args,stdout=log,stderr=subprocess.STDOUT))
        status('VCS_RUNNING',pids=[x.pid for x in processes])
        results = {}
        for proc, (name,_,_,marker) in zip(processes,jobs):
            rc = proc.wait()
            logpath = out/name/'run.log'
            text = logpath.read_text(errors='replace') if logpath.exists() else ''
            results[name] = rc == 0 and marker in text and not any(x in text for x in ('Fatal:','Error:'))
        check_pins()
        if not all(results.values()):
            status('FAIL',results=results)
            return 1
        status('VCS_PASS',results=results)
        if a.dc_output:
            subprocess.run([sys.executable,str(root/'verification/timing/run_shared_mul_ppa.py'),
                            str(a.dc_output.resolve()),'--timeout-seconds',str(a.dc_timeout)],check=True)
            collector = a.dc_output.resolve()/'collect_frozen.py'
            shutil.copy2(root/'verification/timing/collect_shared_mul_ppa.py',collector)
            subprocess.run(['systemd-run','--user','--unit=shared-mul-collect-'+out.name,
                            '--property=StandardOutput=append:'+str(a.dc_output.resolve()/'collector.log'),
                            '--property=StandardError=append:'+str(a.dc_output.resolve()/'collector.log'),
                            sys.executable,str(collector),str(a.dc_output.resolve()),'--wait'],check=True)
            status('VCS_PASS_DC_DISPATCHED',results=results)
        return 0
    except Exception as exc:
        status('ERROR',reason=str(exc))
        raise
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()
        for log in logs:
            log.close()


if __name__ == '__main__':
    raise SystemExit(main())
