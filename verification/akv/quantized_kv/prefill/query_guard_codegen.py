#!/usr/bin/env python3
"""Inspect actual GNU RISC-V code before admitting a new performance trial."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from query_guard_experiment import candidate, SOURCE, HERE, ROOT


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    recipe=ROOT/'verification/out/prefill-production-q4-build-20261028-01/commands.json'
    build=recipe.parent/'build.json'
    receipt=json.loads(build.read_text())
    if receipt['artifacts'][str(recipe)]!=digest(recipe):raise ValueError('Recipe drift')
    cmd=list(next(r['argv'] for r in json.loads(recipe.read_text()) if r['label']=='compile-1'))
    (out/'candidate.h').write_text(candidate(SOURCE.read_text()))
    source=out/'probe.c'
    source.write_text('#include "software/akv/experimental/quantized_kv/prefill/admission.h"\n'
        '#include "candidate.h"\n'
        '__attribute__((noinline)) int original_probe(const quant_prefill_input_t *p,quant_prefill_admission_t *o) { return quant_prefill_admit(p,o); }\n'
        '__attribute__((noinline)) int candidate_probe(const candidate_prefill_input_t *p,candidate_prefill_admission_t *o) { return candidate_prefill_admit(p,o); }\n')
    cmd[cmd.index('-c')+1]=str(source)
    cmd[cmd.index('-o')+1]=str(out/'probe.o')
    cmd+=['-I'+str(out)]
    dependencies=[v for i,v in enumerate(cmd) if i not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
    text=subprocess.check_output([*dependencies,'-M','-MT','object'],text=True,timeout=60)
    paths=[Path(p).resolve() for p in shlex.split(text.replace('\\\n',' ').split(':',1)[1])]
    objdump=Path(cmd[0]).with_name('riscv64-unknown-elf-objdump')
    paths += [Path(__file__),HERE/'query_guard_experiment.py',SOURCE,recipe,build,Path(cmd[0]),objdump]
    pins={str(p):digest(p) for p in paths}
    with (out/'compile.log').open('x') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    dis=subprocess.check_output([objdump,'-dr',out/'probe.o'],text=True,timeout=60)
    (out/'disassembly.txt').write_text(dis)
    assembly=list(cmd);assembly[assembly.index('-c')]='-S'
    assembly[assembly.index('-o')+1]=str(out/'probe.s');assembly+=['-fverbose-asm']
    subprocess.run(assembly,check=True,timeout=120)
    for path,wanted in pins.items():
        if digest(path)!=wanted:raise ValueError('Input drift: '+path)
    (out/'result.json').write_text(json.dumps(dict(state='COMPILED_NOT_BENCHMARKED',
        command=cmd,assembly_command=assembly,source_pins=pins,
        artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file()}),indent=2)+'\n')
    print('COMPILED_NOT_BENCHMARKED '+str(out))


if __name__=='__main__':main()
