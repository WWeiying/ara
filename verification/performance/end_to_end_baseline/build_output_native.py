#!/usr/bin/env python3
"""Build a fresh real-data, native-QK full-call pair from an archived recipe."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from audit import digest, require, verify_pins

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
VERIFY=Path('/home/wangwy/openproject/ara_dsa_signoff_integration')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind',choices=('q4','q8'),required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve()
    require(out.is_relative_to(VERIFY/'verification/out'),'Use sole verification output area')
    prior=VERIFY/'verification/out'/f'register-pv-native-{a.kind}-build-20261028-01'
    recipe=json.loads((prior/'build.json').read_text())
    require(recipe['kind']==('q4_0' if a.kind=='q4' else 'q8_0') and recipe['token_major'], 'Recipe kind')
    for name in ('commands.json','data.S','mask.S','source-pins.json'):
        require(digest(prior/name)==recipe['artifacts'][str(prior/name)],'Recipe artifact drift')
    old_pins=json.loads((prior/'source-pins.json').read_text())
    records=json.loads((prior/'commands.json').read_text())
    compiles=[list(r['argv']) for r in records if r['label'].startswith('compile-')]
    require(len(compiles)==17,'Unexpected recipe')
    out.mkdir(parents=True,exist_ok=False)
    pins={}; commands=[]
    def pin(path):
        path=str(Path(path).resolve(strict=True)); sha=digest(path)
        require(path not in pins or pins[path]==sha,'Input changed')
        pins[path]=sha
    def run(cmd,label):
        cmd=list(map(str,cmd)); pin(cmd[0]); verify_pins(pins)
        commands.append(dict(label=label,argv=cmd))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=180)
        (out/(label+'.log')).write_bytes(r.stdout+r.stderr)
        require(r.returncode==0,label+' failed')
        return r.stdout.decode()
    report=dict(state='FAIL',performance_measured=False,whole_call=True)
    try:
        for path in (Path(__file__),HERE/'audit.py',prior/'build.json',prior/'commands.json',prior/'source-pins.json',prior/'data.S',prior/'mask.S'):
            pin(path)
        # Compiler -M does not enumerate assembler .incbin payloads.
        # Check them explicitly, including the real query and golden outputs.
        for source in (prior/'data.S',prior/'mask.S'):
            for line in source.read_text().splitlines():
                fields=shlex.split(line)
                if fields and fields[0]=='.incbin':
                    require(len(fields)==2,'Unexpected incbin operands')
                    payload=Path(fields[1]).resolve(strict=True)
                    require(old_pins.get(str(payload))==digest(payload),'Capture payload drift')
                    pin(payload)
        # Do not consume today's dirty llama checkout: retain the archived
        # compiler recipe's GGML inputs and check each dependency against pins.
        compiles[1][compiles[1].index('-c')+1]=str(HERE/'output_native_main.c')
        compiles[16][compiles[16].index('-c')+1]=str(ROOT/'software/akv/experimental/quantized_kv/register_pv/entry.c')
        candidate=list(compiles[16])
        candidate[candidate.index('-c')+1]=str(ROOT/'software/akv/experimental/quantized_kv/output_tile/runtime.c')
        compiles.append(candidate)
        objects=[]
        for i,cmd in enumerate(compiles):
            # Override SDK sources/headers with this reviewed worktree; external
            # GGML/toolchain/capture inputs must match the archived pin exactly.
            src=Path(cmd[cmd.index('-c')+1])
            if src.is_relative_to(VERIFY/'software') or src.is_relative_to(VERIFY/'apps'):
                cmd[cmd.index('-c')+1]=str(ROOT/src.relative_to(VERIFY))
            cmd[1:1]=['-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include')]
            obj=out/f'{i}.o'; objects.append(str(obj)); cmd[cmd.index('-o')+1]=str(obj)
            deps=[v for j,v in enumerate(cmd) if j not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
            text=run([*deps,'-M','-MT','object'],'deps-'+str(i))
            for dep in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
                path=Path(dep).resolve(strict=True)
                if not path.is_relative_to(ROOT):
                    require(old_pins.get(str(path))==digest(path),'Unpinned/changed archived input: '+str(path))
                pin(path)
            run(cmd,'compile-'+str(i))
        link=[list(r['argv']) for r in records if r['label']=='link']
        require(len(link)==1,'Ambiguous link')
        link=[v for v in link[0] if not v.endswith('.o')]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')]=objects
        elf=out/'output_native.elf'; link[link.index('-o')+1]=str(elf)
        link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        pin(link[link.index('-T')+1])
        for name in ('libm.a','libgcc.a'):
            pin(run([link[0],'-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-print-file-name='+name],'locate-'+name).strip())
        for name in ('cc1','as','ld'):
            pin(run([link[0],'-print-prog-name='+name],'locate-'+name).strip())
        run(link,'link'); pin(elf)
        dis=run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        for name in ('quant_register_execute','quant_output_tile_execute','qbs_native_execute_command','main'):
            require('<'+name+'>:' in dis,'Missing native symbol '+name)
        require('<qbs_ref_execute>:' not in dis,'Reference executor leaked into native ELF')
        verify_pins(pins)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        report.update(state='BUILT_NOT_EXECUTED',kind=recipe['kind'],elf=str(elf),
            elf_sha256=digest(elf),source_pins_sha256=digest(out/'source-pins.json'),
            baseline='register_pv',candidate='output_tile',rebuilt_objects=18,
            outputs_per_trial=256,commands_per_trial=1,token_major=True,
            scope='Real Qwen3 query19 GQA2 D128 visible20; full call, not whole model',
            artifacts={str(path):digest(path) for path in out.iterdir() if path.is_file()})
    except Exception as exc:
        report['error']=repr(exc); raise
    finally:
        (out/'build.json').write_text(json.dumps(report,indent=2)+'\n')
        print(report['state'])


if __name__=='__main__': main()
