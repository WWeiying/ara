#!/usr/bin/env python3
"""Fresh-object real-capture native build for the two-group V-cache experiment."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
from query_guard_build import capture_inputs, digest, token_major
from value_cache_sources import generate, HERE, ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipe-build',type=Path,required=True)
    p.add_argument('--kind',choices=('q4_0','q8_0'),required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();prior=args.recipe_build.resolve(strict=True);out=args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Fresh independent output required')
    report=json.loads((prior/'build.json').read_text())
    records_path=prior/'commands.json';old_pins=prior/'source-pins.json'
    if (report['state']!='BUILT_NOT_EXECUTED' or report.get('token_major') is not True or
        digest(records_path)!=report['artifacts'][str(records_path)] or
        digest(old_pins)!=report['source_pins_sha256']):
        raise ValueError('Recipe identity')
    records=json.loads(records_path.read_text())
    compiles=[list(r['argv']) for r in records if r['label'].startswith('compile-')]
    names=['quants.c','native_strided_main.c','qbs_runtime.c','qbs_native_riscv.c',
        'crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c',
        'data.S','ggml-quants.c','pv_primitives.c','runtime.c','mask.S','runtime_strided.c']
    if len(compiles)!=len(names):raise ValueError('Object count')
    for cmd,name in zip(compiles,names):
        if Path(cmd[cmd.index('-c')+1]).name!=name:raise ValueError('Recipe source '+name)
    audit=ROOT/'verification/out/quant-prefill-capture-audit-20261028-01'
    if json.loads((audit/'result.json').read_text())['state']!='PASS':raise ValueError('Capture audit')
    capture=ROOT/'verification/out/quant-prefill-capture-20261028-01'/args.kind/'prefill/block'
    inputs=capture_inputs(capture,args.kind,json.loads((audit/'manifest.json').read_text()))
    out.mkdir();pins={};commands=[]
    def pin(path):
        path=Path(path).resolve(strict=True);value=digest(path)
        if str(path) in pins and pins[str(path)]!=value:raise ValueError('Input drift '+str(path))
        pins[str(path)]=value
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);commands.append(dict(label=label,argv=argv))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(label+'.log')).read_text()
    for path in [*generate(out),*inputs,Path(__file__),HERE/'query_guard_build.py',
                 HERE/'run_replay.py',HERE/'token_major.py',HERE/'value_cache_native.c',
                 audit/'result.json',audit/'manifest.json',prior/'build.json',records_path,old_pins]:pin(path)
    data={}
    for name,width in (('attn_k_input-0',72 if args.kind=='q4_0' else 136),('attn_v_input-0',136)):
        dest=out/(name+'.bin');dest.write_bytes(token_major((capture/(name+'.bin')).read_bytes(),width))
        pin(dest);data[name]=dest
    asm=['.section .rodata,"a",@progbits']
    for symbol,name in (('prefill_query','attn_q_input-0'),('prefill_key','attn_k_input-0'),
                         ('prefill_value','attn_v_input-0'),('prefill_golden','kqv_out-0')):
        payload=data.get(name,capture/(name+'.bin'))
        asm.extend(['.balign 64','.global '+symbol,symbol+':',f'.incbin "{payload}"'])
    asm.extend(['.balign 4','.global prefill_scale','prefill_scale:','.word 0x3db504f3',
                '.global prefill_q4','prefill_q4:','.word '+str(int(args.kind=='q4_0'))])
    (out/'data.S').write_text('\n'.join(asm)+'\n')
    (out/'mask.S').write_text('.section .rodata,"a",@progbits\n.balign 64\n.global prefill_mask\nprefill_mask:\n'
                            '.incbin "'+str(capture/'attn_mask_input-0.bin')+'"\n')
    for index,source in ((1,HERE/'value_cache_native.c'),(10,out/'data.S'),(14,out/'mask.S')):
        compiles[index][compiles[index].index('-c')+1]=str(source)
    objects=[]
    for i,cmd in enumerate(compiles):
        cmd+=['-I'+str(HERE),'-I'+str(out)]
        obj=out/f'{i}.o';objects.append(str(obj));cmd[cmd.index('-o')+1]=str(obj)
        deps=[v for j,v in enumerate(cmd) if j not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
        text=run([*deps,'-M','-MT','object'],'deps-'+str(i))
        for path in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):pin(path)
        run(cmd,'compile-'+str(i))
    links=[r['argv'] for r in records if r['label']=='link']
    if len(links)!=1:raise ValueError('Link recipe')
    link=[v for v in links[0] if not v.endswith('.o')];pos=link.index('-Wl,--gc-sections');link[pos:pos]=objects
    elf=out/'prefill.elf';link[link.index('-o')+1]=str(elf)
    link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
    pin(link[link.index('-T')+1])
    for lib in ('libm.a','libgcc.a'):
        pin(run([link[0],'-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-print-file-name='+lib],'locate-'+lib).strip())
    for prog in ('cc1','as','ld'):pin(run([link[0],'-print-prog-name='+prog],'locate-'+prog).strip())
    run(link,'link')
    dis=run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
    # native_qk is inlined in this program; require both real callback entries
    # and the aligned command adapter, rather than a dead out-of-line symbol.
    for symbol in ('main','qbs_native_execute_command','quant_prefill_panel_qk',
                   'vcache_qk','quant_prefill_aligned_execute'):
        if '<'+symbol+'>:' not in dis:raise ValueError('Missing native symbol '+symbol)
    decoder=dis.split('<prefill_native_decode>:',1)
    if len(decoder)!=2 or not all(op in decoder[1].split('\n\n',1)[0]
        for op in ('vle8.v','vsext.vf4','vfcvt.f.x.v','vfmul.vf','vse32.v')):
        raise ValueError('RVV V decoder missing')
    if '<qbs_ref_execute>:' in dis or '<dequantize_row_q8_0>:' in dis:raise ValueError('Reference binding')
    for path,value in pins.items():
        if digest(path)!=value:raise ValueError('Build input drift '+path)
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='BUILT_NOT_EXECUTED',value_cache=True,kind=args.kind,elf=str(elf),elf_sha256=digest(elf),
        source_pins_sha256=digest(out/'source-pins.json'),commands_per_trial=8,outputs_per_trial=2048,
        value_decodes=[12,8,8,12],reused_objects=0,rebuilt_objects=16,whole_call=True,token_major=True,
        golden=str(capture/'kqv_out-0.bin'),golden_sha256=digest(capture/'kqv_out-0.bin'),
        scope='Qwen3 queries0..7 GQA2 D128 one KV head, two groups, original versus bounded V cache',
        performance_measured=False,artifacts={str(f):digest(f) for f in out.iterdir() if f.is_file()})
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    print('VCACHE_BUILT_NOT_EXECUTED '+str(elf))


if __name__=='__main__':main()
