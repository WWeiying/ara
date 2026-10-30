#!/usr/bin/env python3
"""Independent terminal replay of finite V decode numerical/timing evidence."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
from run_value_decode_fast import checked_build,s
from check_value_decode_fast import check_log


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); run=args.run.resolve(strict=True); out=args.output.resolve()
    s.require(not out.is_relative_to(run),'Independent output required')
    out.mkdir(parents=True,exist_ok=False)
    try:
        status,result=s.read_json(run/'status.json'),s.read_json(run/'result.json')
        s.require(status.get('state')==result.get('state')=='PASS' and
            status.get('child_pid') is None and result.get('simulator_exit_code')==0 and
            result.get('post_pins_match') is True and result.get('independent_protocol_checked') is True,
            'Require checked terminal V-decode PASS')
        original=s.hashes([run/'status.json',run/'result.json'])
        report,image,required=checked_build(Path(status['build']))
        s.require(status['elf']==report['elf'] and status['simv']==report['simv'] and
            result['elf_sha256']==report['elf_sha256'] and
            s.digest(run/'source-pins.json')==result['source_pins_sha256'],'Execution identity drift')
        pins=s.read_json(run/'source-pins.json')
        s.require(all(pins.get(p)==h for p,h in required.items()),'Worker omitted inputs')
        s.merge_pins(pins,result['evidence_sha256']); s.merge_pins(pins,original); s.verify_pins(pins)
        log,trace=run/'work/run.vcs.log',run/'work/vector_trace.csv'
        parsed=check_log(log.read_text(),[Path(p).read_bytes() for p in report['value_paths']])
        s.require(all(result.get(k)==v for k,v in parsed.items() if k!='state'),'Raw decoder replay differs')
        s.check_result(run/'work/uvm_result.json',report['elf_sha256'],image)
        uvm=s.read_json(run/'work/uvm_result.json')
        s.require(uvm['log_sha256']==s.digest(log) and uvm['vector_trace_sha256']==s.digest(trace),
                  'Protocol inputs mismatch')
        s.merge_pins(pins,s.hashes([Path(__file__)])); s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json',pins)
        accepted=dict(result)
        accepted.update(state='INDEPENDENT_VALUE_DECODE_ACCEPTED',run=str(run),
            source_pins_sha256=s.digest(out/'source-pins.json'),original_report_sha256=original,
            current_inputs_match=True,whole_attention_accepted=False,deployment_approved=False)
        s.atomic_json(out/'result.json',accepted)
        print('INDEPENDENT_VALUE_DECODE_ACCEPTED trials=8 outputs=262144 boundaries=3584')
    except BaseException as exc:
        s.atomic_json(out/'result.json',dict(state='FAIL',error=repr(exc))); raise


if __name__=='__main__': main()
