#!/usr/bin/env python3
"""Verify the mechanical promotion against immutable compiled candidate objects."""
import argparse
import json
from pathlib import Path
import subprocess
from build_ggml_candidate import digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT/'verification/out/akv-combined-runtime-candidate-20261024-01'
BACKUP = ROOT/'verification/out/akv-runtime-promotion-20261024-01'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        (out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    commands = []
    def invoke(argv,name):
        argv = list(map(str,argv))
        commands.append(dict(argv=argv,cwd=str(out)))
        save('commands.json',commands)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(name+'.log')).read_text()
    try:
        original = json.loads((OLD/'result.json').read_text())
        pins = json.loads((OLD/'source-pins.json').read_text())
        if original['state'] != 'COMBINED_RUNTIME_COMPILED_NOT_EXECUTED' or \
           digest(OLD/'source-pins.json') != original['source_pins_sha256']:
            raise ValueError('Unreviewed original candidate')
        pins.update(original['artifact_sha256'])
        aliases = {str(ROOT/'software/akv/src/akv_v2_native_riscv.c'):BACKUP/'native-before.c',
                   str(ROOT/'software/akv/src/akv_v2_attention_rvv.S'):BACKUP/'attention-before.S'}
        for path,want in pins.items():
            if digest(aliases.get(path,Path(path))) != want:
                raise ValueError('Original candidate input/artifact changed: '+path)
        canonical = [ROOT/'software/akv/src/akv_v2_native_riscv.c',
                     ROOT/'software/akv/src/akv_v2_attention_rvv.S']
        if canonical[0].read_bytes() != (OLD/'akv_v2_native_combined.c').read_bytes():
            raise ValueError('Promoted C is not the reviewed exact combined candidate')
        before = aliases[str(canonical[1])].read_text()
        includes = ('#include "../experimental/paired_heads/attention_rvv.S"\n'
                    '#include "../experimental/paired_heads/f32_pv/attention_rvv.S"\n')
        if canonical[1].read_text() != before+'\n'+includes:
            raise ValueError('Assembly promotion exceeds unconditional leaf inclusion')
        old_commands = json.loads((OLD/'commands.json').read_text())
        compiles = [r['argv'] for r in old_commands if '-c' in r['argv']]
        if len(compiles) != 2:
            raise ValueError('Unexpected candidate compiler inventory')
        results = []
        for index,argv in enumerate(compiles):
            argv = list(argv)
            argv[argv.index('-c')+1] = str(canonical[index])
            obj = out/f'{index}.o'
            argv[argv.index('-o')+1] = str(obj)
            invoke(argv,f'compile-{index}')
            dump = Path(argv[0]).with_name('riscv64-linux-objdump')
            old = invoke([dump,'-dr',OLD/f'{index}.o'],f'old-{index}')
            new = invoke([dump,'-dr',obj],f'new-{index}')
            trim = lambda text:text[text.index('Disassembly of section'):]
            if trim(old) != trim(new):
                raise ValueError('Promoted instruction/relocation stream differs')
            results.append(dict(source=str(canonical[index]),object_sha256=digest(obj),
                reviewed_object_sha256=digest(OLD/f'{index}.o'),instructions_and_relocations_equal=True))
        resolved = {str(aliases.get(p,Path(p))):sha for p,sha in pins.items()}
        for path in [*canonical,Path(__file__),OLD/'result.json',OLD/'source-pins.json']:
            resolved[str(path)] = digest(path)
        if any(digest(path) != sha for path,sha in resolved.items()):
            raise ValueError('Promotion input changed during verification')
        save('source-pins.json',resolved)
        save('result.json',dict(state='PROMOTED_OBJECTS_MATCH_REVIEWED_COMBINED_CANDIDATE',
            source_pins_sha256=digest(out/'source-pins.json'),objects=results,
            scope='Exact source and Linux GNU candidate object equivalence; not a fresh post-promotion RTL execution',
            post_promotion_rtl_executed=False))
        print('PROMOTED_OBJECTS_MATCH_REVIEWED_COMBINED_CANDIDATE')
    except BaseException as exc:
        save('result.json',dict(state='FAIL',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
