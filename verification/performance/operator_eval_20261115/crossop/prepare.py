#!/usr/bin/env python3
"""Build two real decode gate/up cases from archived SDK and llama sources."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

from audit_capture import DEFAULT, audit
from build_support import Builder, digest, require, save, verify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = DEFAULT
SDK_COMMIT = 'dbe2b78817ef45b912444afcb85ad6e01a2be135'
LLAMA_COMMIT = 'a2b7f30da9aadf88b0a068c447383ed2e26ee867'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--llama', type=Path, default=Path('/home/wangwy/llama/llama.cpp'))
    p.add_argument('--toolchain', type=Path, default=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin'))
    a = p.parse_args()
    out = a.output.resolve()
    require(out.parent == OUT.resolve() and not out.exists() and
            re.fullmatch(r'operator_crossop_prepare_[A-Za-z0-9_]+', out.name), 'Fresh owned output required')
    provenance = audit(DEFAULT, 'decode')
    out.mkdir()
    b = Builder(out)
    for f in HERE.iterdir():
        if f.is_file(): b.pin(f)
    capture = Path(provenance['directory'])
    for name in ('result.json', 'source-pins.json', 'ffn_norm-0_f32.bin', 'ffn_gate.bin', 'ffn_up.bin'):
        b.pin(capture / name)
    sdk, llama = out/'inputs/sdk', out/'inputs/llama'
    b.archive(ROOT, SDK_COMMIT, ['software/qbs', 'apps/common', 'verification/qbs/qbs_ref.c',
                                'verification/qbs/qbs_ref.h'], sdk)
    b.archive(a.llama, LLAMA_COMMIT, ['ggml/include', 'ggml/src'], llama)
    b.run('registered-patch-check', ['git', 'apply', '--no-index', '--reverse', '--check',
          sdk/'software/qbs/integrations/llama-decode-sums.patch'], cwd=llama)
    for tree in (sdk, llama):
        for f in tree.rglob('*'):
            if f.is_file(): b.pin(f)
    host = out/'host'; host.mkdir()
    hostflags = ['-std=c11', '-O2', '-fno-fast-math', '-ffp-contract=off', '-frounding-math',
                 '-Wall', '-Wextra', '-Werror', '-I'+str(HERE), '-I'+str(host),
                 '-I'+str(sdk/'software/qbs/include'), '-I'+str(sdk/'verification/qbs')]
    (host/'config.h').write_text('#define EVAL_M 1\n#define EVAL_N 128\n#define EVAL_WB 144\n'
                                '#define EVAL_TILE 1\n#define EVAL_PROFILE 1\n#define EVAL_STORAGE 1\n')
    for src, name in ((sdk/'verification/qbs/qbs_ref.c', 'reference'),
                      (sdk/'software/qbs/src/qbs_runtime.c', 'runtime'),
                      (HERE/'oracle.c', 'oracle'), (HERE/'verify_test.c', 'verify_test')):
        b.compile('/usr/bin/gcc', hostflags, src, host/(name+'.o'))
    b.run('host-verify-link', ['/usr/bin/gcc', host/'verify_test.o', '-o', host/'verify_test'])
    b.run('host-verify', [host/'verify_test'])
    b.run('oracle-link', ['/usr/bin/gcc', host/'oracle.o', host/'reference.o', host/'runtime.o',
                          '-lm', '-o', host/'oracle'])
    plans = []
    for op in ('gate', 'up'):
        d = out/op; d.mkdir()
        output = b.run('oracle-'+op, [host/'oracle', capture/'ffn_norm-0_f32.bin',
                                     capture/('ffn_'+op+'.bin'), d])
        plans.append(json.loads(output))
    require(plans[0]['commands'] == plans[1]['commands'] and len(plans[0]['commands']) == 4,
            'Different or unexpected command plans')
    for name in ('expected_q8.bin', 'expected_packed.bin'):
        require((out/'gate'/name).read_bytes() == (out/'up'/name).read_bytes(), 'Activation gold mismatch')
    require((out/'gate/expected.bin').read_bytes() != (out/'up/expected.bin').read_bytes(), 'Identical golds')
    cc = a.toolchain/'riscv64-unknown-elf-gcc'
    objdump = a.toolchain/'riscv64-unknown-elf-objdump'
    for name in ('cc1', 'as', 'ld'):
        tool = b.run('locate-'+name, [cc, '-print-prog-name='+name]).decode().strip()
        b.pin(Path(tool) if Path(tool).is_file() else shutil.which(tool))
    for name in ('libc.a', 'libm.a', 'libgcc.a', 'libnosys.a'):
        b.pin(b.run('locate-'+name, [cc, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
                                    '-print-file-name='+name]).decode().strip())
    common = sdk/'apps/common'; fw = out/'firmware'; fw.mkdir()
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-O3',
             '-DNDEBUG', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
             '-ffunction-sections', '-fdata-sections', '-DNR_LANES=4', '-DVLEN=1024',
             '-I'+str(common), '-I'+str(HERE), '-I'+str(sdk/'software/qbs/include')]
    ggml = llama/'ggml'
    quantflags = ['-I'+str(ggml/x) for x in ('include','src','src/ggml-cpu','src/ggml-cpu/arch/riscv')]
    sources = [(common/x, Path(x).stem) for x in
               ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    sources += [(sdk/'software/qbs/src/qbs_runtime.c','runtime'),
                (sdk/'software/qbs/src/qbs_native_riscv.c','native'),
                (ggml/'src/ggml-cpu/arch/riscv/quants.c','quant')]
    objects = []
    for src, name in sources:
        obj = fw/(name+'.o')
        b.compile(cc, flags + (quantflags if name == 'quant' else ['-fno-builtin'] if name == 'string' else []), src, obj)
        objects.append(obj)
    link = fw/'link.ld'
    b.run('linker-script', [cc, '-E','-P','-x','c','-DALIGNMENT=16', common/'arch.link.ld','-o',link])
    receipts = []
    for shared in (False, True):
        name = 'shared' if shared else 'independent'
        d = out/name; d.mkdir()
        case = dict(id=name,m=1,n=128,tile=1,reuse='direct',backend='native',shared=shared,
                    baseline_kind='independent_activation_preparation',primary_eligible=True)
        build_id = hashlib.sha256(json.dumps(dict(case=case,pins=b.pins),sort_keys=True).encode()).hexdigest()
        (d/'config.h').write_text((host/'config.h').read_text()+
            f'#define EVAL_X32 0\n#define EVAL_REUSE 0\n#define EVAL_SHARED {int(shared)}\n'
            f'#define EVAL_ID "{build_id}"\n#define EVAL_GATE_FLAGS {plans[0]["flags"]}\n'
            f'#define EVAL_UP_FLAGS {plans[1]["flags"]}\n')
        cmds = plans[0]['commands']
        (d/'plan_config.h').write_text('typedef struct { unsigned m,n,row,col,layout; } reuse_expected_command_t;\n'
            f'#define EVAL_COMMANDS {len(cmds)}\nstatic const reuse_expected_command_t reuse_expected_commands[EVAL_COMMANDS] = {{\n'+
            ''.join('  {'+','.join(str(c[k]) for k in ('m','n','row','col','layout'))+'},\n' for c in cmds)+'};\n')
        blobs = [('reuse_input',capture/'ffn_norm-0_f32.bin'),
                 ('reuse_expected_q8',out/'gate/expected_q8.bin'),('reuse_expected_packed',out/'gate/expected_packed.bin')]
        for op in ('gate','up'):
            blobs += [('reuse_weights_'+op,out/op/'weights_r4.bin'),('reuse_expected_'+op,out/op/'expected.bin')]
        (d/'data.S').write_text(''.join(f'.section .rodata.{sym},"a"\n.balign 64\n.global {sym}\n{sym}:\n.incbin "{path}"\n' for sym,path in blobs))
        perflags = flags+['-I'+str(d)]
        for src, obj in ((HERE/'main.c',d/'main.o'),(d/'data.S',d/'data.o')):
            b.compile(cc, perflags+['-Wall','-Wextra','-Werror'], src, obj)
        elf = d/'operator.elf'
        b.run('link-'+name,[cc,*perflags,'-static','-nostartfiles','-nostdlib',d/'main.o',d/'data.o',
            *objects,'-Wl,--gc-sections','-Wl,-Map='+str(d/'link.map'),'-T',link,
            '-Wl,--start-group','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf])
        dis = b.run('disassemble-'+name,[objdump,'-d','--disassemble=reuse_trial',elf]).decode()
        require(len(re.findall(r'rdcycle\s+zero',dis))==2 and 'quantize_row_q8_K' in dis,
                'ROI markers or quantizer missing')
        for f in d.iterdir():
            if f.is_file(): b.pin(f)
        receipts.append((case,d,elf,build_id))
    for tree in (host, out/'gate', out/'up', fw):
        for f in tree.rglob('*'):
            if f.is_file(): b.pin(f)
    verify(b.pins); save(out/'input-pins.json',b.pins)
    outer = dict(b.pins); outer[str(out/'input-pins.json')] = digest(out/'input-pins.json')
    manifest=[]
    for case,d,elf,build_id in receipts:
        checker = [sys.executable,'-B',str(HERE/'check.py'),'--build',str(d),'--log','{log}','--output','{result}']
        record = dict(state='BUILT_NOT_EXECUTED',rtl_executed=False,performance_measured=False,
                      case=case,plan=plans[0],plans=plans,build_id=build_id,elf=str(elf),elf_sha256=digest(elf),
                      input_pins=str(out/'input-pins.json'),input_pins_sha256=digest(out/'input-pins.json'),
                      provenance=provenance,sdk_commit=SDK_COMMIT,llama_commit=LLAMA_COMMIT)
        save(d/'build.json',record); outer[str(d/'build.json')] = digest(d/'build.json')
        manifest.append(dict(id='crossop_'+case['id'],category='qbs',elf=str(elf),elf_sha256=digest(elf),
            checker=checker,source_pins=str(out/'source-pins.json'),timeout_seconds=10800,
            plusargs=['+QBS_PERF'],baseline_kind=case['baseline_kind'],primary_eligible=True))
    save(out/'manifest.json',dict(cases=manifest)); outer[str(out/'manifest.json')]=digest(out/'manifest.json')
    save(out/'source-pins.json',outer); verify(outer)
    print(json.dumps(dict(state='BUILT_NOT_EXECUTED',manifest=str(out/'manifest.json'))))


if __name__ == '__main__':
    main()
