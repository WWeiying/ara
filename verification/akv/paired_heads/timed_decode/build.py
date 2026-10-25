#!/usr/bin/env python3
"""Reuse pinned canonical objects; compile only the timing-only main and relink."""
import argparse
import importlib.util
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
from timed_spec import (SCHEMA, SOURCE, SOURCE_SHA, ELF_TOOLS, s, original_run,
                        own_files, render)


def recipe(entries, out):
    compiles = [r['argv'] for r in entries if '-c' in r['argv']]
    links = [r['argv'] for r in entries if '-nostdlib' in r['argv']]
    s.require(len(compiles) == 13 and len(links) == 1, 'Original canonical build inventory changed')
    mains = [v for v in compiles if v[v.index('-c')+1] == str(SOURCE)]
    s.require(len(mains) == 1, 'Need exactly one original main')
    objects = [v[v.index('-o')+1] for v in compiles]
    s.require(len(set(objects)) == 13 and [x for x in links[0] if x.endswith('.o')] == objects,
              'Link object order/inventory differs')
    native = [v for v in compiles if Path(v[v.index('-c')+1]).name == 'akv_v2_native_riscv.c']
    s.require(len(native) == 1 and not any('candidate.c' in x for v in compiles for x in v),
              'Need canonical, not experimental runtime objects')
    argv = list(mains[0])
    for flag in ('-fno-fast-math', '-ffp-contract=off', '-ffreestanding', '-fno-builtin'):
        s.require(flag in argv, 'Missing required compiler flag '+flag)
    s.require(Path(argv[0]).name == 'riscv64-unknown-elf-gcc' and
              not any(x.startswith(('-flto', '@')) for x in argv+links[0]), 'Unexpected GNU recipe')
    main_object = argv[argv.index('-o')+1]
    argv[argv.index('-c')+1] = str(out/'main.c')
    argv[argv.index('-o')+1] = str(out/'main.o')
    link = [str(out/'main.o') if x == main_object else
            '-Wl,-Map='+str(out/'link.map') if x.startswith('-Wl,-Map=') else x for x in links[0]]
    link[link.index('-o')+1] = str(out/'timed_decode.elf')
    return argv, link, [Path(x) for x in objects if x != main_object]


def check_disassembly(text):
    match = re.search(r'^[0-9a-f]+ <main>:\n(.*?)(?=^[0-9a-f]+ <|\Z)', text, re.M | re.S)
    s.require(match is not None, 'Missing main disassembly')
    lines = match[1].splitlines()
    cycles = [i for i, line in enumerate(lines) if re.search(r'\brdcycle\b', line)]
    calls = [i for i, line in enumerate(lines) if '<akv_attention_execute_v2_native>' in line]
    s.require(len(cycles) == 2 and len(calls) == 1 and cycles[0] < calls[0] < cycles[1],
              'Timing does not bracket the actual native call')
    end = cycles[1]
    s.require(end >= 2 and re.search(r'\bvmv\.x\.s\s+\w+,v12\b', lines[end-2]) and
              re.search(r'\bfence\b', lines[end-1]) and
              re.search(r'\bfrcsr\b', lines[end+1]) and 'vcsr' in lines[end+2],
              'Drain/fence/end/CSR instruction order differs')


def checked_build(directory):
    report = s.read_json(directory/'build.json')
    s.require(report.get('schema') == SCHEMA and report.get('state') == 'BUILT_NOT_EXECUTED' and
              report.get('execution') == 'NOT_RUN' and report.get('post_pins_match') is True and
              report.get('old_runtime_objects_reused') is True and
              report.get('expected_commands') == 3680 and report.get('expected_calls') == 12,
              'Not the timed successor build contract')
    receipt = directory/'source-pins.json'
    s.require(s.digest(receipt) == report['source_pins_sha256'], 'Timed build receipt drift')
    pins = s.read_json(receipt)
    s.merge_pins(pins, report['artifact_sha256'])
    base, image, old_pins = original_run.checked_build(Path(report['original_build']), 'decode')
    s.require(report['accepted_image_pins'] == image and report['simv'] == base['simv'], 'Original image changed')
    s.require(all(pins.get(p) == h for p, h in old_pins.items()), 'Missing original build provenance')
    s.require((directory/'main.c').read_text() == render(SOURCE.read_text()), 'Rendered main drift')
    compile_argv, link, reused = recipe(s.read_json(Path(report['original_build'])/'commands.json'), directory)
    s.require(report['reused_objects'] == s.hashes(reused), 'Reused object identities differ')
    invocations = s.read_json(directory/'commands.json')
    s.require([r['argv'] for r in invocations if '-c' in r['argv']] == [compile_argv] and
              [r['argv'] for r in invocations if '-nostdlib' in r['argv']] == [link], 'Successor recipe drift')
    s.require(report['elf'] == str(directory/'timed_decode.elf') and
              pins.get(report['elf']) == report['elf_sha256'] == s.digest(Path(report['elf'])), 'Timed ELF drift')
    check_disassembly((directory/'disassembly.log').read_text())
    s.merge_pins(pins, s.hashes([directory/'build.json', receipt]))
    s.verify_pins(pins)
    return report, image, pins


