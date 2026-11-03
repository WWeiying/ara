#!/usr/bin/env python3
"""Snapshot and run two independent local DC comparisons in the EDA container."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

def save(path, obj):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj, indent=2) + '\n')
    temp.replace(path)

def worker(out, shared):
    manifest = json.loads((out/'manifest.json').read_text())
    timeout_seconds = int(manifest.get('timeout_seconds', 3600))
    if not 1 <= timeout_seconds <= 14400:
        raise ValueError('Invalid DC execution bound')
    status = {'state':'RUNNING','pid':os.getpid(),'started':datetime.now(timezone.utc).isoformat()}
    save(out/'status.json',status)
    for name, sha in manifest['hashes'].items():
        if hashlib.sha256((out/name).read_bytes()).hexdigest() != sha:
            save(out/'status.json',dict(status,state='FAIL',reason='snapshot hash mismatch'))
            return 1
    command=['docker','exec','-u',f'{os.getuid()}:{os.getgid()}',
             '-e',f'HOME={Path.home()}','-e',f'SHARED_MUL={shared}',
             '-w',str(out),'synopsys_workspace','bash','-lc',
             f'exec timeout --signal=TERM --kill-after=30s {timeout_seconds} dc_shell -f shared_mul_ppa.tcl']
    try:
        with (out/'dc.log').open('w') as log:
            r=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        text=(out/'dc.log').read_text(errors='replace')
        errors=[l for l in text.splitlines() if l.startswith(('Error:','Fatal:'))]
        passed=r.returncode==0 and not errors and 'SHARED_MUL_PPA_COMPLETE' in text
        if passed:
            metrics = dict(line.split('\t') for line in (out/'metrics.tsv').read_text().splitlines())
            for key in ('area_um2', 'clk_i_slack_ns', 'clk_i_arrival_ns'):
                if not math.isfinite(float(metrics[key])):
                    raise ValueError(f'Invalid metric: {key}')
            if float(metrics['area_um2']) <= 0:
                raise ValueError('Nonpositive cell area')
        status.update(state='PASS' if passed else 'FAIL',exit_code=r.returncode,errors=errors)
    except Exception as exc:
        status.update(state='FAIL',error=str(exc))
    status['finished']=datetime.now(timezone.utc).isoformat()
    save(out/'status.json',status)
    return 0 if status['state']=='PASS' else 1

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    p.add_argument('--worker',type=int,choices=(0,1))
    p.add_argument('--timeout-seconds',type=int,default=3600)
    a=p.parse_args(); out=a.output.resolve()
    if a.worker is not None:
        return worker(out,a.worker)
    if not 1 <= a.timeout_seconds <= 14400:
        p.error('timeout-seconds must be between 1 and 14400')
    out.mkdir(parents=True,exist_ok=False)
    subprocess.run([sys.executable,str(HERE/'extract_shared_mul_bank.py'),
                    str(ROOT/'hardware/src/lane/vmfpu.sv'),str(out/'extracted')],check=True)
    packages=['hardware/deps/common_cells/src/cf_math_pkg.sv','hardware/deps/axi/src/axi_pkg.sv',
      'hardware/deps/fpnew/src/fpnew_pkg.sv','hardware/deps/cva6/core/include/config_pkg.sv',
      'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
      'hardware/deps/cva6/core/include/riscv_pkg.sv','hardware/include/rvv_pkg.sv','hardware/include/ara_pkg.sv']
    modules=['simd_mul.sv','simd_mul_partition_add.sv','simd_mul_shared_product.sv','simd_mul_shared.sv']
    for shared,name in enumerate(('baseline','shared')):
        d=out/name; (d/'src/common_cells').mkdir(parents=True)
        for rel in packages:
            shutil.copy2(ROOT/rel,d/'src'/Path(rel).name)
        for name2 in modules:
            shutil.copy2(ROOT/'hardware/src/lane'/name2,d/'src'/name2)
        shutil.copy2(out/'extracted/bank.sv',d/'src/bank.sv')
        shutil.copy2(ROOT/'hardware/deps/common_cells/include/common_cells/registers.svh',d/'src/common_cells/registers.svh')
        shutil.copy2(HERE/'shared_mul_ppa.sv',d/'src/shared_mul_ppa.sv')
        shutil.copy2(HERE/'shared_mul_ppa.tcl',d/'shared_mul_ppa.tcl')
        shutil.copy2(ROOT/'backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env',d/'library_env.tcl')
        shutil.copy2(Path(__file__),d/'worker.py')
        hashes={str(f.relative_to(d)):hashlib.sha256(f.read_bytes()).hexdigest() for f in d.rglob('*') if f.is_file()}
        save(d/'manifest.json',{'shared':shared,'scope':'local_integer_bank_not_soc',
             'commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
             'period_ns':1,'setup_uncertainty_ns':0.15,'hashes':hashes,
             'timeout_seconds':a.timeout_seconds})
        unit='shared-mul-ppa-'+name+'-'+datetime.now().strftime('%Y%m%d%H%M%S')
        save(d/'status.json',{'state':'QUEUED','unit':unit})
        subprocess.run(['systemd-run','--user','--unit='+unit,
           '--property=StandardOutput=append:'+str(d/'worker.log'),
           '--property=StandardError=append:'+str(d/'worker.log'),
           sys.executable,str(d/'worker.py'),str(d),'--worker',str(shared)],check=True)
        print(name,d,unit,flush=True)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
