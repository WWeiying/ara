#!/usr/bin/env python3
"""Independently re-audit real Decode SDK timing and retained reader/context activity."""
import argparse
import json
from pathlib import Path

from audit import digest,require,verify_pins
from check_decode_native import check
from run_decode_native import oracle


def collect(root):
    from collect_matrix_soc import audit_build
    from run_output_native import s,accepted
    root=root.resolve(strict=True);report=json.loads((root/'result.json').read_text())
    require(report['state']=='PASS' and report['wide']==0 and report['performance_measured'] and
            report['independent_protocol_checked'] and report['post_pins_match'],'Unaccepted Decode run')
    require(digest(root/'source-pins.json')==report['source_pins_sha256'],'Pin-map drift')
    pins=json.loads((root/'source-pins.json').read_text());checked=verify_pins(pins)
    build=Path(report['build']);program=json.loads((build/'build.json').read_text())
    require(program['state']=='REAL_QWEN3_DECODE_SDK_BUILT_NOT_EXECUTED' and
            pins.get(str(build/'build.json'))==digest(build/'build.json') and
            report['elf_sha256']==program['elf_sha256']==digest(program['elf']),'Build binding')
    simv=Path(json.loads((root/'status.json').read_text())['simv']);soc=audit_build(simv.parent.parent)
    require(soc['wide']==0 and soc['image_pins']==report['image_pins'] and
            s.hashes(s.image_files(simv))==report['image_pins'],'Image binding')
    text=(root/'work/run.vcs.log').read_text();measured=check(text,*oracle(build))
    require(measured==report['measured'],'Raw run replay differs')
    accepted.protocol(root/'work',report['elf_sha256'],report['image_pins'])
    verify_pins(pins)
    return dict(run=str(root),build=str(build),elf_sha256=report['elf_sha256'],checked_inputs=checked,
                measured=measured,result_sha256=digest(root/'result.json'),
                source_pins_sha256=report['source_pins_sha256'],log_sha256=digest(root/'work/run.vcs.log'),
                protocol_sha256=digest(root/'work/uvm_result.json'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result=dict(state='CHECKING',whole_model=False,full_n=False,full_k=True,area_measured=False)
    try:
        pins={str(path):digest(path) for path in (Path(__file__),Path(__file__).with_name('check_decode_native.py'),
                Path(__file__).with_name('run_decode_native.py'),Path(__file__).with_name('audit.py'))}
        accepted=collect(args.run);m=accepted['measured'];verify_pins(pins)
        result.update(state='REAL_QWEN3_DECODE_SDK_BASELINE_REAUDITED',report=accepted,collector_pins=pins,
            local_preparation_fraction=m['total']['preparation']/m['total']['region'],
            local_sdk_outside_busy_cycles=m['total']['execution']-m['qbs_busy_cycles'],
            limitations=['M1/N128 prefixes with true post-prefill Decode activations and original full K',
                'Projection inputs captured at separate graph boundaries; not one contiguous model interval',
                'Existing activation-context reuse retained; no all-DIRECT weak baseline',
                'activation_bytes is compute intake, not AXI traffic; reader payload separately reconciled',
                'Strict WAIT buckets observe shared-reader service, not weight-only DDR latency',
                'One reset trial; cold weight repack, full GGML dispatch and full-model timing excluded'])
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
