#!/usr/bin/env python3
"""Pair original/trace-context model libraries on complete Qwen3 graph steps."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from audit import digest,require,verify_pins
from build_trace_context_library import archive_members,compare_archives
from run_projection_capture_v3 import HERE,ROOT,VERIFY,MODEL_RUN,GRAPH,MODEL,dependency_pin
from trace_context_model import fixture,check


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute-reviewed',action='store_true')
    args=parser.parse_args();out=args.output.absolute()
    require(out==out.resolve() and out.is_relative_to(VERIFY/'verification/out'),'Fresh verification output')
    out.mkdir(parents=True,exist_ok=False);pins={};identities={};commands=[]
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None,performance_measured=False,
               rtl_changed=False,model_library_promoted=False)
    def save():(out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    def pin(path,expected=None):
        lexical=Path(path).absolute();path=lexical.resolve(strict=True);sha=digest(path)
        require(expected is None or sha==expected,'Input identity: '+str(path))
        require(str(path) not in pins or pins[str(path)]==sha,'Input drift');pins[str(path)]=sha
        identities[str(lexical)]=str(path)
    def verify():
        verify_pins(pins)
        require(all(str(Path(path).resolve(strict=True))==target for path,target in identities.items()),'Symlink drift')
    def run(argv,label,bound=180):
        argv=list(map(str,argv));pin(argv[0]);verify()
        commands.append(dict(label=label,argv=argv,timeout=bound))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');state['state']=label.upper();save()
        with (out/(label+'.log')).open('xb') as log:
            child=subprocess.Popen(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT)
            state['child_pid']=child.pid;save()
            try:code=child.wait(timeout=bound)
            except BaseException:child.kill();child.wait();raise
            finally:state['child_pid']=None;save()
        require(code==0,label+' failed');verify()
    save()
    try:
        for module in tuple(sys.modules.values()):
            path=getattr(module,'__file__',None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(HERE):pin(path)
        for path in (HERE/'trace_context_model_driver.cpp',HERE/'check_output_model.py',Path(__file__)):pin(path)
        receipt=ROOT/'verification/performance/evidence/trace_context_library_20261106_01/result.json'
        pin(receipt);accepted=json.loads(receipt.read_text());library_run=Path(accepted['run'])
        pin(library_run/'result.json',accepted['result_sha256'])
        pin(library_run/'source-pins.json',accepted['source_pins_sha256'])
        library=json.loads((library_run/'result.json').read_text())
        require(library['state']=='TRACE_CONTEXT_LIBRARY_BUILT_ARCHIVE_VERIFIED' and library['compiled_translation_units']==1 and
                library['original_library_unchanged'] and library['inventory_and_order_unchanged'],'Library candidate gate')
        for path,sha in json.loads((library_run/'source-pins.json').read_text()).items():pin(path,sha)
        for name,sha in library['artifacts'].items():
            path=library_run/name;require(path.resolve().is_relative_to(library_run),'Artifact outside archive build');pin(path,sha)
        baseline=Path(library['original_library']);candidate=Path(library['candidate_library'])
        pin(baseline,accepted['original_library_sha256']);pin(candidate,accepted['candidate_library_sha256'])
        evidence=compare_archives(archive_members(baseline.read_bytes()),archive_members(candidate.read_bytes()),
                                  (library_run/'objects/qbs.cpp.o').read_bytes())
        require(evidence==json.loads((library_run/'archive-members.json').read_text()),'Archive re-audit differs')
        model_receipt=ROOT/'verification/performance/evidence/output_model_20261106_01/result.json'
        pin(model_receipt);control=json.loads(model_receipt.read_text())
        require(control['state']=='PAIRED_QWEN3_OUTPUT_MODEL_REAUDITED' and control['run']==str(MODEL_RUN),'Model gate')
        pin(MODEL_RUN/'result.json',control['worker_result_sha256'])
        pin(MODEL_RUN/'source-pins.json',control['source_pins_sha256'])
        pin(MODEL_RUN/'qemu.log',control['log_sha256'])
        pin(MODEL_RUN/'commands.json',control['audit_pins'][str(MODEL_RUN/'commands.json')])
        old=json.loads((MODEL_RUN/'source-pins.json').read_text())
        # Bind every projection profile/shape to the original GGUF and sealed graph.
        capture_receipt=ROOT/'verification/performance/evidence/qwen3_projection_capture_20261106_01/result.json'
        pin(capture_receipt);capture=json.loads(capture_receipt.read_text());capture_root=Path(capture['run'])
        pin(capture_root/'source-pins.json',capture['source_pins_sha256'])
        pin(capture_root/'model-identity.json',capture['model_identity_sha256'])
        capture_pins=json.loads((capture_root/'source-pins.json').read_text())
        model_identity=json.loads((capture_root/'model-identity.json').read_text())
        require(model_identity['embedded_file_verified'],'Model disk/host file not independently matched')
        pin(MODEL,model_identity['sha256'])
        for rel in ('src/models/qwen3.cpp','src/llama-graph.cpp'):
            pin(GRAPH/'llama'/rel,old[str(GRAPH/'llama'/rel)])
        sys.path.insert(0,str(GRAPH/'llama/gguf-py'))
        from gguf import GGUFReader
        from trace_context_model import PROJECTIONS,call_schema
        gguf=GGUFReader(str(MODEL));weights=[]
        tensor_names=[f'blk.{layer}.{name}.weight' for layer in range(28) for name,_,_ in PROJECTIONS]+['output.weight']
        for name in tensor_names:
            tensors=[t for t in gguf.tensors if t.name==name];require(len(tensors)==1,'Missing/duplicate model tensor')
            tensor=tensors[0];require(len(tensor.shape)==2,'Matrix shape')
            require(tensor.tensor_type.name in ('Q4_K','Q6_K'),'Unexpected projection type')
            weights.append(dict(tensor=name,k=int(tensor.shape[0]),n=int(tensor.shape[1]),
                                type={'Q4_K':'q4_K','Q6_K':'q6_K'}[tensor.tensor_type.name]))
        call_schema(weights,0);call_schema(weights,1)
        (out/'projection-schema.json').write_text(json.dumps(weights,indent=2)+'\n');pin(out/'projection-schema.json')
        for module in tuple(sys.modules.values()):
            filename=getattr(module,'__file__',None)
            if filename and Path(filename).is_file() and Path(filename).resolve().is_relative_to(GRAPH/'llama/gguf-py'):
                path=Path(filename).resolve();pin(path,capture_pins[str(path)])
        source_path=MODEL_RUN/'model.cpp';pin(source_path,old[str(source_path)])
        generated=out/'model.cpp';generated.write_text(fixture(source_path.read_text()));pin(generated)
        records=json.loads((MODEL_RUN/'commands.json').read_text())
        def recipe(label):
            rows=[r['argv'] for r in records if r['label']==label];require(len(rows)==1,'Recipe identity');return list(rows[0])
        cc=recipe('compile');pin(cc[0],old[str(Path(cc[0]).resolve())])
        for label,source,obj in (('model',generated,out/'model.o'),
                                 ('driver',HERE/'trace_context_model_driver.cpp',out/'driver.o')):
            command=list(cc);command[command.index('-c')+1]=str(source);command[command.index('-o')+1]=str(obj)
            dep=[v for i,v in enumerate(command) if i not in (command.index('-c'),command.index('-o'),command.index('-o')+1)]
            run([*dep,'-M','-MT','object'],'deps-'+label)
            for name in shlex.split((out/('deps-'+label+'.log')).read_text().replace('\\\n',' ').split(':',1)[1]):
                path=Path(name).resolve(strict=True)
                if path not in (source.resolve(),generated):pin(path,dependency_pin(path,old))
            run(command,'compile-'+label);pin(obj)
        base_link=recipe('link')
        require(base_link.count(str(baseline))==1 and base_link.count(str(MODEL_RUN/'model.o'))==1,'Archive/object link operands')
        for name in base_link:
            if name.endswith('.a'):pin(name,old[str(Path(name).resolve())])
        for name in ('libc.a','libstdc++.a','libm.a','libgcc.a','libgcc_eh.a','libpthread.a','libdl.a',
                     'crt1.o','crti.o','crtbeginT.o','crtend.o','crtn.o'):
            path=Path(subprocess.check_output([cc[0],'-print-file-name='+name],text=True).strip())
            pin(path,dependency_pin(path,old))
        for label,archive in (('base',baseline),('candidate',candidate)):
            command=[str(out/'model.o') if v==str(MODEL_RUN/'model.o') else str(archive) if v==str(baseline) else v
                     for v in base_link]
            command[command.index('-o')+1]=str(out/label);run(command,'link-'+label);pin(out/label)
        run([cc[0],'-static',out/'driver.o','-ldl','-lm','-pthread','-o',out/'test'],'link-driver');pin(out/'test')
        init=VERIFY/'verification/out/q8k-signed-max-model-20261026-01/init';pin(init,old[str(init)])
        listing='dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /model 755 0 0\ndir /tmp 1777 0 0\n'
        for guest,path in (('init',init),('test',out/'test'),('base',out/'base'),('candidate',out/'candidate')):
            listing+=f'file /{guest} {path} 755 0 0\n'
        (out/'initramfs.list').write_text(listing);pin(out/'initramfs.list')
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        pin(cpio,dependency_pin(cpio,old))
        with (out/'initramfs.cpio').open('xb') as stream:
            subprocess.run([cpio,out/'initramfs.list'],stdout=stream,check=True,timeout=60)
        pin(out/'initramfs.cpio');qemu=recipe('qemu')
        require('xaraqbs=true' in qemu[qemu.index('-cpu')+1] and 'readonly=on' in qemu[qemu.index('-drive')+1],
                'Native QBS CPU/read-only disk required')
        qemu[qemu.index('-initrd')+1]=str(out/'initramfs.cpio')
        sys.path.insert(0,str(ROOT/'verification/qbs'))
        from run_ggml_segmented import verify_native_build
        for path in verify_native_build(Path(qemu[0])):
            lexical=Path(path);require(old.get(str(lexical),old.get(str(lexical.resolve())))==digest(lexical),'Native emulator provenance')
            pin(lexical,digest(lexical))
        disk=Path(qemu[qemu.index('-drive')+1].split(',',1)[0].removeprefix('file='))
        require(capture_pins[str(disk.resolve())]==digest(disk),'Model disk differs from inspected GGUF capture')
        for path in (Path(qemu[0]),disk,Path(qemu[qemu.index('-bios')+1]),Path(qemu[qemu.index('-kernel')+1])):
            expected=old.get(str(path),old.get(str(path.resolve())));require(expected is not None,'Original boot input missing')
            pin(path,expected)
        verify();(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        (out/'path-identities.json').write_text(json.dumps(identities,indent=2)+'\n')
        state.update(state='TRACE_CONTEXT_MODEL_PAIR_PREPARED_NOT_EXECUTED',library_build=str(library_run),
            candidate_library_sha256=digest(candidate),source_pins_sha256=digest(out/'source-pins.json'),
            common_model_object_sha256=digest(out/'model.o'),baseline_elf_sha256=digest(out/'base'),
            candidate_elf_sha256=digest(out/'candidate'),driver_elf_sha256=digest(out/'test'))
        if args.execute_reviewed:
            run(qemu,'qemu',7200)
            measured=check((out/'qemu.log').read_text(),(MODEL_RUN/'qemu.log').read_text(),weights);verify()
            state.update(state='TRACE_CONTEXT_MODEL_PAIR_FUNCTIONAL_PASS',measured=measured,
                         log_sha256=digest(out/'qemu.log'),post_pins_match=True)
        state['artifacts']={str(path):digest(path) for path in out.iterdir() if path.is_file() and path.name not in ('result.json','status.json')}
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:save();(out/'result.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__':main()
