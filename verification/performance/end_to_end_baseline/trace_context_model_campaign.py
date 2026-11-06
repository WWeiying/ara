#!/usr/bin/env python3
"""Own the Qwen3 library pair and its independent replay without status polling."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from audit import digest,require,verify_pins


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);here=Path(__file__).resolve().parent
    files=(Path(__file__).resolve(),here/'audit.py',here/'run_trace_context_model.py',here/'trace_context_model.py',
           here/'collect_trace_context_model.py',here/'trace_context_model_driver.cpp')
    pins={str(p):digest(p) for p in files};(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='PREPARING',performance_measured=False)
    try:
        commands=(('model',[sys.executable,'-B',here/'run_trace_context_model.py','--output',args.run,'--execute-reviewed']),
                  ('audit',[sys.executable,'-B',here/'collect_trace_context_model.py','--run',args.run,'--output',args.audit]))
        for stage,cmd in commands:
            verify_pins(pins);result['state']=stage.upper();(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            with (out/(stage+'.log')).open('xb') as stream:
                child=subprocess.run(list(map(str,cmd)),stdout=stream,stderr=subprocess.STDOUT,timeout=9000)
            require(child.returncode==0,stage+' failed');verify_pins(pins)
        audited=json.loads((args.audit/'result.json').read_text())
        require(audited['state']=='TRACE_CONTEXT_QWEN3_MODEL_PAIR_REAUDITED','Independent model audit missing')
        result.update(state='PASS',run=str(args.run),audit=str(args.audit),
                      audit_result_sha256=digest(args.audit/'result.json'),source_pins_sha256=digest(out/'source-pins.json'))
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