def build(args):
    base, out = args.base.resolve(strict=True), args.output.resolve()
    s.require(not out.is_relative_to(base), 'Use fresh independent output')
    out.mkdir(parents=True, exist_ok=False)
    invocations = []

    def invoke(argv, label):
        argv = list(map(str, argv))
        invocations.append(dict(argv=argv, cwd=str(out)))
        s.atomic_json(out/'commands.json', invocations)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        return (out/(label+'.log')).read_text()

    try:
        old, image, pins = original_run.checked_build(base, 'decode')
        argv, link, reused = recipe(s.read_json(base/'commands.json'), out)
        s.require(all(pins.get(str(p)) == s.digest(p) for p in reused), 'Unpinned reused object')
        s.require(pins.get(str(SOURCE)) == SOURCE_SHA, 'Original main provenance missing')
        spec = importlib.util.spec_from_file_location('timed_decode_elf_tools', ELF_TOOLS)
        elf_tools = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = elf_tools
        spec.loader.exec_module(elf_tools)
        cc = Path(argv[0])
        objdump = cc.with_name('riscv64-unknown-elf-objdump')
        s.merge_pins(pins, s.hashes([cc.resolve(strict=True), objdump.resolve(strict=True), *own_files()]))
        s.verify_pins(pins)
        (out/'main.c').write_text(render(SOURCE.read_text()))
        s.merge_pins(pins, s.hashes([out/'main.c']))
        flags = argv[1:argv.index('-c')]
        for name in ('cc1', 'as', 'ld'):
            path = Path(invoke([cc, *flags, '-print-prog-name='+name], 'tool-'+name).strip()).resolve(strict=True)
            s.merge_pins(pins, s.hashes([path]))
        for name in ('libgcc.a', 'libm.a'):
            path = Path(invoke([cc, *flags, '-print-file-name='+name], 'library-'+name).strip()).resolve(strict=True)
            s.merge_pins(pins, s.hashes([path]))
        si, oi = argv.index('-c')+1, argv.index('-o')+1
        deps = invoke([v for i, v in enumerate(argv) if i not in (si-1, oi-1, oi)] + ['-M', '-MT', 'main'], 'dependencies')
        s.merge_pins(pins, s.hashes([Path(x).resolve(strict=True) for x in
            shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1])]))
        s.verify_pins(pins)
        invoke(argv, 'compile-main')
        invoke(link, 'link')
        elf = out/'timed_decode.elf'
        check_disassembly(invoke([objdump, '-d', elf], 'disassembly'))
        sections = elf_tools.alloc_sections(elf)
        s.require(sections and min(x['address'] for x in sections) >= 0x80000000 and
                  max(x['address']+x['bytes'] for x in sections) < 0x81000000-65536, 'ELF bounds')
        s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json', pins)
        s.atomic_json(out/'build.json', dict(schema=SCHEMA, state='BUILT_NOT_EXECUTED', execution='NOT_RUN',
            elf=str(elf), elf_sha256=s.digest(elf), simv=old['simv'], accepted_image_pins=image,
            source_pins_sha256=s.digest(out/'source-pins.json'), post_pins_match=True,
            artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()),
            original_build=str(base), old_runtime_objects_reused=True, reused_objects=s.hashes(reused),
            fresh_main_and_link=True, expected_commands=3680, expected_calls=12, sections=sections,
            canonical_modified=False, scope='Full native Decode calls; original real data and numerical checks unchanged'))
        print('BUILT_NOT_EXECUTED '+str(elf))
    except BaseException as exc:
        s.atomic_json(out/'build.json', dict(state='FAIL', execution='NOT_RUN', error=repr(exc)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args())
