#!/usr/bin/env python3
"""New manifest for unchanged ELFs, with the reviewed strict VCSR successor."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--successor-pins',type=Path,required=True)
    p.add_argument('--checker',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir()
    manifest=json.loads(a.manifest.read_text())
    pins=json.loads(a.successor_pins.read_text())
    for case in manifest['cases']:
        original=json.loads(Path(case['source_pins']).read_text())
        for name,h in original.items():
            if name in pins and pins[name]!=h:
                raise ValueError('Conflicting input '+name)
            pins[name]=h
        args=case['checker']
        if Path(args[2]).name!='check.py' or args[-2:]!=['--output','{result}']:
            raise ValueError('Unreviewed original checker command')
        case['checker']=[*args[:2],str(a.checker),*args[3:-2],
                         '--commit','{run}/commit.csv',*args[-2:]]
        case['source_pins']=str(a.output/'source-pins.json')
        case['checker_contract']='VCSR2 established by original RVV quantizer; exact preservation plus ELF/commit audit'
    for name in (a.manifest,a.successor_pins,a.checker,Path(__file__).resolve()):
        pins[str(name)]=sha(name)
    for name,h in pins.items():
        if sha(name)!=h:
            raise ValueError('Pinned input drift '+name)
    (a.output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    (a.output/'cases.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    main()
