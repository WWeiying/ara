#!/usr/bin/env python3
"""Merge explicit run manifests without changing individual case identities."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args(); cases=[]; ids=set(); sources={}
    for path in a.manifest:
        sources[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
        for c in json.loads(path.read_text())['cases']:
            if c['id'] in ids:
                raise ValueError('Duplicate case '+c['id'])
            ids.add(c['id']);cases.append(c)
    with a.output.open('x') as f:
        json.dump(dict(cases=cases, merged_inputs=sources),f,indent=2);f.write('\n')


if __name__=='__main__':
    main()
