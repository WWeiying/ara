#!/usr/bin/env python3
"""Build the bounded owner-transfer fixture from a sealed GNU/SoC baseline."""
import argparse
import importlib.util
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent/'quantized_kv'))
from run_strided_attention import checked_build, s
from build_threeway_attention import templates
import build_strided_attention as predecessor
from wave_profile import profile, script


def build(base, out):
    base, out = base.resolve(strict=True), out.resolve()
    s.require(not out.is_relative_to(base) and not base.is_relative_to(out), 'Independent fresh build required')
    old, pins = checked_build(base)
    cc, old_link = templates(s.read_json(base/'commands.json'), base)
    image, simv = old['accepted_image_pins'], Path(old['simv'])
    s.require(s.hashes(s.image_files(simv)) == image, 'Image inventory drift')
    helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
    sources = [HERE/'main.c', HERE/'probe.S']
    objdump = Path(cc[0]).with_name('riscv64-unknown-elf-objdump')
    own = [Path(__file__), *sources, HERE/'wave_profile.py', HERE/'test_profile.py',
           HERE/'test_reader_handoff.py', helper, base/'commands.json', objdump, objdump.resolve()]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.is_file():
                own.append(path)
    s.merge_pins(pins, s.hashes(own))
    for path in (Path(x) for x in old_link if x.endswith(('.o','.a'))):
        s.require(pins.get(str(path)) == s.digest(path), 'Predecessor object drift')
    s.verify_pins(pins)
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def execute(argv, label):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        s.atomic_json(out/'commands.json', commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=180, check=True)
        return (out/(label+'.log')).read_text()

    try:
        objects = []
        for i, source in enumerate(sources):
            command = list(cc)
            command[command.index(str(predecessor.MAIN))] = str(source)
            target = out/('fixture-'+str(i)+'.o')
            command[command.index('-o')+1] = str(target)
            excluded = {command.index('-c'), command.index('-o'), command.index('-o')+1}
            deps = execute([x for index,x in enumerate(command) if index not in excluded]+['-M','-MT','object'], 'deps-'+str(i))
            paths = [Path(x).resolve(strict=True) for x in
                     shlex.split(deps.replace('\\\n',' ').split(':',1)[1])]
            s.merge_pins(pins, s.hashes(paths))
            s.verify_pins(pins)
            execute(command, 'compile-'+str(i))
            objects.append(target)
        elf = out/'reader_handoff.elf'
        link = [str(objects[0]) if x == str(base/'main.o') else
                '-Wl,-Map='+str(out/'link.map') if x.startswith('-Wl,-Map=') else x for x in old_link]
        link[link.index('-o')+1] = str(elf)
        link.insert(link.index('-Wl,--gc-sections'), str(objects[1]))
        execute(link,'link')
        assembly = execute([objdump,'-d',elf],'disassembly')
        for symbol in ('main','rh_trap_handler','rh_qbs_site','rh_qbs_then_akv','rh_akv_full',
                       'rh_akv_load','rh_akv_release','rh_rvv_copy_add'):
            s.require('<'+symbol+'>:' in assembly, 'Required live fixture symbol missing: '+symbol)
        s.require('mret' in assembly and all(op in assembly for op in
                  ('00b5045b','0005385b','00b5605b','0005345b','0000505b')), 'Instruction ABI absent')
        s.require('qbs_ref_execute' not in assembly and 'archived_main' not in assembly, 'Old/reference entry retained')
        spec = importlib.util.spec_from_file_location('handoff_sections',helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sections = module.alloc_sections(elf)
        s.require(sections and min(x['address'] for x in sections) >= 0x80000000 and
                  max(x['address']+x['bytes'] for x in sections) < 0x81000000-65536, 'ELF exceeds reserved 16MiB')
        execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf], 'image-contract')
        s.atomic_json(out/'profile.json',profile())
        (out/'probe.tcl').write_text(script(500000))
        s.require(s.hashes(s.image_files(simv)) == image, 'Simulator changed while building')
        s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json',pins)
        result = dict(state='READER_HANDOFF_BUILT_NOT_EXECUTED', execution='NOT_RUN',
                      elf=str(elf),elf_sha256=s.digest(elf),simv=str(simv),accepted_image_pins=image,
                      predecessor=str(base),qbs_commands=6,akv_commands=65,expected_traps=1,
                      fault_cause=5,expected_tval=0,source_pins_sha256=s.digest(out/'source-pins.json'),
                      sections=sections,capture_bound_ns=500000,required_signals=len(profile()['signals']),
                      sampling='Settled negedge snapshots, not pre-NBA samples',performance=False,
                      post_pins_match=True,artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()))
        s.atomic_json(out/'build.json',result)
        print(result['state'],'qbs=6 akv=65 sim_launched=0')
    except BaseException as exc:
        s.atomic_json(out/'build.json',dict(state='FAIL',execution='NOT_RUN',error=repr(exc)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    build(args.base,args.output)
