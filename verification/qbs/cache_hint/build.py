#!/usr/bin/env python3
"""Build a paired real multi-group cache-hint experiment; no matrix commands."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/akv/quantized_kv/prefill'))
from run_replay import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Fresh independent output required')
    prior=ROOT/'verification/out/m4-prepared-qkv-build-20261027-02'
    accepted=ROOT/'verification/out/m4-packed-qkv-vcs-20261027-01'
    if json.loads((accepted/'result.json').read_text())['state']!='PASS':
        raise ValueError('Unaccepted capture provenance')
    manifest=json.loads((prior/'manifest.json').read_text())
    report=json.loads((prior/'build.json').read_text())
    if digest(prior/'manifest.json')!=report['manifest_sha256']:
        raise ValueError('Archived manifest identity')
    inputs=[prior/'activation_f32.bin',prior/'activation_q8k_m4.bin']
    for path,size in zip(inputs,(24576,7008)):
        if path.stat().st_size!=size or digest(path)!=manifest[str(path)]:
            raise ValueError('Real activation/golden identity')
    records=json.loads((prior/'commands.json').read_text())
    recipes=[list(c) for c in records if '-c' in c][:12]
    if len(recipes)!=12:raise ValueError('Incomplete recipe')
    capture=Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators')
    captured=[]
    for name in ('attn_q','attn_v','attn_k'):
        folder=capture/('blk_0_'+name+'_weight')
        meta=json.loads((folder/'activation_f32.json').read_text())
        data=(folder/'activation_f32.bin').read_bytes()
        if meta['shape']!=[1536,15,1,1] or meta['type']!='f32' or len(data)!=92160 or \
                meta['nbytes']!=92160 or meta['strides']!=[4,6144,92160,92160]:
            raise ValueError('Capture geometry changed')
        captured.append((folder,data))
    if any(data!=captured[0][1] for _,data in captured):
        raise ValueError('QKV no longer share captured activations')
    if captured[0][1][:24576]!=inputs[0].read_bytes():
        raise ValueError('First group differs from accepted capture')
    inputs[0]=captured[0][0]/'activation_f32.bin'
    out.mkdir(parents=True)
    pins={};commands=[]
    def pin(path):
        path=Path(path).resolve(strict=True);value=digest(path)
        if str(path) in pins and pins[str(path)]!=value:raise ValueError('Input drift')
        pins[str(path)]=value
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);commands.append(dict(label=label,argv=argv))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(label+'.log')).read_text()
    for path in (Path(__file__),prior/'manifest.json',prior/'build.json',prior/'commands.json',
                 accepted/'result.json',*inputs):pin(path)
    for folder,_ in captured:
        pin(folder/'activation_f32.bin');pin(folder/'activation_f32.json')
    pin(HERE/'prepare.py')
    run([sys.executable,HERE/'prepare.py','--source',
         '/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/q8_K-prepared-cache.h',
         '--output',out/'headers'],'prepare-candidate')
    generated=json.loads((out/'headers/source-pins.json').read_text())
    for path,expected in generated.items():
        if digest(path)!=expected:raise ValueError('Candidate generation drift')
        pin(path)
    pin(out/'headers/source-pins.json')
    assembly=['.section .rodata,"a",@progbits']
    for name,path in zip(('sums_input','sums_golden'),inputs):
        assembly+=['.balign 64','.global '+name,name+':',f'.incbin "{path}"']
    (out/'data.S').write_text('\n'.join(assembly)+'\n')
    selected=[recipes[i] for i in (0,2,3,4,5,6,7,8,9)]
    selected[0][selected[0].index('-c')+1]=str(HERE/'native.cpp')
    selected[2][selected[2].index('-c')+1]=str(out/'data.S')
    objects=[]
    for i,cmd in enumerate(selected):
        cmd=[v for v in cmd if not v.startswith('-ffp-contract=')]
        cmd+=['-I'+str(out/'headers'),'-ffp-contract=fast','-isystem','/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv']
        obj=out/f'{i}.o';objects.append(str(obj));cmd[cmd.index('-o')+1]=str(obj)
        deps=[v for j,v in enumerate(cmd) if j not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
        text=run([*deps,'-M','-MT','object'],'deps-'+str(i))
        for path in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):pin(path)
        run(cmd,'compile-'+str(i))
    link=list(next(c for c in records if '-c' not in c and '-o' in c and c[c.index('-o')+1]==str(prior/'qbs_current_projection_soc')))
    link=[v for v in link if not v.endswith('.o')]
    link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')]=objects
    elf=out/'cache_hint.elf';link[link.index('-o')+1]=str(elf)
    link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
    pin(link[link.index('-T')+1])
    for name in ('libstdc++.a','libm.a','libc.a','libgcc.a','libnosys.a'):
        pin(run([link[0],'-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-print-file-name='+name],'locate-'+name).strip())
    for name in ('cc1','cc1plus','as','ld'):
        pin(run([link[0],'-print-prog-name='+name],'locate-'+name).strip())
    run(link,'link')
    dis=run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
    if 'vsse16.v' not in dis or 'vfmacc.vf' not in dis:
        raise ValueError('Required parallel quantizer vector path missing')
    for path,h in pins.items():
        if digest(path)!=h:raise ValueError('Build input drift: '+path)
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='BUILT_NOT_EXECUTED',cache_hint=True,commands_per_trial=0,
        outputs_per_trial=63072,reused_objects=0,rebuilt_objects=9,whole_prepare=True,
        elf=str(elf),elf_sha256=digest(elf),source_pins_sha256=digest(out/'source-pins.json'),
        golden=str(inputs[1]),golden_sha256=digest(inputs[1]),performance_measured=False,
        artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file()})
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    print('BUILT_NOT_EXECUTED '+str(elf))


if __name__=='__main__':main()
