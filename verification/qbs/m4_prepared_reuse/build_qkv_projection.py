#!/usr/bin/env python3
"""Real M4 Q/V/K full-output pair, fresh SDK objects and checked captured data."""
import argparse
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    installed=ROOT/'verification/out/m4-prepared-installed-model-20261027-01'
    pins=json.loads((installed/'manifest.json').read_text())
    if json.loads((installed/'result.json').read_text())['state']!='PASS' or hashes(map(Path,pins))!=pins:
        raise ValueError('Installed model acceptance drift')
    base=ROOT/'verification/qbs/combined_zvfh_m4/projection/build-03'
    oldpins=json.loads((base/'manifest.json').read_text())
    for name in ('activation_f32.bin','activation_q8k_m4.bin','weight_r4.bin','oracle_f32.bin','generic.cpp'):
        path=base/name
        if oldpins.get(str(path))!=digest(path):raise ValueError('Original data/reference drift')
        pins.update(hashes([path]))
    capture=Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m')
    replay=capture/'replay/manifest.json'
    integrity=json.loads(replay.read_text())['tensor_integrity'];pins.update(hashes([replay]))
    operations=[];input_bytes=None
    for name,kind,n,block in (('q','q4_K',1536,144),('v','q6_K',256,210),('k','q4_K',256,144)):
        directory=capture/f'prefill/operators/blk_0_attn_{name}_weight'
        for stem,typ,shape,strides,size in (
            ('activation_f32','f32',[1536,15,1,1],[4,6144,92160,92160],92160),
            ('weight_'+kind,kind,[1536,n,1,1],[block,6*block,n*6*block,n*6*block],n*6*block),
            ('output_f32','f32',[n,15,1,1],[4,n*4,n*60,n*60],n*60)):
            meta=directory/(stem+'.json');binary=directory/(stem+'.bin');m=json.loads(meta.read_text())
            if (m['type'],m['shape'],m['strides'],m['nbytes'])!=(typ,shape,strides,size) or binary.stat().st_size!=size:
                raise ValueError('Capture geometry: '+name+'/'+stem)
            entries=[r for r in integrity if r['data']==str(binary.relative_to(capture))]
            if len(entries)!=1 or entries[0]['sha256']!=digest(binary):raise ValueError('Capture identity')
            pins.update(hashes([meta,binary]))
        value=(directory/'activation_f32.bin').read_bytes()[:24576]
        if input_bytes is not None and value!=input_bytes:raise ValueError('Q/V/K inputs differ')
        input_bytes=value
        weights=(directory/('weight_'+kind+'.bin')).read_bytes()
        r4=b''.join(weights[((row+r)*6+b)*block:((row+r)*6+b+1)*block]
                    for row in range(0,n,4) for b in range(6) for r in range(4))
        expected=(base/'oracle_f32.bin').read_bytes() if name=='q' else (directory/'output_f32.bin').read_bytes()[:n*16]
        if len(expected)!=n*16 or not all(math.isfinite(x[0]) for x in struct.iter_unpack('<f',expected)):
            raise ValueError('Oracle shape/finite domain')
        if name=='q' and r4!=(base/'weight_r4.bin').read_bytes():raise ValueError('Independent Q oracle weight mismatch')
        operations.append((name,r4,expected))
    if input_bytes!=(base/'activation_f32.bin').read_bytes():raise ValueError('Golden preparation input mismatch')
    pins.update(hashes([Path(__file__),HERE/'qkv_projection.cpp',HERE/'producer.cpp',base/'commands.json']))
    out.mkdir(parents=True,exist_ok=False)
    (out/'activation_f32.bin').write_bytes(input_bytes)
    (out/'activation_q8k_m4.bin').write_bytes((base/'activation_q8k_m4.bin').read_bytes())
    assets=[('projection_input',out/'activation_f32.bin'),('projection_input_reference',out/'activation_f32.bin'),
            ('projection_golden',out/'activation_q8k_m4.bin')]
    for name,r4,expected in operations:
        weight=out/(name+'_r4.bin');oracle=out/(name+'_oracle.bin');weight.write_bytes(r4);oracle.write_bytes(expected)
        assets.extend(((name+'_weights',weight),(name+'_weights_reference',weight),(name+'_expected',oracle)))
    assembly=out/'data.S';assembly.write_text('.section .rodata\n'+''.join(
        f'.balign 64\n.global {name}\n{name}:\n.incbin "{path}"\n' for name,path in assets))
    link=out/'link.ld';link.write_bytes((base/'link.ld').read_bytes())
    templates=json.loads((base/'commands.json').read_text())
    sources=[HERE/'qkv_projection.cpp',HERE/'producer.cpp',base/'generic.cpp',assembly,
        *(ROOT/'apps/common'/name for name in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')),
        ROOT/'software/qbs/src/qbs_runtime.c',ROOT/'software/qbs/src/qbs_native_riscv.c']
    pins.update(hashes(sources));pins.update(hashes((ROOT/'apps/common').glob('*.h')))
    records=[];objects=[]
    def run(cmd,label):
        cmd=list(map(str,cmd));records.append(cmd);atomic_json(out/'commands.json',records)
        with (out/(label+'.log')).open('x') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
    for i,source in enumerate(sources):
        cmd=list(templates[0] if source.suffix=='.cpp' else templates[2])
        cmd[cmd.index('-c')+1]=str(source);obj=out/f'{i}.o';cmd[cmd.index('-o')+1]=str(obj)
        cmd+=['-I'+str(ROOT/'software/qbs/ggml')]
        if source.name=='string.c':cmd+=['-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns']
        run(cmd,'bare-'+str(i));objects.append(obj)
    compiler=Path(templates[0][0]);elf=out/'qbs_current_projection_soc'
    library_names=('libstdc++.a','libm.a','libc.a','libgcc.a','libnosys.a')
    for name in library_names:
        archive=Path(subprocess.check_output([compiler,'-print-file-name='+name],text=True).strip()).resolve(strict=True)
        pins.update(hashes([archive]))
    run([compiler,'-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax','-static','-nostartfiles','-nostdlib',
         *objects,'-Wl,--gc-sections','-Wl,-Map='+str(out/'link.map'),'-T',link,'-Wl,--start-group',
         '-lstdc++','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf],'bare-link')
    linux=Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-g++')
    includes=[*['-I'+str(x) for x in (ROOT/'software/qbs/include',ROOT/'software/qbs/ggml')],
              *[f for x in ('include','src','src/ggml-cpu') for f in ('-isystem','/home/wangwy/llama/llama.cpp/ggml/'+x)]]
    flags=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-O3','-fno-fast-math','-ffp-contract=off',*includes]
    linux_objects=[]
    for i,source in enumerate([*sources[:4],*sources[-2:]]):
        cpp=source.suffix=='.cpp';driver=linux if cpp else linux.with_name('riscv64-linux-gcc')
        obj=out/f'linux-{i}.o';extra=['-std=c++17','-DPROJECTION_LINUX'] if cpp else ['-std=gnu11']
        run([driver,*flags,*extra,'-c',source,'-o',obj],'linux-'+str(i));linux_objects.append(obj)
    run([linux,'-static',*linux_objects,'-lm','-o',out/'qkv-linux'],'linux-link')
    if hashes(map(Path,pins))!=pins:raise ValueError('Build drift')
    atomic_json(out/'contract.json',dict(m=4,k=1536,outputs=[1536,256,256],profiles=['Q4_K','Q6_K','Q4_K'],
        commands_per_trial=64,order=[0,1,1,0],rows=[0,4],q_oracle='Accepted independent decoded-sum oracle',
        vk_oracle='Original captured GGML first-four-row outputs; fixed 2e-3 absolute/relative tolerance',
        included=['plan/descriptor/native dispatch','all three preparations/copies','cold allocation and final release',
                  'all 64 native commands','8192 output elements','cycle fences/CSR/bookkeeping'],
        excluded=['GGML graph lookahead/threadpool/allocator','model loading','weight repacking','integrity/oracle checks'],
        scope='Real full-N M4 projection chain slice, not end-to-end model or hardware baseline comparison'))
    pins.update(hashes(p for p in out.iterdir() if p.is_file()));atomic_json(out/'manifest.json',pins)
    atomic_json(out/'build.json',dict(state='READY',execution='NOT_RUN',elf_sha256=digest(elf),
        linux_elf_sha256=digest(out/'qkv-linux'),manifest_sha256=digest(out/'manifest.json')))
    print(json.dumps(dict(state='READY',output=str(out))))


if __name__=='__main__':main()
