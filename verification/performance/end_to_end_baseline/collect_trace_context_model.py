#!/usr/bin/env python3
"""Re-audit cross-library Qwen3 comparisons, actual link inputs and boot identity."""
import argparse
import json
from pathlib import Path

from audit import digest,require,verify_pins
from trace_context_model import check,fixture
from run_projection_capture_v3 import HERE,ROOT,VERIFY,MODEL_RUN


def normalized_link(argv,root,archive):
    argv=list(argv)
    require(argv.count(str(root/'model.o'))==1 and argv.count(str(archive))==1 and argv.count('-o')==1,
            'Ambiguous model link')
    return ['MODEL_OBJECT' if v==str(root/'model.o') else 'GGML_CPU_ARCHIVE' if v==str(archive)
            else 'OUTPUT_ELF' if i==argv.index('-o')+1 else v for i,v in enumerate(argv)]


def collect(root):
    root=root.resolve(strict=True);report=json.loads((root/'result.json').read_text())
    require(report['state']=='TRACE_CONTEXT_MODEL_PAIR_FUNCTIONAL_PASS' and report['post_pins_match'] and
            not report['performance_measured'] and not report['model_library_promoted'],'Unaccepted model worker')
    require(digest(root/'source-pins.json')==report['source_pins_sha256'],'Source inventory drift')
    pins=json.loads((root/'source-pins.json').read_text());checked=verify_pins(pins);verify_pins(report['artifacts'])
    for path,target in json.loads((root/'path-identities.json').read_text()).items():
        require(str(Path(path).resolve(strict=True))==target,'Symlink identity drift')
    library=Path(report['library_build']);lr=json.loads((library/'result.json').read_text())
    require(pins.get(str(library/'result.json'))==digest(library/'result.json') and
            lr['candidate_library_sha256']==report['candidate_library_sha256'],'Candidate library binding')
    for filename,key in (('model.o','common_model_object_sha256'),('base','baseline_elf_sha256'),
                         ('candidate','candidate_elf_sha256'),('test','driver_elf_sha256')):
        require(pins.get(str(root/filename))==report[key]==digest(root/filename),'Linked object/ELF binding')
    require((root/'model.cpp').read_text()==fixture((MODEL_RUN/'model.cpp').read_text()),'Model source transformation drift')
    commands=json.loads((root/'commands.json').read_text())
    def command(label):
        rows=[r['argv'] for r in commands if r['label']==label];require(len(rows)==1,'Duplicate/missing command');return rows[0]
    base=command('link-base');candidate=command('link-candidate')
    require(normalized_link(base,root,Path(lr['original_library']))==
            normalized_link(candidate,root,Path(lr['candidate_library'])),'More than one library/output changed')
    require(base[base.index('-o')+1]==str(root/'base') and candidate[candidate.index('-o')+1]==str(root/'candidate'),
            'Link output identity')
    cc=command('compile-model');require(cc[cc.index('-c')+1]==str(root/'model.cpp') and
            cc[cc.index('-o')+1]==str(root/'model.o'),'Shared model compile binding')
    qemu=command('qemu');require('xaraqbs=true' in qemu[qemu.index('-cpu')+1] and
            qemu[qemu.index('-initrd')+1]==str(root/'initramfs.cpio'),'Actual guest CPU/payload')
    listing=(root/'initramfs.list').read_text()
    for guest,filename in (('base','base'),('candidate','candidate'),('test','test')):
        require(listing.splitlines().count(f'file /{guest} {root/filename} 755 0 0')==1,'Guest ELF mapping')
    sys_path=ROOT/'verification/qbs'
    import sys
    sys.path.insert(0,str(sys_path));from run_ggml_segmented import verify_native_build
    for path in verify_native_build(Path(qemu[0])):
        require(pins.get(str(Path(path).resolve()))==digest(path),'Native emulator identity drift')
    require(digest(root/'qemu.log')==report['log_sha256'],'Guest log drift')
    require(pins.get(str(root/'projection-schema.json'))==digest(root/'projection-schema.json'),'Projection schema identity')
    measured=check((root/'qemu.log').read_text(),(MODEL_RUN/'qemu.log').read_text(),
                   json.loads((root/'projection-schema.json').read_text()))
    require(measured==report['measured'],'Raw model replay differs');verify_pins(pins)
    return dict(run=str(root),checked_inputs=checked,measured=measured,
        source_pins_sha256=report['source_pins_sha256'],worker_result_sha256=digest(root/'result.json'),
        log_sha256=report['log_sha256'],common_model_object_sha256=report['common_model_object_sha256'],
        baseline_elf_sha256=report['baseline_elf_sha256'],candidate_elf_sha256=report['candidate_elf_sha256'],
        candidate_library_sha256=report['candidate_library_sha256'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();require(out.is_relative_to(VERIFY/'verification/out'),'Verification output')
    out.mkdir(parents=True,exist_ok=False);result=dict(state='CHECKING',performance_measured=False,rtl_changed=False)
    try:
        collector_pins={str(p):digest(p) for p in (Path(__file__),HERE/'audit.py',HERE/'trace_context_model.py')}
        report=collect(args.run);verify_pins(collector_pins)
        result.update(state='TRACE_CONTEXT_QWEN3_MODEL_PAIR_REAUDITED',report=report,collector_pins=collector_pins,
            limitations=['Native QEMU mathematical model is used for functional checks, never RTL timing',
                         '40-token prompt and one Decode step per KV choice; not broad model/format signoff',
                         'Trace aggregate enabled with per-command lifetime logging disabled',
                         'Trace flags must remain stable inside a blocking context'])
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
