#!/usr/bin/env python3
"""One-shot campaign progress; no launches and no polling loop."""
import json
from pathlib import Path

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')


def main():
    patterns = ('power_rtl_20261117_*', 'power_precheck_20261117_*', 'power_gate_build_20261117_*')
    for pattern in patterns:
        for directory in sorted(OUT.glob(pattern)):
            state = directory/'status.json'
            if not state.exists():
                continue
            data = json.loads(state.read_text())
            disposition = directory/'disposition.json'
            if disposition.exists():
                data['state'] = json.loads(disposition.read_text())['state']
            build = directory/'build.json'
            attempt = directory/'attempt.json'
            if build.exists() and not (directory/'runs').is_dir():
                data['state'] = json.loads(build.read_text())['state']
            elif attempt.exists() and not (directory/'runs').is_dir():
                owner = json.loads(attempt.read_text()).get('pid')
                if owner and Path('/proc',str(owner)).exists():
                    data['state'] = 'COMPILING'
            print(directory.name, data['state'],
                  f"{data.get('completed','-')}/{data.get('total','-')}")
            for child in sorted((directory/'runs').glob('*/status.json')):
                result = json.loads(child.read_text())
                pid = result.get('pid')
                live = bool(pid and Path('/proc',str(pid)).exists())
                print(' ',child.parent.name,result['state'],f'pid={pid} live={live}' if pid else '')
    for directory in sorted(OUT.glob('power_protocol_audit_20261117_*')):
        result = directory/'result.json'
        if result.exists():
            data = json.loads(result.read_text())
            print(directory.name, data['state'], '(independent audit; original worker unchanged)')
    for pattern in ('power_gls_20261117_*', 'power_saif_20261117_*', 'power_dc_20261117_*'):
        for directory in sorted(OUT.glob(pattern)):
            report = directory/'result.json'
            if not report.exists():
                report = directory/'status.json'
            if not report.exists():
                continue
            data = json.loads(report.read_text())
            pid = data.get('child_pid') or data.get('owner_pid')
            live = bool(pid and Path('/proc', str(pid)).exists())
            details = f'pid={pid} live={live}' if pid else ''
            print(directory.name, data.get('state', 'UNKNOWN'), details)
            if 'power_watts' in data:
                print(' ', json.dumps(data['power_watts'], sort_keys=True))
    print('RTL precheck PASS is not gate-level power completion.')


if __name__ == '__main__':
    main()
