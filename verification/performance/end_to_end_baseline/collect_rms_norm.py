#!/usr/bin/env python3
"""Independently replay real fused-call timings, source identity and RVV work."""
import argparse
import json
from pathlib import Path

from audit import digest,require,verify_pins
from check_rms_norm import check,check_activity
from rms_norm_completion import completed_caller


def collect(root):
    from collect_matrix_soc import audit_build
    from run_output_native import s,accepted
    root=root.resolve(strict=True);report=json.loads((root/'result.json').read_text())
    require(report['state']=='PASS' and report['wide']==0 and report['performance_measured'] and
            report['independent_protocol_checked'] and report['post_pins_match'],'Unaccepted RMSNorm worker')
    require(digest(root/'source-pins.json')==report['source_pins_sha256'],'Pin inventory drift')
    pins=json.loads((root/'source-pins.json').read_text());checked=verify_pins(pins)
    build=Path(report['build']);program=json.loads((build/'build.json').read_text())
    require(program['state']=='REAL_QWEN3_FUSED_RMS_NORM_ABBA_BUILT_NOT_EXECUTED' and
            program['timing_includes_csr_completion'] and
            pins.get(str(build/'build.json'))==digest(build/'build.json') and
            report['elf_sha256']==program['elf_sha256']==digest(program['elf']),'Program binding')
    parent=Path(program['parent_build'])
    require(pins.get(str(parent/'build.json'))==digest(parent/'build.json') and
            pins.get(program['completed_caller'])==digest(program['completed_caller']) and
            Path(program['completed_caller']).read_text()==completed_caller(
                Path(__file__).with_name('rms_norm_native.cpp').read_text()),'Completion timer source binding')
    data=Path(program['data']);require(pins.get(str(data/'data.json'))==digest(data/'data.json'),'Model input identity')
    d=json.loads((data/'data.json').read_text());verify_pins(d['artifacts'])
    for filename in ('input_f32.bin','norm_weight_f32.bin','expected_f32.bin','epsilon.bin',
                     'decode_input_f32.bin','decode_expected_f32.bin'):
        path=str(data/filename);require(pins.get(path)==d['artifacts'].get(path)==digest(path),'Tensor binding')
    simv=Path(json.loads((root/'status.json').read_text())['simv']);soc=audit_build(simv.parent.parent)
    require(soc['wide']==0 and soc['image_pins']==report['image_pins'] and
            s.hashes(s.image_files(simv))==report['image_pins'],'Actual image binding')
    measured=check((root/'work/run.vcs.log').read_text(),(data/'expected_f32.bin').read_bytes(),
                   (data/'decode_expected_f32.bin').read_bytes())
    activity=check_activity((root/'work/vector_trace.csv').read_text())
    require(measured==report['measured'] and activity==report['activity'],'Raw RMSNorm replay differs')
    accepted.protocol(root/'work',report['elf_sha256'],report['image_pins']);verify_pins(pins)
    return dict(run=str(root),checked_inputs=checked,measured=measured,activity=activity,
        worker_result_sha256=digest(root/'result.json'),source_pins_sha256=report['source_pins_sha256'],
        log_sha256=digest(root/'work/run.vcs.log'),vector_trace_sha256=digest(root/'work/vector_trace.csv'),
        protocol_sha256=digest(root/'work/uvm_result.json'),elf_sha256=report['elf_sha256'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result=dict(state='CHECKING',whole_model=False,rtl_changed=False,production_library_changed=False)
    try:
        pins={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('audit.py'),
                                       Path(__file__).with_name('check_rms_norm.py'))}
        report=collect(args.run);verify_pins(pins)
        result.update(state='REAL_QWEN3_FUSED_RMS_NORM_ABBA_REAUDITED',report=report,collector_pins=pins,
            limitations=['Full first-layer fused norm only; not whole-model phase attribution',
                         'Call interval includes vcsr/fcsr/vstart completion reads; no assumed probe cost is subtracted',
                         'Decode is actual token 22406 after 40-token Prefill; Prefill is four original prompt rows',
                         'Actual GGML fusion/output path retained; only the square sum changes in candidate',
                         'Boundary tests are differential checks, not real model workload or measured performance',
                         'No production integration, synthesis, area or physical acceptance'])
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
