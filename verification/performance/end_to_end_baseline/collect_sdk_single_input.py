#!/usr/bin/env python3
"""Re-audit actual same-ELF SDK ABBA results; retain negative performance outcomes."""
import argparse
import json
from pathlib import Path

from audit import digest,require,verify_pins
from check_sdk_single_input import check,verify_oracle_inputs
from run_decode_native import oracle


def collect(root):
    from collect_matrix_soc import audit_build
    from run_output_native import s,accepted
    root=root.resolve(strict=True);report=json.loads((root/'result.json').read_text())
    require(report['state']=='PASS' and report['wide']==0 and report['performance_measured'] and
            report['independent_protocol_checked'] and report['post_pins_match'],'Unaccepted ABBA run')
    require(digest(root/'source-pins.json')==report['source_pins_sha256'],'Pin inventory drift')
    pins=json.loads((root/'source-pins.json').read_text());checked=verify_pins(pins)
    build=Path(report['build']);program=json.loads((build/'build.json').read_text())
    require(program['state']=='REAL_QWEN3_SDK_SINGLE_INPUT_ABBA_BUILT_NOT_EXECUTED' and
            pins.get(str(build/'build.json'))==digest(build/'build.json') and
            report['elf_sha256']==program['elf_sha256']==digest(program['elf']),'Program binding')
    require(pins.get(program['host_result'])==program['host_result_sha256']==digest(program['host_result']),
            'Host differential binding')
    verify_oracle_inputs(program,pins)
    simv=Path(json.loads((root/'status.json').read_text())['simv']);soc=audit_build(simv.parent.parent)
    require(soc['wide']==0 and soc['image_pins']==report['image_pins'] and
            s.hashes(s.image_files(simv))==report['image_pins'],'Actual SoC binding')
    measured=check((root/'work/run.vcs.log').read_text(),*oracle(Path(program['oracle_build'])))
    require(measured==report['measured'],'Raw ABBA replay differs')
    accepted.protocol(root/'work',report['elf_sha256'],report['image_pins']);verify_pins(pins)
    return dict(run=str(root),build=str(build),checked_inputs=checked,measured=measured,
        result_sha256=digest(root/'result.json'),source_pins_sha256=report['source_pins_sha256'],
        log_sha256=digest(root/'work/run.vcs.log'),protocol_sha256=digest(root/'work/uvm_result.json'),
        elf_sha256=report['elf_sha256'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result=dict(state='CHECKING',whole_model=False,rtl_changed=False,production_sdk_changed=False)
    try:
        pins={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('audit.py'),
              Path(__file__).with_name('check_sdk_single_input.py'))}
        report=collect(args.run);verify_pins(pins)
        result.update(state='REAL_QWEN3_SDK_SINGLE_INPUT_ABBA_REAUDITED',report=report,collector_pins=pins,
            limitations=['One reset-start ABBA sequence; first/cold and warmed baseline timings both retained',
                         'M1, actual full K, seven N128 prefixes; not full GGML or full-model timing',
                         'SDK loop only; same hardware, production quantizer, native/fence and context semantics',
                         'Performance ratios do not decide PASS; no production promotion until benefit is reviewed'])
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
