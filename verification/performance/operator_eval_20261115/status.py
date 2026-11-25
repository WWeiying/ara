#!/usr/bin/env python3
"""One-shot current campaign status, without launching or polling simulations."""
import argparse
import json
from pathlib import Path
import subprocess

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--detail',action='store_true')
    args=parser.parse_args()
    for path in sorted(OUT.glob('operator_soc_20261115_*')) + sorted(OUT.glob('operator_campaign_20261115_*')) + sorted(OUT.glob('operator_campaign_20261116_*')):
        status = path / 'status.json'
        record = json.loads(status.read_text()) if status.is_file() else {}
        for f in (path / 'runs').glob('*/status.json'):
            child = json.loads(f.read_text()).get('child_pid')
            if child and Path('/proc/'+str(child)).exists():
                record['state']='RUNNING'
                break
        print(path.name, record.get('state','NOT_STARTED'),
              str(record.get('completed',0))+'/'+str(record.get('total','?')))
        for work in sorted((path / 'runs').glob('*')) if (path / 'runs').exists() else []:
            if not work.is_dir():
                continue
            f = work / 'status.json'
            state = json.loads(f.read_text()) if f.exists() else {}
            pid = state.get('child_pid')
            actual = ''
            if pid:
                columns='pid=,etime=,pcpu=,args=' if args.detail else 'pid=,etime=,pcpu=,comm='
                actual = subprocess.run(['ps','-p',str(pid),'-o',columns],
                    text=True, stdout=subprocess.PIPE).stdout.strip() or 'PROCESS_NOT_PRESENT'
            print(' ',work.name, state.get('state','NOT_STARTED'), actual)
    print('Separate audits (original worker statuses above are not rewritten):')
    for path in sorted(OUT.glob('operator_audit_20261115_*'))+sorted(OUT.glob('operator_attention_activity_audit_20261115_*')):
        f=path/'result.json'
        r=json.loads(f.read_text()) if f.exists() else {}
        print(' ',path.name,r.get('state','NOT_COMPLETE'),r.get('original_case',''))
    print('Successor queues:')
    for path in sorted(OUT.glob('operator_chain_20261115_*'))+sorted(OUT.glob('operator_chain_20261116_*'))+sorted(OUT.glob('operator_control_worker_20261115_*'))+sorted(OUT.glob('operator_control_worker_20261116_*'))+sorted(OUT.glob('operator_slot_probe_20261116_*')):
        f=path/'status.json'; r=json.loads(f.read_text()) if f.exists() else {}
        f=path/'attempt.json'; attempt=json.loads(f.read_text()) if f.exists() else {}
        pid=attempt.get('owner_pid')
        owner=subprocess.run(['ps','-p',str(pid),'-o','pid=,etime=,comm='],
            text=True,stdout=subprocess.PIPE).stdout.strip() if pid else ''
        print(' ',path.name,r.get('state','NOT_STARTED'),owner or 'NO_LIVE_CONTROLLER')


if __name__ == '__main__':
    main()
