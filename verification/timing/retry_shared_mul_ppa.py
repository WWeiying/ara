#!/usr/bin/env python3
"""Retry a timed-out shared DC from frozen inputs; retain the passing baseline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone
from collect_shared_mul_ppa import collect


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--timeout', type=int, default=10800)
    a = p.parse_args()
    if not 3600 < a.timeout <= 14400:
        p.error('Retry bound must be greater than 3600 and at most 14400 seconds')
    src, out = a.source.resolve(), a.output.resolve()
    manifests = {}
    for name in ('baseline', 'shared'):
        m = json.loads((src/name/'manifest.json').read_text())
        for rel, sha in m['hashes'].items():
            if hashlib.sha256((src/name/rel).read_bytes()).hexdigest() != sha:
                raise RuntimeError('Changed source input: '+name+'/'+rel)
        manifests[name] = m
    for key in ('hashes', 'period_ns', 'setup_uncertainty_ns'):
        if manifests['baseline'][key] != manifests['shared'][key]:
            raise RuntimeError('Baseline/shared mismatch: '+key)
    if json.loads((src/'baseline/status.json').read_text())['state'] != 'PASS':
        raise RuntimeError('Baseline must be complete')
    old_status = json.loads((src/'shared/status.json').read_text())
    if old_status.get('exit_code') != 124 or old_status.get('errors'):
        raise RuntimeError('Expected clean timeout, not another failure')
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(src/'baseline', out/'baseline')
    d = out/'shared'
    d.mkdir()
    for rel in [*manifests['shared']['hashes'], 'manifest.json']:
        dst = d/rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src/'shared'/rel, dst)
    (out/'retry.json').write_text(json.dumps(dict(source=str(src),
        reused_baseline=True, timeout_seconds=a.timeout, rtl_and_constraints_unchanged=True), indent=2)+'\n')
    status = dict(state='RUNNING', started=datetime.now(timezone.utc).isoformat(), pid=os.getpid())
    def save():
        tmp = d/'status.tmp'
        tmp.write_text(json.dumps(status,indent=2)+'\n')
        tmp.replace(d/'status.json')
    save()
    try:
        command = ['docker','exec','-u',f'{os.getuid()}:{os.getgid()}',
            '-e',f'HOME={Path.home()}','-e','SHARED_MUL=1','-w',str(d),
            'synopsys_workspace','bash','-lc',
            f'exec timeout --signal=TERM --kill-after=30s {a.timeout} dc_shell -f shared_mul_ppa.tcl']
        with (d/'dc.log').open('w') as log:
            rc = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
        text = (d/'dc.log').read_text(errors='replace')
        errors = [line for line in text.splitlines() if line.startswith(('Error:','Fatal:'))]
        status.update(exit_code=rc,errors=errors)
        if rc or errors or 'SHARED_MUL_PPA_COMPLETE' not in text:
            raise RuntimeError('DC incomplete; inspect dc.log')
        status['state'] = 'PASS'
        save()
        result = collect(out)
        (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
        lines = ['variant,area_um2,clk_i_slack_ns,clk_i_arrival_ns']
        for name, row in result['results'].items():
            lines.append(f'{name},{row["area_um2"]},{row["clk_i_slack_ns"]},{row["clk_i_arrival_ns"]}')
        (out/'comparison.csv').write_text('\n'.join(lines)+'\n')
        print(json.dumps(result,indent=2),flush=True)
    except Exception as exc:
        status.update(state='FAIL',reason=str(exc))
        raise
    finally:
        status['finished'] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == '__main__':
    main()
