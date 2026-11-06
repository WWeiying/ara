"""Shared source-gated model-input capture using immutable complete-model libraries."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from audit import digest, require, verify_pins
from ffn_capture import environment
from run_projection_capture_v3 import dependency_pin, HERE, ROOT, VERIFY, MODEL_RUN, GRAPH, MODEL


def run_capture(output, caller, checker, weight_specs, terminal_state, qemu_bound):
    out = Path(output).absolute(); caller = Path(caller).resolve(strict=True)
    require(out == out.resolve() and out.is_relative_to(VERIFY/'verification/out') and
            caller.parent == HERE and 0 < qemu_bound <= 3600, 'Capture configuration')
    out.mkdir(parents=True,exist_ok=False)
    state = dict(state='PREPARING',pid=os.getpid(),child_pid=None,performance_measured=False)
    pins = {}; commands = []
    def save(): (out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    def pin(path, expected=None):
        path = str(Path(path).resolve(strict=True)); sha = digest(path)
        require(expected is None or expected == sha, 'Prior input drift: '+path)
        require(path not in pins or pins[path] == sha, 'Input changed'); pins[path] = sha
    def run(argv,label,bound=180):
        argv = list(map(str,argv)); pin(argv[0]); verify_pins(pins)
        state['state'] = label.upper(); save(); commands.append(dict(label=label,argv=argv,timeout=bound))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        with (out/(label+'.log')).open('xb') as log:
            child = subprocess.Popen(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT)
            state['child_pid'] = child.pid; save()
            try: code = child.wait(timeout=bound)
            except BaseException: child.kill(); child.wait(); raise
            finally: state['child_pid'] = None; save()
        require(code == 0,label+' failed'); verify_pins(pins)
    save()
    try:
        receipt = ROOT/'verification/performance/evidence/output_model_20261106_01/result.json'
        accepted = json.loads(receipt.read_text())
        require(accepted['state'] == 'PAIRED_QWEN3_OUTPUT_MODEL_REAUDITED' and accepted['run'] == str(MODEL_RUN),
                'Complete-model library gate')
        pin(receipt); pin(MODEL_RUN/'result.json',accepted['worker_result_sha256'])
        pin(MODEL_RUN/'source-pins.json',accepted['source_pins_sha256'])
        old = json.loads((MODEL_RUN/'source-pins.json').read_text())
        pin(MODEL_RUN/'commands.json',accepted['audit_pins'][str(MODEL_RUN/'commands.json')])
        prior = json.loads((MODEL_RUN/'commands.json').read_text())
        for module in tuple(sys.modules.values()):
            name = getattr(module,'__file__',None)
            if name and Path(name).is_file() and Path(name).resolve().is_relative_to(HERE): pin(name)
        for relative in ('src/models/qwen3.cpp','src/llama-graph.cpp','ggml/src/ggml-backend.cpp'):
            path = GRAPH/'llama'/relative; pin(path,old[str(path)])
        pin(caller); pin(MODEL_RUN/'model.cpp',old[str(MODEL_RUN/'model.cpp')])
        header = out/'capture_environment.h'; header.write_text(environment((MODEL_RUN/'model.cpp').read_text())); pin(header)
        cc = list(next(r['argv'] for r in prior if r['label'] == 'compile'))
        cc[cc.index('-c')+1] = str(caller); cc[cc.index('-o')+1] = str(out/'capture.o'); cc.insert(1,'-I'+str(out))
        pin(cc[0],old[str(Path(cc[0]).resolve())])
        dep = [v for i,v in enumerate(cc) if i not in (cc.index('-c'),cc.index('-o'),cc.index('-o')+1)]
        run([*dep,'-M','-MT','object'],'deps')
        for name in shlex.split((out/'deps.log').read_text().replace('\\\n',' ').split(':',1)[1]):
            path = Path(name).resolve(strict=True)
            if path not in (caller,header): pin(path,dependency_pin(path,old))
        run(cc,'compile')
        link = list(next(r['argv'] for r in prior if r['label'] == 'link'))
        link[link.index(str(MODEL_RUN/'model.o'))] = str(out/'capture.o'); link[link.index('-o')+1] = str(out/'test')
        for name in link:
            if name.endswith('.a'): pin(name,old[str(Path(name).resolve())])
        for name in ('libc.a','libstdc++.a','libm.a','libgcc.a','libgcc_eh.a','libpthread.a','libdl.a',
                     'crt1.o','crti.o','crtbeginT.o','crtend.o','crtn.o'):
            path = Path(subprocess.check_output([cc[0],'-print-file-name='+name],text=True).strip())
            require(path.is_file(),'Missing target runtime'); pin(path,dependency_pin(path,old))
        run(link,'link'); pin(out/'test')
        init = VERIFY/'verification/out/q8k-signed-max-model-20261026-01/init'; pin(init,old[str(init)])
        listing = 'dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /model 755 0 0\ndir /tmp 1777 0 0\n'
        listing += f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n'
        (out/'initramfs.list').write_text(listing); pin(out/'initramfs.list')
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        pin(cpio,old[str(cpio.resolve())])
        with (out/'initramfs.cpio').open('xb') as stream:
            subprocess.run([cpio,out/'initramfs.list'],stdout=stream,check=True,timeout=60)
        pin(out/'initramfs.cpio')
        qemu = list(next(r['argv'] for r in prior if r['label'] == 'qemu'))
        require('xaraqbs=true' in qemu[qemu.index('-cpu')+1],'Native QBS emulator required')
        qemu[qemu.index('-initrd')+1] = str(out/'initramfs.cpio')
        disk = Path(qemu[qemu.index('-drive')+1].split(',',1)[0].removeprefix('file='))
        require('readonly=on' in qemu[qemu.index('-drive')+1],'Read-only model disk required')
        for path in (Path(qemu[0]),disk,Path(qemu[qemu.index('-bios')+1]),Path(qemu[qemu.index('-kernel')+1])):
            pin(path,old[str(path.resolve())])
        control_receipt = ROOT/'verification/performance/evidence/qwen3_projection_capture_20261106_01/result.json'
        control = json.loads(control_receipt.read_text()); source = Path(control['run'])
        pin(control_receipt); pin(source/'result.json',control['result_sha256'])
        pin(source/'source-pins.json',control['source_pins_sha256'])
        cpins = json.loads((source/'source-pins.json').read_text())
        pin(source/'qemu.log',json.loads((source/'result.json').read_text())['artifacts'][str(source/'qemu.log')])
        pin(source/'model-identity.json',control['model_identity_sha256'])
        identity = json.loads((source/'model-identity.json').read_text())
        require(identity['embedded_file_verified'] and identity['sha256'] == cpins[str(MODEL.resolve())] and
                cpins[str(disk.resolve())] == pins[str(disk.resolve())],'Model identity binding')
        pin(MODEL,identity['sha256'])
        # Reject missing/unsupported weights before paying for a full Prefill.
        sys.path.insert(0,str(GRAPH/'llama/gguf-py'))
        from gguf import GGUFReader
        reader = GGUFReader(str(MODEL)); weights = []
        for tensor_name,filename,k,n in weight_specs:
            require(Path(filename).name == filename and k > 0 and k%256 == 0 and n >= 128,'Weight specification')
            tensors = [t for t in reader.tensors if t.name == tensor_name]
            require(len(tensors) == 1,'Weight inventory'); tensor = tensors[0]
            require(list(map(int,tensor.shape)) == [k,n] and tensor.tensor_type.name in ('Q4_K','Q6_K'),'Weight geometry')
            row_bytes = (k//256)*({'Q4_K':144,'Q6_K':210}[tensor.tensor_type.name])
            require(tensor.n_bytes == n*row_bytes,'Weight bytes')
            raw = tensor.data.view('uint8').reshape(-1)[:128*row_bytes].tobytes()
            require(len(raw) == 128*row_bytes,'Truncated weight prefix')
            path = out/filename; path.write_bytes(raw); pin(path)
            weights.append(dict(tensor=tensor.name,type=tensor.tensor_type.name,k=k,full_n=n,captured_n=128,
                                file=filename,sha256=digest(path)))
        for module in tuple(sys.modules.values()):
            name = getattr(module,'__file__',None)
            if name and Path(name).resolve().is_relative_to(GRAPH/'llama/gguf-py'): pin(name,cpins[str(Path(name).resolve())])
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        run(qemu,'qemu',qemu_bound)
        payloads, metadata = checker((out/'qemu.log').read_text(),(source/'qemu.log').read_text())
        for name,payload in payloads.items(): (out/(name+'_f32.bin')).write_bytes(payload)
        verify_pins(pins); (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        state.update(state=terminal_state,activation=metadata,weights=weights,source_pins_sha256=digest(out/'source-pins.json'),
                     post_pins_match=True,artifacts={str(p):digest(p) for p in out.iterdir()
                         if p.is_file() and p.name not in ('status.json','result.json')})
    except BaseException as exc: state.update(state='FAIL',error=repr(exc)); raise
    finally: save(); (out/'result.json').write_text(json.dumps(state,indent=2)+'\n')
