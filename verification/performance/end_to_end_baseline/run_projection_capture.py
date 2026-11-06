#!/usr/bin/env python3
"""Capture real Qwen3 pre-projection inputs with previously audited llama libs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from audit import digest, require, verify_pins
from check_projection_capture import check

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
MODEL_RUN = VERIFY/'verification/out/e2e_output_model_20261106_01'
GRAPH = VERIFY/'verification/out/e2e_output_graph_20261106_01'
MODEL = Path('/home/wangwy/llama/models/Qwen3-1.7B-Q4_K_M.gguf')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY/'verification/out'), 'Fresh verification output')
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None, performance_measured=False)
    pins = {}; commands = []
    def save(): (out/'status.json').write_text(json.dumps(state, indent=2)+'\n')
    def pin(path, expected=None):
        path = Path(path).resolve(strict=True); sha = digest(path)
        require(expected is None or expected == sha, 'Prior input identity: '+str(path))
        require(str(path) not in pins or pins[str(path)] == sha, 'Input drift')
        pins[str(path)] = sha
    def run(argv, label, bound=180):
        argv = list(map(str, argv)); pin(argv[0]); state['state'] = label.upper(); save()
        commands.append(dict(label=label, argv=argv, timeout=bound))
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        with (out/(label+'.log')).open('xb') as log:
            child = subprocess.Popen(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT)
            state['child_pid'] = child.pid; save()
            try: code = child.wait(timeout=bound)
            except BaseException: child.kill(); child.wait(); raise
            finally: state['child_pid'] = None; save()
        require(code == 0, label+' failed')
    try:
        receipt = ROOT/'verification/performance/evidence/output_model_20261106_01/result.json'
        accepted = json.loads(receipt.read_text())
        require(accepted['state'] == 'PAIRED_QWEN3_OUTPUT_MODEL_REAUDITED' and
                accepted['run'] == str(MODEL_RUN), 'Unaccepted complete model libraries')
        pin(receipt); pin(MODEL_RUN/'result.json', accepted['worker_result_sha256'])
        pin(MODEL_RUN/'source-pins.json', accepted['source_pins_sha256'])
        old = json.loads((MODEL_RUN/'source-pins.json').read_text())
        prior = json.loads((MODEL_RUN/'commands.json').read_text())
        pin(MODEL_RUN/'commands.json', accepted['audit_pins'][str(MODEL_RUN/'commands.json')])
        for path in (Path(__file__), HERE/'audit.py', HERE/'capture_projection.cpp', HERE/'check_projection_capture.py'):
            pin(path)
        # Capture at this source-defined boundary, before build_qkv consumes cur.
        for name in ('src/models/qwen3.cpp', 'src/llama-graph.cpp', 'ggml/src/ggml-backend.cpp'):
            path = GRAPH/'llama'/name; pin(path, old[str(path)])
        cc = list(next(c['argv'] for c in prior if c['label'] == 'compile'))
        cc[cc.index('-c')+1] = str(HERE/'capture_projection.cpp')
        cc[cc.index('-o')+1] = str(out/'capture.o')
        pin(cc[0], old[str(Path(cc[0]).resolve())])
        # Enumerate the new fixture's real transitive headers with the same compiler.
        dep = [v for i, v in enumerate(cc) if i not in (cc.index('-c'), cc.index('-o'), cc.index('-o')+1)]
        run([*dep, '-M', '-MT', 'object'], 'deps')
        import shlex
        for name in shlex.split((out/'deps.log').read_text().replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(name).resolve(strict=True)
            if path != HERE/'capture_projection.cpp':
                require(str(path) in old, 'Unpinned archived header: '+str(path)); pin(path, old[str(path)])
        run(cc, 'compile')
        link = list(next(c['argv'] for c in prior if c['label'] == 'link'))
        link[link.index(str(MODEL_RUN/'model.o'))] = str(out/'capture.o')
        link[link.index('-o')+1] = str(out/'test')
        for name in link:
            if name.endswith('.a'): pin(name, old[str(Path(name).resolve())])
        run(link, 'link'); pin(out/'test')
        init = VERIFY/'verification/out/q8k-signed-max-model-20261026-01/init'
        pin(init, old[str(init)])
        listing = 'dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /model 755 0 0\ndir /tmp 1777 0 0\n'
        listing += f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n'
        (out/'initramfs.list').write_text(listing); pin(out/'initramfs.list')
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        pin(cpio, old[str(cpio)])
        with (out/'initramfs.cpio').open('xb') as f:
            subprocess.run([cpio, out/'initramfs.list'], stdout=f, check=True, timeout=60)
        pin(out/'initramfs.cpio')
        qemu = list(next(c['argv'] for c in prior if c['label'] == 'qemu'))
        qemu[qemu.index('-initrd')+1] = str(out/'initramfs.cpio')
        disk = Path(qemu[qemu.index('-drive')+1].split(',', 1)[0].removeprefix('file='))
        require('readonly=on' in qemu[qemu.index('-drive')+1] and
                'xaraqbs=true' in qemu[qemu.index('-cpu')+1], 'Wrong model environment')
        for path in (Path(qemu[0]), disk, Path(qemu[qemu.index('-bios')+1]), Path(qemu[qemu.index('-kernel')+1])):
            pin(path, old[str(path.resolve(strict=True))])
        # Prove the host GGUF used for raw weight extraction is the guest file.
        pin(MODEL); pin('/usr/sbin/debugfs'); pin('/usr/bin/timeout')
        state['state'] = 'CHECK_EMBEDDED_MODEL'; save()
        debug = ['/usr/bin/timeout', '180', '/usr/sbin/debugfs', '-R', 'cat /models/'+MODEL.name, str(disk)]
        commands.append(dict(label='embedded-model-sha256', argv=debug, timeout=180))
        with (out/'debugfs.log').open('xb') as log:
            child = subprocess.Popen(debug, stdout=subprocess.PIPE, stderr=log)
            state['child_pid'] = child.pid; save(); h = hashlib.sha256(); size = 0
            for block in iter(lambda: child.stdout.read(1024*1024), b''):
                h.update(block); size += len(block)
            require(child.wait(timeout=180) == 0 and size == MODEL.stat().st_size and
                    h.hexdigest() == pins[str(MODEL.resolve())], 'Guest/host model mismatch')
            state['child_pid'] = None
        (out/'model-identity.json').write_text(json.dumps(dict(path=str(MODEL), guest='/model/models/'+MODEL.name,
            sha256=h.hexdigest(), bytes=size, embedded_file_verified=True), indent=2)+'\n')
        pin(out/'model-identity.json')
        (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        verify_pins(pins)
        run(qemu, 'qemu', 1200)
        payload, metadata = check((out/'qemu.log').read_text())
        (out/'activation_f32.bin').write_bytes(payload)
        # Read original GGUF bytes, never the runtime's repacked weight buffer.
        sys.path.insert(0, str(GRAPH/'llama/gguf-py'))
        from gguf import GGUFReader
        reader = GGUFReader(str(MODEL)); weights = []
        for tensor_name in ('blk.0.attn_q.weight', 'blk.0.attn_k.weight', 'blk.0.attn_v.weight'):
            matches = [t for t in reader.tensors if t.name == tensor_name]
            require(len(matches) == 1, 'Missing/duplicate projection tensor')
            t = matches[0]; shape = list(map(int, t.shape))
            require(shape[0] == 2048 and len(shape) == 2 and shape[1] >= 128 and
                    t.tensor_type.name in ('Q4_K', 'Q6_K'), 'Unexpected Qwen3 weight')
            row_bytes = t.n_bytes//shape[1]
            require(row_bytes*shape[1] == t.n_bytes and row_bytes == 8*({'Q4_K':144,'Q6_K':210}[t.tensor_type.name]),
                    'Raw quantized row geometry')
            name = tensor_name.replace('blk.0.', '').replace('.weight', '')+'.bin'
            raw = t.data.view('uint8').reshape(-1)[:128*row_bytes].tobytes()
            require(len(raw) == 128*row_bytes, 'Truncated weight prefix')
            (out/name).write_bytes(raw)
            weights.append(dict(tensor=t.name, profile=t.tensor_type.name, original_shape=shape,
                                captured_n=128, k=2048, file=name, sha256=digest(out/name)))
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).resolve().is_relative_to(GRAPH/'llama/gguf-py'): pin(path)
        verify_pins(pins); (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        state.update(state='REAL_QWEN3_PROJECTION_CAPTURED_NOT_BENCHMARKED', activation=metadata,
            activation_sha256=digest(out/'activation_f32.bin'), weights=weights,
            source_pins_sha256=digest(out/'source-pins.json'), post_pins_match=True,
            artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('status.json','result.json')})
    except BaseException as exc: state.update(state='FAIL', error=repr(exc)); raise
    finally: save(); (out/'result.json').write_text(json.dumps(state, indent=2)+'\n')


if __name__ == '__main__': main()
