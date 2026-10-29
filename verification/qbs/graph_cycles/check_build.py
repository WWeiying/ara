#!/usr/bin/env python3
"""Cross-compile the isolated probe and require OFF preprocessor equivalence."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--commands',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    prepared=args.prepared.resolve(strict=True)
    receipt=json.loads((prepared/'preparation.json').read_text())
    source=Path(receipt['source'])
    assert digest(source)==receipt['source_sha256']
    for name,value in receipt['artifacts'].items(): assert digest(Path(name))==value,name
    entries=[x for x in json.loads(args.commands.read_text()) if Path(x['file'])==source]
    assert len(entries)==1
    entry=entries[0];base=shlex.split(entry['command'])
    args.output.mkdir(parents=True,exist_ok=False)
    commands=[]
    result=dict(state='FAIL',runtime_validated=False)
    try:
        for name,path,enabled in [('original',source,False),('off',prepared/'ggml-cpu.c',False),
                                  ('on',prepared/'ggml-cpu.c',True)]:
            command=base.copy();command[command.index('-c')+1]=str(path)
            command[command.index('-o')+1]=str((args.output/(name+'.o')).resolve())
            if enabled: command.append('-DGGML_RISCV_NODE_CYCLES=1')
            commands.append(command)
            with (args.output/(name+'.log')).open('w') as log:
                subprocess.run(command,cwd=entry['directory'],stdout=log,stderr=subprocess.STDOUT,
                               check=True,timeout=180)
            if not enabled:
                command=command.copy();command[command.index('-c')]='-E'
                command[command.index('-o')+1]=str((args.output/(name+'.i')).resolve())
                command.append('-P');commands.append(command)
                subprocess.run(command,cwd=entry['directory'],check=True,timeout=180,
                               stdout=subprocess.DEVNULL)
        assert (args.output/'original.i').read_bytes()==(args.output/'off.i').read_bytes(), 'OFF source differs'
        assert digest(source)==receipt['source_sha256'], 'Source drift'
        result.update(state='COMPILE_PASS_NOT_RUNTIME_ACCEPTED',off_preprocessed_equal=True,
                      original_off_objects_equal=digest(args.output/'original.o')==digest(args.output/'off.o'),
                      source_sha256=receipt['source_sha256'])
    finally:
        (args.output/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
