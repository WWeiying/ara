#!/usr/bin/env python3
"""Build isolated F32 PV RTL fixture; no simulator launch or canonical edits."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
from rtl_check import ROOT, HERE, SHAPES, EXPECTED, require
sys.path.insert(0, str(HERE.parent/'contexts'))
import context_spec
from build_context import validate_capture
import attention_run as tools

CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')


def gather(capture, case):
    block = capture/'decode/block'
    q32 = (block/'attn_q_input-0.bin').read_bytes()
    key = (block/'attn_k_input-0.bin').read_bytes()
    value = (block/'attn_v_input-0.bin').read_bytes()
    d, head = case['d'], case['head']
    q = bytearray(b'\xa5'*512)
    k, v = bytearray(b'\xa5'*16384), bytearray(b'\xa5'*16384)
    coeff, scale, accum = (bytearray(b'\xa5'*n) for n in (512,64,1024))
    for h in range(2):
        for dim in range(d):
            x = struct.unpack_from('<f', q32, ((head*6+h)*128+dim)*4)[0]
            struct.pack_into('<e', q, (h*d+dim)*2, x)
            x = struct.unpack_from('<e',value,((head*256+h)*128+dim)*2)[0]
            struct.pack_into('<f',accum,(h*d+dim)*4,x)
        struct.pack_into('<f',scale,h*4,.5 if h == 0 else 1.)
        for t in range(case['tokens']):
            struct.pack_into('<f',coeff,h*256+t*4,1./3. if (h+t)%2 else .5)
    for t in range(64):
        for dim in range(d):
            source = ((head*256+t)*128+dim)*2
            target = (t*d+dim)*2
            k[target:target+2] = key[source:source+2]
            v[target:target+2] = value[source:source+2]
            require(k[target:target+2] == key[source:source+2] and
                    v[target:target+2] == value[source:source+2], 'Capture coordinate mismatch')
    result = bytes(q+k+v+coeff+scale+accum)
    require(len(result) == 34880, 'Fixture layout mismatch')
    require(all(math.isfinite(x) for (x,) in struct.iter_unpack('<e',v[:128*d])), 'Nonfinite active V')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    def pin(paths):
        tools.merge_pins(pins, tools.hashes([Path(x).resolve(strict=True) for x in paths]))
    def save(name, value):
        (out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    def run(argv, name):
        argv = list(map(str,argv))
        commands.append(dict(argv=argv,cwd=str(out)))
        save('commands.json',commands)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(name+'.log')).read_text()
    try:
        capture = context_spec.CAPTURE_ROOT/'kv128'
        info = validate_capture(capture,128)
        pin(info['files'])
        pin([Path(__file__),HERE/'rtl_main.c',HERE/'rtl_check.py',HERE/'rtl_test.py',
             HERE/'rtl_oracle.c',HERE/'oracle.c',HERE.parent/'rtl_check.py',
             Path(context_spec.__file__),HERE.parent/'contexts/build_context.py',
             HERE.parent/'threeway_build.py',HERE.parent/'attention_run.py',
             ROOT/'verification/akv/run_qk_panel4_abba.py',Path(sys.executable).resolve()])
        simv = ROOT/'verification/out/qbacc-soc-20261023-02/build/sim/simv'
        image,accepted = tools.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',simv)
        tools.merge_pins(pins,accepted)
        host = Path('/usr/bin/gcc')
        objdump = CC.with_name('riscv64-unknown-elf-objdump')
        pin([host,CC,objdump])
        for compiler,name in ((host,'host'),(CC,'target')):
            run([compiler,'--version'],name+'-version')
            for tool in ('cc1','as','ld'):
                path = run([compiler,'-print-prog-name='+tool],name+'-'+tool).strip()
                pin([path if '/' in path else shutil.which(path)])
        pin([run([CC,'-print-libgcc-file-name'],'libgcc-path').strip()])
        (out/'inputs.bin').write_bytes(b''.join(gather(capture,c) for c in SHAPES))
        run([sys.executable,'-B','-m','unittest','discover','-s',HERE,'-p','rtl_test.py','-v'],'host-tests')
        oracle = out/'oracle'
        host_flags = ['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math',
                      '-frounding-math','-ffp-contract=off','-fno-builtin-fmaf','-Wno-unknown-pragmas']
        for i,source in enumerate((HERE/'oracle.c',HERE/'rtl_oracle.c')):
            deps = run([host,*host_flags,'-M','-MT','oracle',source],f'host-deps-{i}')
            pin(shlex.split(deps.replace('\\\n',' ').split(':',1)[1]))
        run([host,*host_flags,HERE/'oracle.c',HERE/'rtl_oracle.c','-lm','-o',oracle],'host-compile')
        libs = run(['/usr/bin/ldd',oracle],'host-libraries')
        pin(['/usr/bin/ldd',*re.findall(r'(/[^\s()]+)',libs)])
        lines = run([oracle,out/'inputs.bin',out/'golden.bin'],'oracle-results').splitlines()
        require(len(lines) == 3 and (out/'golden.bin').stat().st_size == 3072, 'Oracle extent mismatch')
        cases = []
        for c,line in zip(SHAPES,lines):
            prefix = f"F32_ORACLE case={c['id']} d={c['d']} tokens={c['tokens']} outputs={2*c['d']} fcsr="
            require(line.startswith(prefix) and line[len(prefix):].isdigit(), 'Oracle record mismatch')
            flags = int(line[len(prefix):])
            require(flags <= 31 and flags & 8, 'Oracle flags mismatch')
            cases.append(dict(c,fcsr=flags))
        (out/'rtl_data.h').write_text('static const struct { unsigned d,tokens,fcsr; } rtl_cases[3] = {\n'+
            ''.join('{%d,%d,%d},\n'%(c['d'],c['tokens'],c['fcsr']) for c in cases)+'};\n')
        (out/'rtl_data.S').write_text('.section .rodata,"a",@progbits\n'+''.join(
            f'.balign 64\n.global rtl_{name}\nrtl_{name}:\n.incbin "{out/file}"\n'
            for name,file in (('inputs','inputs.bin'),('golden','golden.bin'))))
        common = ROOT/'apps/common'
        helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
        spec = importlib.util.spec_from_file_location('pv_elf_tools',helper)
        elf_tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(elf_tools)
        pin([helper,common/'arch.link.ld'])
        template = (common/'arch.link.ld').read_text()
        require(template.count('LENGTH = 0x00100000') == template.count('*(.bss)') == 1,'Link template drift')
        linker = out/'link.ld'
        linker.write_text(template.replace('ALIGNMENT','16').replace('LENGTH = 0x00100000',
            'LENGTH = 0x01000000').replace('*(.bss)','*(.bss .bss.*)'))
        flags = ['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax','-O3',
            '-std=gnu11','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-fno-common',
            '-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin',
            '-fno-tree-loop-distribute-patterns','-DNR_LANES=4','-DVLEN=1024',
            '-I'+str(ROOT),'-I'+str(out),'-I'+str(common),'-I'+str(ROOT/'software/akv/include'),'-I'+str(ROOT/'apps/include')]
        sources = [HERE/'rtl_main.c',HERE.parent.parent/'qk_panel4_native/rtl_native.c',
            ROOT/'software/akv/src/akv_runtime.c',ROOT/'software/akv/src/akv_native_riscv.c',
            ROOT/'software/akv/src/akv_v2_attention_rvv.S',
            ROOT/'software/akv/experimental/paired_heads/f32_pv/attention_rvv.S',
            *[common/n for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')],out/'rtl_data.S']
        for i,source in enumerate(sources):
            deps = run([CC,*flags,'-M','-MT','object',source],f'deps-{i}')
            pin(shlex.split(deps.replace('\\\n',' ').split(':',1)[1]))
        pin([linker,out/'inputs.bin',out/'golden.bin',oracle])
        save('source-pins.json',pins)
        objects = []
        for i,source in enumerate(sources):
            obj = out/f'{i}.o'
            extra = ['-Wall','-Wextra','-Werror'] if source == HERE/'rtl_main.c' else []
            run([CC,*flags,*extra,'-c',source,'-o',obj],f'compile-{i}')
            if source == common/'string.c':
                elf_tools.check_libc(run([objdump,'-dr',obj],'libc-disassembly'))
            objects.append(obj)
        elf = out/'akv_paired_f32_pv.elf'
        run([CC,*flags,'-static','-nostdlib','-nostartfiles',*objects,'-Wl,--gc-sections',
             '-Wl,-Map='+str(out/'link.map'),'-T',linker,'-lgcc','-o',elf],'link')
        disasm = run([objdump,'-d',elf],'disassembly')
        for name in ('akv_v2_update_outputs_f32_generic','akv_experimental_pv_f32_pair','rtl_akv_full','rtl_akv_release'):
            require(f'<{name}>:' in disasm and re.search(r'\b(?:jalr?|jr?)\b[^\n]*<'+name+r'>',disasm), 'Missing actual call: '+name)
        require(re.search(r'vmv\.x\.s\s+\w+,\s*v12\n[^\n]*fence\s+rw,rw\n[^\n]*frcsr\s+\w+\n[^\n]*csrr\s+\w+,\s*vcsr',disasm), 'Missing drain/CSR boundary')
        sections = elf_tools.alloc_sections(elf)
        require(min(s['address'] for s in sections) >= 0x80000000 and
                max(s['address']+s['bytes'] for s in sections) < 0x81000000-65536,'ELF bounds')
        tools.verify_pins(pins)
        require(tools.hashes(tools.image_files(simv)) == image,'Image inventory drift')
        save('build.json',dict(state='BUILT_NOT_EXECUTED',execution='NOT_RUN',elf=str(elf),
            elf_sha256=tools.digest(elf),source_pins=str(out/'source-pins.json'),
            source_pins_sha256=tools.digest(out/'source-pins.json'),post_pins_match=True,
            artifact_sha256=tools.hashes([f for f in out.iterdir() if f.is_file()]),cases=cases,
            expected=EXPECTED,simv=str(simv),accepted_image_pins=image,capture=str(capture),
            capture_provenance=info['provenance'],sections=sections,
            scope='Isolated F32 PV derived real Q/K/V; directed scores/scales, not complete model softmax or Attention',
            oracle='Independent C fmaf/fenv oracle, initial sticky DZ8; generic/paired all bytes and CSR on chip'))
        print(json.dumps(dict(state='BUILT_NOT_EXECUTED',elf=str(elf))))
    except BaseException as exc:
        save('build.json',dict(state='FAIL',execution='NOT_RUN',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
