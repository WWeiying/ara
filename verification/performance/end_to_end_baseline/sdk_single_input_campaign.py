#!/usr/bin/env python3
"""Own one same-ELF VCS SDK comparison and its independent replay audit."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from audit import digest,require,verify_pins


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True);parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--audit',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    here=Path(__file__).resolve().parent
    files=(Path(__file__).resolve(),here/'audit.py',here/'run_sdk_single_input_native.py',
           here/'check_sdk_single_input.py',here/'collect_sdk_single_input.py',args.build.resolve()/'build.json')
    pins={str(p):digest(p) for p in files}
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='PREPARING',performance_measured=False,production_sdk_changed=False)
    try:
        commands=[('simulate',[sys.executable,'-B',here/'run_sdk_single_input_native.py','--build',args.build,
            '--output',args.run,'--execute-reviewed']),('audit',[sys.executable,'-B',here/'collect_sdk_single_input.py',
            '--run',args.run,'--output',args.audit])]
        for stage,cmd in commands:
            verify_pins(pins);result['state']=stage.upper();(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            with (out/(stage+'.log')).open('w') as log:
                child=subprocess.run(list(map(str,cmd)),stdout=log,stderr=subprocess.STDOUT,
                                     timeout=12000 if stage=='simulate' else 900)
            require(child.returncode==0,stage+' worker failed');verify_pins(pins)
        audited=json.loads((args.audit/'result.json').read_text())
        require(audited['state']=='REAL_QWEN3_SDK_SINGLE_INPUT_ABBA_REAUDITED','No accepted audit')
        result.update(state='PASS',performance_measured=True,run=str(args.run),audit=str(args.audit),
            audit_result_sha256=digest(args.audit/'result.json'),source_pins_sha256=digest(out/'source-pins.json'))
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
