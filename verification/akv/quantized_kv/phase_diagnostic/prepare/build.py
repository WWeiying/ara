#!/usr/bin/env python3
"""GNU-only diagnostic build/preflight; no image, simulator or EDA invocation."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render
from elf import Elf

ROOT, BASE = render.ROOT, render.BASE
CONSUMER = ROOT / 'verification/akv/quantized_kv/canonical_q4_hsb/run.py'
CONSUMER_SHA = '715dfe948977163c993e6bc0b587c62cec5d15d13f1191e6d8104da41b2bcf79'
LINK_SHA = '38d6d1b0314672296e5ebd532eeff83bc09c7a99c8356e463941bd5c8ebaed7d'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return render.digest(Path(path).read_bytes())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def verify(pins):
    for path, expected in pins.items():
        require(sha(path) == expected, 'Input drift: '+path)


def consumer():
    require(sha(CONSUMER) == CONSUMER_SHA, 'Frozen program consumer changed')
    spec = importlib.util.spec_from_file_location('phase_diag_accepted_program', CONSUMER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def templates():
    records = json.loads((BASE/'predecessor-commands.json').read_text())
    compile_rows = [r['argv'] for r in records if r['label'] == 'compile']
    link_rows = [r['argv'] for r in json.loads((BASE/'commands.json').read_text()) if r['label'] == 'link']
    require(len(compile_rows) == len(link_rows) == 1, 'Ambiguous compile/link')
    cc, link = compile_rows[0], link_rows[0]
    policy(cc, link)
    return cc, link


def policy(cc, link):
    require(Path(cc[0]).name == Path(link[0]).name == 'riscv64-unknown-elf-gcc', 'GNU compiler only')
    require([x for x in cc if x.startswith('-ffp-contract=')] == ['-ffp-contract=fast'] and
            [x for x in link if x.startswith('-ffp-contract=')] == ['-ffp-contract=off'], 'Changed FP contract')
    for argv in (cc, link):
        require('-fno-fast-math' in argv and '-ffast-math' not in argv and '-Ofast' not in argv and
                '-ffreestanding' in argv and '-fno-builtin' in argv and
                '-fno-tree-loop-distribute-patterns' in argv and '-march=rv64gcv_zfh_zvfh' in argv,
                'Changed architecture/libc/FP policy')
    require(cc.count('-c') == cc.count('-o') == 1 and '-Werror' in cc and
            len([x for x in cc if x.endswith('.c')]) == 1 and link.count('-o') == link.count('-T') == 1 and
            link.count(str(BASE/'main.o')) == 1 and link.count('-Wl,--gc-sections') == 1 and
            len([x for x in link if x.startswith('-Wl,-Map=')]) == 1, 'Changed build shape')


def linker(output):
    data = (BASE/'link.ld').read_text()
    require(render.digest(data.encode()) == LINK_SHA, 'Fixed-layout linker drift')
    require(data.count(str(BASE/'main.o')) == 2, 'Wrong main placements')
    data = data.replace(str(BASE/'main.o'), str(output/'main.o'))
    data = render.replace_one(data, '    . += 0x48;', '    . = 0x1c4c;')
    return render.replace_one(data,
        'ASSERT(__review_main_body_end == 0x80001c04, "Reviewed main size differs")',
        'ASSERT(__review_main_body_end <= 0x80001c4c, "Diagnostic main exceeds reserved slot")')


def protocol_bytes(data):
    # The immutable primitive prefix retains unused predecessor strings.
    # Only the diagnostic namespace is an executable protocol claim here.
    terminal = b'QUANT_DIAG_HSB_SUITE_PASS trials=3 outputs=768 rvv_exact=1 repeat_checks=0\n\0'
    require(b'QUANT_THREEWAY_' not in data and data.count(b'QUANT_DIAG_HSB_') == 4 and
            data.count(terminal) == 1, 'Wrong linked diagnostic protocol')


def mapped(elf, assembly, prior):
    new, old = Elf(elf), Elf(BASE/'threeway_attention.elf')
    sections = new.allocated()
    require(sections and min(s['address'] for s in sections) >= 0x80000000 and
            max(s['address']+s['bytes'] for s in sections) < 0x81000000-65536, 'L2 extent exceeds stack reserve')
    rows = {}
    for name,row in prior['objects_and_tensor_symbols'].items():
        a,b = old.symbols[name],new.symbols[name]
        require(a['address'] == b['address'] and a['size'] == b['size'], 'Data layout changed: '+name)
        proof = dict(address=b['address'], size=b['size'], address_size_equal=True)
        if 'payload_compared_bytes' in row:
            extent = row['payload_compared_bytes']
            require(old.payload(name,extent) == new.payload(name,extent), 'Data bytes changed: '+name)
            proof.update(payload_bytes=extent, payload_sha256=render.digest(new.payload(name,extent)))
        else:
            require(new.sections[b['section']][1] == 8, 'Expected NOBITS')
            proof['uninitialized_storage_only'] = True
        rows[name] = proof
    functions = {}
    for name in prior['nonmain_functions']:
        a,b = old.symbols[name],new.symbols[name]
        require(a['address'] == b['address'] and a['size'] == b['size'] and old.payload(name) == new.payload(name),
                'Nonmain linked function changed: '+name)
        functions[name] = dict(start=b['address'], end=b['address']+b['size'], bytes_sha256=render.digest(new.payload(name)))
    main = new.symbols['main']
    instructions = []
    for line in assembly.splitlines():
        match = re.fullmatch(r'\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)', line)
        if match and main['address'] <= int(match[1],16) < main['address']+main['size']:
            instructions.append(dict(pc=int(match[1],16), encoding=match[2], text=match[3]))
    cycles = [i for i in instructions if re.match(r'rdcycle\s',i['text'])]
    require(len(cycles) == 2 and all((int(i['encoding'],16) & 0xfffff07f) == 0xc0002073 for i in cycles),
            'Need exactly two genuine rdcycle sites in main')
    require(any('fence' in i['text'] for i in instructions) and any('vmv.x.s' in i['text'] for i in instructions),
            'Missing original drain/fence')
    protocol_bytes(new.data)
    return dict(sections=sections, objects=rows, nonmain_functions=functions,
                main=main, rdcycle_sites=cycles, main_instructions=instructions,
                attribution='Use actual retired PCs/call stack; numeric interval between timer PCs alone is NOT a CFG',
                timed_machine_identity=False, execution='NOT_RUN')


def build(output, prepare_only=False):
    output = output.absolute()
    require(output == output.resolve() and not output.exists() and output.is_relative_to(HERE/'out'),
            'Use fresh output under owned prepare/out')
    admitted = consumer()
    report,pins = admitted.checked_program()
    # Consume only the accepted program, never canonical/old image validators.
    originals = dict(pins)
    source = render.SOURCE.read_bytes()
    generated = render.render(source)
    cc,link = templates()
    reused = {x:sha(x) for x in link if x.endswith('.o') and x != str(BASE/'main.o')}
    require(len(reused) == 16 and reused == report['original_16_object_identity_map'], 'Wrong reused object set')
    for module in tuple(sys.modules.values()):
        name = getattr(module,'__file__',None)
        if name and Path(name).is_file() and Path(name).resolve().is_relative_to(ROOT):
            pins[str(Path(name).resolve())] = sha(name)
    for path in [*HERE.glob('*.py'), HERE/'README.md', HERE/'.gitignore', Path(sys.executable).resolve(), CONSUMER]:
        pins[str(path)] = sha(path)
    verify(pins)
    output.mkdir(parents=True)
    main,elf = output/'diagnostic.c',output/'q4_hsb_phase_diagnostic.elf'
    main.write_bytes(generated);(output/'link.ld').write_text(linker(output))
    proof=render.provenance(generated);save(output/'source-transform.json',proof)
    oldsource=next(x for x in cc if x.endswith('.c'))
    cc=[str(main) if x==oldsource else x for x in cc];cc[cc.index('-o')+1]=str(output/'main.o')
    link=[str(output/'main.o') if x==str(BASE/'main.o') else '-Wl,-Map='+str(output/'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
    link[link.index('-T')+1]=str(output/'link.ld');link[link.index('-o')+1]=str(elf)
    drop={cc.index('-c'),cc.index('-o'),cc.index('-o')+1}
    deps=[x for i,x in enumerate(cc) if i not in drop]+['-M','-MT','object']
    objdump=Path(cc[0]).with_name('riscv64-unknown-elf-objdump')
    require(str(objdump) in pins and cc[0] in pins, 'Unpinned tools')
    commands=[dict(label=n,argv=a,cwd=str(output),timeout_seconds=120) for n,a in
              [('dependencies',deps),('compile',cc),('link',link),('disassembly',[str(objdump),'-d',str(elf)])]]
    save(output/'planned-commands.json',commands)
    for path in (main,output/'link.ld',output/'source-transform.json',output/'planned-commands.json'):
        pins[str(path)]=sha(path)
    save(output/'input-pins-before.json',pins)
    try:
        if prepare_only:
            state='PREPARED_NOT_COMPILED'
            mapping=None
        else:
            executed=[]
            env=dict(os.environ,PATH='/usr/bin:/bin',LC_ALL='C',PYTHONDONTWRITEBYTECODE='1')
            for key in ('GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','LD_PRELOAD'):
                env.pop(key,None)
            for command in commands:
                verify(pins)
                log=output/(command['label']+'.log')
                with log.open('x') as stream:
                    completed=subprocess.run(command['argv'],cwd=output,env=env,stdout=stream,
                                             stderr=subprocess.STDOUT,timeout=120,check=False)
                executed.append(dict(command,exit_code=completed.returncode));save(output/'commands.json',executed)
                require(completed.returncode == 0,'GNU stage failed: '+command['label'])
                if command['label']=='dependencies':
                    body=log.read_text().replace('\\\n',' ').split(':',1)[1]
                    paths=[Path(x).resolve(strict=True) for x in shlex.split(body)]
                    require(all(str(p)==str(main) or originals.get(str(p))==sha(p) for p in paths),
                            'New/changed dependency outside accepted program inventory')
                    save(output/'dependency-pins.json',{str(p):sha(p) for p in paths})
                verify(pins)
            mapping=mapped(elf,(output/'disassembly.log').read_text(),json.loads((BASE/'layout-review.json').read_text()))
            save(output/'object-map.json',mapping)
            state='DIAGNOSTIC_GNU_STATIC_PASS_NOT_EXECUTED'
        verify(pins)
        save(output/'input-pins-after.json',pins)
        artifacts={str(p):sha(p) for p in output.iterdir() if p.is_file()}
        result=dict(state=state,execution='NOT_RUN',diagnostic_only=True,trials=3,trial_order=[0,1,2],
            outputs_per_trial=768,total_outputs=2304,expected_qbs_commands=8,repeat_checks=0,
            source_provenance=proof,accepted_program_receipt_sha256=admitted.RECEIPT_SHA,
            accepted_elf_sha256=admitted.ELF_SHA,reused_objects=reused,
            rebuilt_objects=[str(output/'main.o')],elf=str(elf) if elf.exists() else None,
            elf_sha256=sha(elf) if elf.exists() else None,
            input_pins_sha256=sha(output/'input-pins-before.json'),post_pins_match=True,artifacts=artifacts,
            runtime_acceptance=False,numerical_execution_checked=False,performance_claim=False,
            old_timed_machine_identity=False,accepted_six_call_evidence_replaced=False,
            image_admission='NOT_PERFORMED; parent-owned future actual-canonical gate',simulations_launched=0)
        save(output/'build.json',result)
        return result
    except BaseException as error:
        save(output/'build.json',dict(state='FAIL',execution='NOT_RUN',error=repr(error),simulations_launched=0))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    print(build(args.output,args.preflight_only)['state'])
