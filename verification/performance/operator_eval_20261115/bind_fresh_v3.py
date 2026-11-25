#!/usr/bin/env python3
"""Bind an unexecuted original QBS ELF to the exact, strict VCSR successor."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','successor-pins','checker','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        raise ValueError('Never overwrite bindings')
    data=json.loads(a.manifest.read_text())
    pins=json.loads(a.successor_pins.read_text())
    for c in data['cases']:
        args=c['checker']
        if c['category']!='qbs' or Path(args[2]).name!='check.py' or args[-2:]!=['--output','{result}']:
            raise ValueError('Only reviewed original QBS firmware can use this binding')
        for name,h in json.loads(Path(c['source_pins']).read_text()).items():
            if name in pins and pins[name]!=h:
                raise ValueError('Conflicting pinned input '+name)
            pins[name]=h
        if sha(c['elf'])!=c['elf_sha256']:
            raise ValueError('ELF drift')
        c['checker']=[*args[:2],str(a.checker),*args[3:-2],
            '--commit','{run}/commit.csv','--fresh','--audit-pins',str(a.successor_pins),*args[-2:]]
        c['source_pins']=str(a.output/'source-pins.json')
        c['checker_contract']='Fresh complete numeric/guard/work checks; VCSR2 quantizer lineage; exact RVV saturating instruction decoder'
    for f in (a.manifest,a.successor_pins,a.checker,Path(__file__).resolve()):
        pins[str(f)]=sha(f)
    for name,h in pins.items():
        if sha(name)!=h:
            raise ValueError('Pinned source drift '+name)
    a.output.mkdir()
    (a.output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    (a.output/'cases.json').write_text(json.dumps(data,indent=2)+'\n')


if __name__=='__main__':
    main()
