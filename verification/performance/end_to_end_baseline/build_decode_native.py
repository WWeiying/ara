#!/usr/bin/env python3
"""Build genuine M1 Decode SDK regions with production quantization and contexts."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess

from audit import digest, require, verify_pins
from decode_capture import check
from run_projection_capture_v3 import HERE, ROOT, VERIFY, GRAPH

PREFIX = VERIFY/'verification/out/e2e_qwen3_projection_native_build_20261106_03'
NAMES = ('attn_q','attn_v','attn_k','ffn_gate','ffn_up','ffn_down','vocabulary')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); capture = args.capture.resolve(strict=True); out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY/'verification/out'),'Fresh verification output')
    out.mkdir(parents=True,exist_ok=False); pins = {}; commands = []
    state = dict(state='PREPARING',performance_measured=False,whole_model=False,full_ggml=False)

    def pin(path,expected=None):
        path = str(Path(path).resolve(strict=True)); sha = digest(path)
        require(expected is None or sha == expected,'Input identity: '+path)
        require(path not in pins or pins[path] == sha,'Input changed'); pins[path] = sha

    def run(argv,label):
        argv = list(map(str,argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label,argv=argv)); (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        state['state'] = label.upper(); (out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
        result = subprocess.run(argv,cwd=out,capture_output=True,timeout=300)
        (out/(label+'.log')).write_bytes(result.stdout+result.stderr)
        require(result.returncode == 0,label+' failed'); return result.stdout.decode()

    try:
        receipt = ROOT/'verification/performance/evidence/decode_capture_20261106_01/result.json'
        accepted = json.loads(receipt.read_text()); audit = Path(accepted['run'])
        require(digest(audit/'result.json') == accepted['result_sha256'],'Independent capture audit identity')
        ar = json.loads((audit/'result.json').read_text())
        require(ar['state'] == 'REAL_QWEN3_DECODE_CAPTURE_REAUDITED' and Path(ar['run']) == capture,
                'Unaccepted Decode source')
        verify_pins(ar['audit_pins'])
        report = json.loads((capture/'result.json').read_text())
        require(report['state'] == 'REAL_QWEN3_DECODE_CAPTURED_NOT_BENCHMARKED' and report['post_pins_match'] and
                digest(capture/'source-pins.json') == report['source_pins_sha256'],'Capture identity')
        cpins = json.loads((capture/'source-pins.json').read_text()); verify_pins(cpins); verify_pins(report['artifacts'])
        control = VERIFY/'verification/out/e2e_qwen3_projection_capture_20261106_03/qemu.log'
        require(cpins.get(str(control)) == digest(control),'Projection control identity')
        payloads, metadata = check((capture/'qemu.log').read_text(),control.read_text())
        require(metadata == report['activation'] and all((capture/(name+'_f32.bin')).read_bytes() == data
                for name,data in payloads.items()),'Raw input replay')
        before = json.loads((PREFIX/'build.json').read_text())
        require(before['state'] == 'REAL_QWEN3_SDK_BUILT_NOT_EXECUTED' and
                digest(PREFIX/'source-pins.json') == before['source_pins_sha256'],'Common build identity')
        old = json.loads((PREFIX/'source-pins.json').read_text()); verify_pins(old); verify_pins(before['artifacts'])
        archived = json.loads((GRAPH/'source-pins.json').read_text())
        for path in (Path(__file__),HERE/'audit.py',HERE/'decode_capture.py',HERE/'decode_native.cpp',HERE/'decode_golden.c',
                     receipt,audit/'result.json',capture/'result.json',capture/'source-pins.json',
                     PREFIX/'build.json',PREFIX/'commands.json',PREFIX/'source-pins.json',GRAPH/'source-pins.json',control): pin(path)
        for path,sha in report['artifacts'].items(): pin(path,sha)
        weights = {Path(row['file']).stem:row for row in report['weights']}
        require(set(weights) == set(NAMES),'Weight inventory')
        profiles = [dict(Q4_K=1,Q6_K=2)[weights[name]['type']] for name in NAMES]
        require(profiles == [1,2,1,1,1,2,2] and all(weights[name]['captured_n'] == 128 and
                weights[name]['k'] == (6144 if name == 'ffn_down' else 2048) for name in NAMES),'Weight geometry')
        import struct
        (out/'profiles.bin').write_bytes(struct.pack('<7I',*profiles)); pin(out/'profiles.bin')
        host = ['/usr/bin/gcc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math',
                '-Wall','-Wextra','-Werror',HERE/'decode_golden.c',ROOT/'verification/qbs/qbs_ref.c','-lm','-o',out/'golden']
        deps = [v for i,v in enumerate(host) if i not in (host.index('-o'),host.index('-o')+1) and v != '-lm']
        text = run([*deps,'-M','-MT','object'],'host-deps')
        for path in shlex.split(text.replace('\\\n',' ').replace('object:',' ')): pin(path)
        run(host,'host-build'); run([out/'golden',capture,out],'host-golden')
        symbols = dict(decode_profiles=out/'profiles.bin',decode_flags=out/'flags.bin')
        for i,name in enumerate(payloads):
            symbols[f'decode_input_{i}'] = capture/(name+'_f32.bin')
            symbols[f'decode_quantized_{i}'] = out/f'activation_{i}.bin'
        for i in range(7):
            symbols[f'decode_weights_{i}'] = out/f'part_{i}_r4.bin'
            symbols[f'decode_expected_{i}'] = out/f'part_{i}_expected.bin'
        assembly = '.section .rodata\n'
        for symbol,path in symbols.items():
            pin(path); assembly += f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{path}"\n'
        (out/'data.S').write_text(assembly); pin(out/'data.S')
        recipes = {int(r['label'].split('-')[1]):list(r['argv']) for r in json.loads((PREFIX/'commands.json').read_text())
                   if r['label'].startswith('compile-')}
        require(set(recipes) == set(range(11)),'Common object inventory')
        objects = []
        # The M4 generic object is not used. Compile the unmodified archived RVV quantizer instead.
        for i in range(3,11):
            path = PREFIX/f'{i}.o'; pin(path,before['artifacts'][str(path)]); objects.append(str(path))
        quantizer = GRAPH/'llama/ggml/src/ggml-cpu/arch/riscv/quants.c'
        for i,source,template in ((0,HERE/'decode_native.cpp',0),(1,quantizer,9),(2,out/'data.S',2)):
            cmd = list(recipes[template]); cmd[cmd.index('-c')+1] = str(source)
            obj = out/f'{i}.o';cmd[cmd.index('-o')+1] = str(obj);objects.append(str(obj))
            dep = [v for j,v in enumerate(cmd) if j not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
            text = run([*dep,'-M','-MT','object'],'deps-'+str(i))
            for name in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
                path = Path(name).resolve(strict=True)
                if path.is_relative_to(GRAPH):
                    require(cpins.get(str(path),archived.get(str(path))) == digest(path),'Archived input drift: '+str(path))
                elif path not in (source.resolve(),(out/'data.S').resolve()):
                    toolchain = Path('/home/wangwy/openproject/ara/install/riscv-gcc').resolve(strict=True)
                    require(old.get(str(path)) == digest(path) or
                            (path.is_relative_to(toolchain) and path.suffix == '.h'),
                            'Unreviewed compiler dependency: '+str(path))
                pin(path)
            run(cmd,'compile-'+str(i))
        records = json.loads((PREFIX/'commands.json').read_text())
        link = [v for v in next(r['argv'] for r in records if r['label'] == 'link') if not v.endswith('.o')]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = objects
        elf = out/'decode_projection.elf';link[link.index('-o')+1] = str(elf)
        link = ['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        pin(link[link.index('-T')+1],old[str(Path(link[link.index('-T')+1]).resolve())]);run(link,'link');pin(elf)
        dis = run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        require('<quantize_row_q8_K>:' in dis and '<qbs_native_execute_command>:' in dis and
                '<qbs_ref_execute>:' not in dis and re.search(r'csrwi\s+vxrm,1',dis),
                'Production quantizer/executor or expected rounding setup missing; oracle leakage')
        sim = VERIFY/'verification/out/e2e_matrix_soc_base_20261106_01/sim'
        run(['/usr/bin/bash',VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',sim,elf],'l2')
        verify_pins(old);verify_pins(cpins);verify_pins(pins)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        state.update(state='REAL_QWEN3_DECODE_SDK_BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=digest(elf),
            source_pins_sha256=digest(out/'source-pins.json'),capture=str(capture),profiles=profiles,
            m=1,n=128,k=[2048,2048,2048,2048,2048,6144,2048],parts=list(NAMES),stages=4,trials=1,
            commands=28,outputs=896,preparation_included=True,existing_context_reuse=True,
            cold_weight_repack_included=False,reused_objects=8,rebuilt_objects=3,
            artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('status.json','build.json')})
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:
        (out/'status.json').write_text(json.dumps(state,indent=2)+'\n');(out/'build.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__ == '__main__':main()
