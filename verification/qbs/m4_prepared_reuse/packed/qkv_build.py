#!/usr/bin/env python3
"""Combine the accepted cache policy with packed cold preparation, not ratios."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out') or out.exists():raise ValueError('Fresh independent output required')
    base=ROOT/'verification/out/m4-prepared-qkv-build-20261027-02'
    report=json.loads((base/'build.json').read_text());pins=json.loads((base/'manifest.json').read_text())
    gate=ROOT/'verification/out/m4-packed-soc-vcs-20261027-01'
    accepted=json.loads((gate/'result.json').read_text());gpins=json.loads((gate/'source-pins.json').read_text())
    if report['state']!='READY' or digest(base/'manifest.json')!=report['manifest_sha256'] or \
       accepted['state']!='PASS' or not accepted['post_pins_match'] or accepted['measured']['speedup']<=1 or \
       hashes(map(Path,pins))!=pins or hashes(map(Path,gpins))!=gpins:
        raise ValueError('Accepted build/performance/source drift')
    for name,value in gpins.items():
        if name in pins and pins[name]!=value:raise ValueError('Conflicting source identity')
        pins[name]=value
    source=HERE.parent/'qkv_projection.cpp';text=source.read_text()
    declaration='extern "C" bool m4_produce(const float *,void *,int64_t);'
    cold='const bool used=m4_produce(projection_input,destination,K);'
    if text.count(declaration)!=1 or text.count(cold)!=1:raise ValueError('Unreviewed source adaptation')
    text=text.replace(declaration,declaration+'\nextern "C" bool m4_packed_produce(const float *,void *,int64_t);')
    text=text.replace(cold,'const bool used=m4_packed_produce(projection_input,destination,K);')
    out.mkdir(parents=True);candidate=out/'main.cpp';candidate.write_text(text)
    pins.update(hashes([Path(__file__),source,candidate,base/'build.json',base/'manifest.json',
        gate/'result.json',gate/'source-pins.json',HERE.parent/'packed_producer.cpp',HERE.parent/'packed_candidate.h']))
    commands=json.loads((base/'commands.json').read_text());executed=[]
    def run(cmd,label):
        cmd=list(map(str,cmd));executed.append(cmd);atomic_json(out/'commands.json',executed)
        with (out/(label+'.log')).open('x') as stream:subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=180)
    for linux in (False,True):
        suffix='linux' if linux else 'bare';driver=base/'linux-0.o' if linux else base/'0.o'
        template=next(c for c in commands if '-c' in c and c[c.index('-o')+1]==str(driver))
        main_cmd=list(template);main_obj=out/(suffix+'-main.o')
        main_cmd[main_cmd.index('-c')+1]=str(candidate);main_cmd[main_cmd.index('-o')+1]=str(main_obj)
        run(main_cmd,suffix+'-main')
        packed_cmd=list(template);packed_obj=out/(suffix+'-packed.o')
        packed_cmd[packed_cmd.index('-c')+1]=str(HERE.parent/'packed_producer.cpp')
        packed_cmd[packed_cmd.index('-o')+1]=str(packed_obj)
        run(packed_cmd,suffix+'-packed')
        old_elf=base/('qkv-linux' if linux else 'qbs_current_projection_soc')
        link=list(next(c for c in commands if '-c' not in c and '-o' in c and c[c.index('-o')+1]==str(old_elf)))
        link=[str(main_obj) if c==str(driver) else c for c in link]
        link.insert(link.index('-o'),str(packed_obj));link[link.index('-o')+1]=str(out/old_elf.name)
        link=['-Wl,-Map='+str(out/'link.map') if c.startswith('-Wl,-Map=') else c for c in link]
        run(link,suffix+'-link')
    atomic_json(out/'contract.json',dict(comparison='original recompute versus packed cold preparation plus exact-byte reuse',
        original_scope=json.loads((base/'contract.json').read_text()),
        only_source_change='Candidate cold-miss producer; baseline original producer and all checks unchanged'))
    if hashes(map(Path,pins))!=pins:raise ValueError('Build drift')
    pins.update(hashes(x for x in out.iterdir() if x.is_file()));atomic_json(out/'manifest.json',pins)
    atomic_json(out/'build.json',dict(state='READY',elf_sha256=digest(out/'qbs_current_projection_soc'),
        linux_elf_sha256=digest(out/'qkv-linux'),manifest_sha256=digest(out/'manifest.json'),
        performance_measured=False,whole_model=False))
    print('READY')


if __name__=='__main__':main()
