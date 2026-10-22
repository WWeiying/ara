"""ExecStopPost only: preserve systemd's exit fields, never infer numeric wait."""
import json
import os
from pathlib import Path
import sys
import time

FIELDS=('EXIT_CODE','EXIT_STATUS','SERVICE_RESULT')

def payload(env,now):
    result={}
    for name in FIELDS:
        value=env.get(name)
        if not isinstance(value,str) or not value or '\n' in value or '\r' in value:
            raise ValueError('Missing/malformed systemd field '+name)
        result[name]=value
    if result['EXIT_CODE'] not in ('exited','killed','dumped'):
        raise ValueError('Unsupported systemd EXIT_CODE')
    if result['EXIT_CODE']=='exited' and not result['EXIT_STATUS'].isdigit():
        raise ValueError('Exited status must retain a numeric systemd string')
    if type(now) not in (int,float) or now<=0:
        raise ValueError('Invalid timestamp')
    return dict(result,recorded_unix_s=now)

def write(path,record):
    with Path(path).open('x') as stream:
        json.dump(record,stream,indent=2)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Expected exclusive output path')
    write(sys.argv[1],payload(os.environ,time.time()))
