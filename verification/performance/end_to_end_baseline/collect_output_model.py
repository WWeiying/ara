#!/usr/bin/env python3
"""Post-run audit of the complete Qwen3 pair, including native emulator identity."""
import argparse
import json
import os
from pathlib import Path
import sys

from audit import digest,require,verify_pins
from check_output_model import check

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_ggml_segmented import verify_native_build


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run=a.run.resolve(strict=True);out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    state=dict(state='CHECKING',pid=os.getpid(),performance_measured=False)
    def save(): (out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    save()
    try:
        report=json.loads((run/'result.json').read_text())
        require(report['state']=='MODEL_EXECUTED_PENDING_INDEPENDENT_AUDIT','Incomplete model execution')
        for filename,key in (('test','elf_sha256'),('qemu.log','log_sha256'),('source-pins.json','source_pins_sha256')):
            require(digest(run/filename)==report[key],'Worker artifact drift: '+filename)
        pins=json.loads((run/'source-pins.json').read_text())
        checked=check((run/'qemu.log').read_text())
        command=[r for r in json.loads((run/'commands.json').read_text()) if r['label']=='qemu']
        require(len(command)==1,'Missing/duplicate QEMU execution')
        argv=command[0]['argv'];qemu=Path(argv[0]).resolve(strict=True)
        require('xaraqbs=true' in argv[argv.index('-cpu')+1] and
                argv[argv.index('-initrd')+1]==str(run/'initramfs.cpio'),'Wrong CPU or model payload')
        inputs=verify_pins(pins)
        state.update(state='NATIVE_EMULATOR_POSTCHECK',checked=checked);save()
        paths=verify_native_build(qemu)
        for path in paths:
            path=Path(path).resolve(strict=True)
            require(pins.get(str(path))==digest(path),'Native emulator inventory differs: '+str(path))
        verify_pins(pins)
        state.update(state='PAIRED_QWEN3_OUTPUT_MODEL_REAUDITED',checked_inputs=inputs,
                     native_emulator_postchecked=True,checked=checked,
                     worker_result_sha256=digest(run/'result.json'),
                     elf_sha256=report['elf_sha256'],log_sha256=report['log_sha256'],
                     source_pins_sha256=report['source_pins_sha256'],run=str(run),
                     audit_pins={str(path):digest(path) for path in (Path(__file__),HERE/'audit.py',
                         HERE/'check_output_model.py',ROOT/'verification/qbs/run_ggml_segmented.py',
                         run/'result.json',run/'commands.json')},
                     limitations=['QEMU validates functionality/dispatch, not hardware cycles',
                                  'Original hardware: this model run does not enable the optional wide dot prototype',
                                  'Paired final CSR state, not universal whole-model CSR preservation'])
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:save();(out/'result.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__':main()
