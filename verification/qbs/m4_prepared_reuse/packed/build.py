#!/usr/bin/env python3
"""Incremental same-ELF comparison with a packed, ordinary unit-stride store."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out') or out.exists():raise ValueError('Fresh independent output required')
    gate=ROOT/'verification/out/m4-packed-reference-20261027-01'
    gpins=json.loads((gate/'manifest.json').read_text());g=json.loads((gate/'result.json').read_text())
    if g['state']!='PASS' or len(g['configurations'])!=4 or hashes(map(Path,gpins))!=gpins:raise ValueError('Functional gate drift')
    prior=ROOT/'verification/out/m4-tiled-soc-build-20261027-01'
    report=json.loads((prior/'build.json').read_text());pins=json.loads((prior/'manifest.json').read_text())
    if report['state']!='READY' or digest(prior/'manifest.json')!=report['manifest_sha256'] or hashes(map(Path,pins))!=pins:
        raise ValueError('Original source/object drift')
    for name,value in gpins.items():
        if name in pins and pins[name]!=value:raise ValueError('Conflicting source pin')
        pins[name]=value
    text=(HERE.parent/'tiled/main.cpp').read_text()
    if text.count('m4_tiled_produce')!=2 or text.count('M4_TILED_')!=2 or text.count('tiled=%u')!=1:
        raise ValueError('Unreviewed main adaptation')
    out.mkdir(parents=True)
    main_source=out/'main.cpp';main_source.write_text(text.replace('m4_tiled_produce','m4_packed_produce')
        .replace('M4_TILED_','M4_PACKED_').replace('tiled=%u','packed=%u'))
    commands=json.loads((prior/'commands.json').read_text());executed=[];replacement={}
    pins.update(hashes([Path(__file__),gate/'result.json',gate/'manifest.json',prior/'build.json',
                       prior/'manifest.json',prior/'commands.json',main_source,HERE.parent/'tiled/main.cpp']))
    def run(cmd,name):
        cmd=list(map(str,cmd));executed.append(cmd);atomic_json(out/'commands.json',executed)
        with (out/(name+'.log')).open('x') as stream:subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=180)
    for index,source in ((0,main_source),(2,HERE.parent/'packed_producer.cpp')):
        command=list(commands[index]);old=command[command.index('-o')+1];obj=out/f'{index}.o'
        command[command.index('-c')+1]=str(source);command[command.index('-o')+1]=str(obj)
        run(command,'compile-'+str(index));replacement[old]=str(obj)
    link=list(commands[-1]);elf=out/'qbs_current_projection_soc'
    link=[replacement.get(arg,arg) for arg in link];link[link.index('-o')+1]=str(elf)
    link=['-Wl,-Map='+str(out/'link.map') if arg.startswith('-Wl,-Map=') else arg for arg in link]
    run(link,'link')
    listing=subprocess.check_output([str(Path(link[0]).with_name('riscv64-unknown-elf-objdump')),'-d',elf],text=True)
    body='';current=''
    for line in listing.splitlines():
        if line.endswith('>:'):current=line
        if 'm4_packed_candidate' in current:body+=line+'\n'
    if not body or 'vse32.v' not in body or 'vsseg' in listing or \
       re.search(r'\b(?:vs[1248]r\.v|vl[1248]re\d+\.v)\b',body):raise ValueError('Store/spill mapping changed')
    (out/'disassembly.log').write_text(listing)
    if hashes(map(Path,pins))!=pins:raise ValueError('Build drift')
    pins.update(hashes(path for path in out.iterdir() if path.is_file()));atomic_json(out/'manifest.json',pins)
    atomic_json(out/'build.json',dict(state='READY',elf_sha256=digest(elf),manifest_sha256=digest(out/'manifest.json'),
        rebuilt_objects=2,reused_objects=9,performance_measured=False,
        scope='Preparation-only original/packed/packed/original; no segment store, cache or matrix work'))
    print('READY')


if __name__=='__main__':main()
