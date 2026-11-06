#!/usr/bin/env python3
"""Expand the accepted real capture to complete Q/K/V weights, not larger K."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

from audit import digest, require, verify_pins
from full_projection import native_source, golden_source, N, K, M
from run_projection_capture_v3 import ROOT, VERIFY, GRAPH, HERE, MODEL

TEMPLATE_COMMIT = '739c54722'
CAPTURE = VERIFY/'verification/out/e2e_qwen3_projection_capture_20261106_03'
PREFIX = VERIFY/'verification/out/e2e_qwen3_projection_native_build_20261106_03'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY/'verification/out'), 'Fresh verification output')
    before = json.loads((PREFIX/'build.json').read_text())
    require(before['state'] == 'REAL_QWEN3_SDK_BUILT_NOT_EXECUTED' and
            digest(PREFIX/'source-pins.json') == before['source_pins_sha256'], 'Prefix build identity')
    old = json.loads((PREFIX/'source-pins.json').read_text()); verify_pins(old); verify_pins(before['artifacts'])
    captured = json.loads((CAPTURE/'result.json').read_text())
    require(captured['state'] == 'REAL_QWEN3_PROJECTION_CAPTURED_NOT_BENCHMARKED', 'Capture state')
    cpins = json.loads((CAPTURE/'source-pins.json').read_text())
    require(digest(CAPTURE/'source-pins.json') == captured['source_pins_sha256'], 'Capture pin map')
    model_path = MODEL.resolve(strict=True)
    require(cpins.get(str(model_path)) == digest(model_path), 'Wrong complete model')
    out.mkdir(parents=True, exist_ok=False); pins = {}; commands = []
    state = dict(state='PREPARING', performance_measured=False, full_n=True, full_ggml=False, whole_model=False)
    def pin(path, expected=None):
        path = str(Path(path).resolve(strict=True)); sha = digest(path)
        require(expected is None or sha == expected, 'Input identity: '+path)
        require(path not in pins or pins[path] == sha, 'Input changed'); pins[path] = sha
    def run(argv, label):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv)); (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        state['state'] = label.upper(); (out/'status.json').write_text(json.dumps(state, indent=2)+'\n')
        result = subprocess.run(argv, cwd=out, capture_output=True, timeout=180)
        (out/(label+'.log')).write_bytes(result.stdout+result.stderr)
        require(result.returncode == 0, label+' failed'); return result.stdout.decode()
    try:
        for path in (Path(__file__), HERE/'full_projection.py', HERE/'audit.py', PREFIX/'build.json',
                     PREFIX/'commands.json', PREFIX/'source-pins.json', CAPTURE/'result.json', CAPTURE/'source-pins.json'):
            pin(path)
        pin(model_path, cpins[str(model_path)])
        for name in ('projection_native.cpp', 'projection_golden.c'):
            relative = 'verification/performance/end_to_end_baseline/'+name
            blob = subprocess.check_output(['/usr/bin/git','-C',str(ROOT),'show',TEMPLATE_COMMIT+':'+relative])
            require(old.get(str(ROOT/relative)) == hashlib.sha256(blob).hexdigest(), 'Wrong frozen template')
            pin(ROOT/relative, old[str(ROOT/relative)])
            target = out/('full_native.cpp' if name.endswith('.cpp') else 'full_golden.c')
            text = native_source(blob.decode()) if name.endswith('.cpp') else golden_source(
                blob.decode(), ROOT/'verification/qbs/qbs_ref.h')
            target.write_text(text); pin(target)
        pin(CAPTURE/'activation_f32.bin', captured['activation_sha256'])
        # Extract all rows with the exact same official reader as the prefix capture.
        sys.path.insert(0,str(GRAPH/'llama/gguf-py'))
        from gguf import GGUFReader
        reader = GGUFReader(str(model_path)); raw_weights = []
        for part, name in enumerate(('attn_q','attn_k','attn_v')):
            tensors = [t for t in reader.tensors if t.name == 'blk.0.'+name+'.weight']
            require(len(tensors) == 1, 'Tensor inventory'); tensor = tensors[0]
            require(list(map(int,tensor.shape)) == [K,N[part]] and
                    tensor.tensor_type.name == ('Q4_K','Q4_K','Q6_K')[part], 'Full tensor geometry/type')
            raw = tensor.data.view('uint8').reshape(-1).tobytes()
            row_bytes = (K//256)*(144 if part<2 else 210)
            require(len(raw) == N[part]*row_bytes and
                    raw[:128*row_bytes] == (CAPTURE/(name+'.bin')).read_bytes(), 'Prefix/full model mismatch')
            target = out/(name+'.bin'); target.write_bytes(raw); pin(target)
            raw_weights.append(dict(tensor=tensor.name, n=N[part], k=K,
                                    type=tensor.tensor_type.name, sha256=digest(target)))
        # The oracle loads activation_f32.bin beside the original-weight files.
        (out/'activation_f32.bin').write_bytes((CAPTURE/'activation_f32.bin').read_bytes()); pin(out/'activation_f32.bin')
        for module in tuple(sys.modules.values()):
            path = getattr(module,'__file__',None)
            if path and Path(path).resolve().is_relative_to(GRAPH/'llama/gguf-py'):
                pin(path,cpins[str(Path(path).resolve())])
        host = ['/usr/bin/gcc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math',
                '-Wall','-Wextra','-Werror',out/'full_golden.c',ROOT/'verification/qbs/qbs_ref.c','-lm','-o',out/'golden']
        dep = [v for i,v in enumerate(host) if i not in (host.index('-o'),host.index('-o')+1) and v!='-lm']
        text = run([*dep,'-M','-MT','object'],'host-deps')
        for path in shlex.split(text.replace('\\\n',' ').replace('object:',' ')): pin(path)
        run(host,'host-build'); run([out/'golden',out,out],'host-golden')
        require((out/'activation_q8k_m4.bin').read_bytes() == (PREFIX/'activation_q8k_m4.bin').read_bytes(), 'Quantized input drift')
        import numpy as np
        for part, name in enumerate(('attn_q','attn_k','attn_v')):
            row_bytes = (K//256)*(144 if part<2 else 210)
            require((out/(name+'_r4.bin')).read_bytes()[:128*row_bytes] == (PREFIX/(name+'_r4.bin')).read_bytes(), 'R4 prefix drift')
            full = np.fromfile(out/(name+'_expected.bin'), dtype='<u4').reshape(M,N[part])
            prefix = np.fromfile(PREFIX/(name+'_expected.bin'), dtype='<u4').reshape(M,128)
            require(np.array_equal(full[:,:128],prefix), 'Golden prefix drift')
        symbols = dict(projection_input=out/'activation_f32.bin', projection_golden=out/'activation_q8k_m4.bin')
        for short,name in (('q','attn_q'),('k','attn_k'),('v','attn_v')):
            for suffix,artifact in (('weights','r4'),('expected','expected'),('flags','fflags')):
                symbols[short+'_'+suffix] = out/(name+'_'+artifact+'.bin')
        assembly = '.section .rodata\n'
        for symbol,path in symbols.items():
            pin(path); assembly += f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{path}"\n'
        (out/'data.S').write_text(assembly); pin(out/'data.S')
        records = json.loads((PREFIX/'commands.json').read_text())
        recipes = {int(r['label'].split('-')[1]):list(r['argv']) for r in records if r['label'].startswith('compile-')}
        require(set(recipes) == set(range(11)), 'Common object inventory')
        objects = []
        for i in range(11):
            if i in (0,2): continue
            path=PREFIX/f'{i}.o'; pin(path,before['artifacts'][str(path)]); objects.append(str(path))
        for i,source in ((0,out/'full_native.cpp'),(2,out/'data.S')):
            cmd=recipes[i]; cmd[cmd.index('-c')+1]=str(source); obj=out/f'{i}.o'
            cmd[cmd.index('-o')+1]=str(obj); objects.append(str(obj))
            dep=[v for j,v in enumerate(cmd) if j not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
            text=run([*dep,'-M','-MT','object'],'deps-'+str(i))
            for name in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
                path=Path(name).resolve(strict=True)
                require(path in (source.resolve(),(out/'data.S').resolve()) or old.get(str(path))==digest(path),
                        'Common compile dependency changed: '+str(path)); pin(path)
            run(cmd,'compile-'+str(i))
        link=[v for v in next(r['argv'] for r in records if r['label']=='link') if not v.endswith('.o')]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')]=objects
        elf=out/'full_qkv.elf'; link[link.index('-o')+1]=str(elf)
        link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        pin(link[link.index('-T')+1],old[str(Path(link[link.index('-T')+1]).resolve())])
        run(link,'link'); pin(elf)
        for mode in ('base','wide'):
            sim=VERIFY/'verification/out'/('e2e_matrix_soc_'+mode+'_20261106_01/sim')
            run(['/usr/bin/bash',VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',sim,elf], 'l2-'+mode)
        verify_pins(old); verify_pins(pins); (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        state.update(state='FULL_QWEN3_SDK_BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=digest(elf),
            source_pins_sha256=digest(out/'source-pins.json'),m=M,n=list(N),k=K,trials=1,
            commands=128,outputs=16384,weights=raw_weights,template_commit=TEMPLATE_COMMIT,
            reused_objects=9,rebuilt_objects=2,preparation_included=True,cold_weight_repack_included=False,
            artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('status.json','build.json')})
    except BaseException as exc: state.update(state='FAIL',error=repr(exc)); raise
    finally:
        (out/'status.json').write_text(json.dumps(state,indent=2)+'\n'); (out/'build.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__': main()
