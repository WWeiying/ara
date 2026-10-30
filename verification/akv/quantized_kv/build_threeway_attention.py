#!/usr/bin/env python3
"""Build a fresh H/S/B executable; retain the sealed strided build untouched."""
import argparse
import importlib.util
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_strided_attention as predecessor
from run_strided_attention import checked_build

s = predecessor.s
ROOT = predecessor.ROOT
MAIN = HERE / 'attention_threeway_main.c'


def templates(records, base):
    source = str(predecessor.MAIN)
    compiles = [r['argv'] for r in records if '-c' in r['argv'] and source in r['argv']]
    links = [r['argv'] for r in records if '-nostdlib' in r['argv']]
    s.require(len(compiles) == len(links) == 1, 'Ambiguous strided compile/link')
    cc, link = list(compiles[0]), list(links[0])
    s.require(cc.count(source) == 1 and cc.count('-o') == 1 and
              cc[cc.index('-o') + 1] == str(base / 'main.o') and
              link.count(str(base / 'main.o')) == 1 and link.count('-o') == 1 and
              sum(x.startswith('-Wl,-Map=') for x in link) == 1 and
              link.count('-Wl,--gc-sections') == 1 and
              [x for x in cc if x.startswith('-ffp-contract=')] == ['-ffp-contract=fast'] and
              '-fno-fast-math' in cc and '-ffast-math' not in cc and '-Ofast' not in cc and
              '-Werror' in cc and '-march=rv64gcv_zfh_zvfh' in cc and
              Path(cc[0]).name == 'riscv64-unknown-elf-gcc', 'Changed toolchain/FP/link policy')
    return cc, link


def build(base, out):
    base, out = base.resolve(strict=True), out.resolve()
    s.require(not out.is_relative_to(base) and not base.is_relative_to(out),
              'Use a separate output directory')
    report, pins = checked_build(base)
    primitives = HERE / 'threeway_strided_primitives.h'
    s.require(primitives.read_text() == predecessor.MAIN.read_text().split('int main(void) {', 1)[0],
              'Frozen strided primitives differ')
    cc, link = templates(s.read_json(base / 'commands.json'), base)
    image = report['accepted_image_pins']
    simv = Path(report['simv'])
    s.require(s.hashes(s.image_files(simv)) == image, 'Simulator identity changed')
    compiler = Path(cc[0])
    objdump = compiler.with_name('riscv64-unknown-elf-objdump')
    helper = ROOT / 'verification/akv/refill_overlap_probe/build.py'
    contract = ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'
    own = [Path(__file__), MAIN, primitives, HERE / 'shared_rvv_qk.h',
           HERE / 'test_shared_rvv_qk.py', HERE / 'test_shared_rvv_qk.c',
           HERE / 'test_threeway_attention_build.py', HERE / 'check_threeway_attention.py',
           HERE / 'test_threeway_attention_check.py', HERE / 'shared_rvv_control_plan.md',
           helper, contract, base / 'commands.json', compiler, compiler.resolve(),
           objdump, objdump.resolve(), Path(sys.executable).resolve()]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.is_file():
                own.append(path)
    s.merge_pins(pins, s.hashes(own))
    for path in (Path(x) for x in link if x.endswith(('.o', '.a'))):
        s.require(pins.get(str(path)) == s.digest(path), 'Original object drift: ' + str(path))
    s.verify_pins(pins)
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def execute(argv, name):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        s.atomic_json(out / 'commands.json', commands)
        with (out / (name + '.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        return (out / (name + '.log')).read_text()

    try:
        cc[cc.index(str(predecessor.MAIN))] = str(MAIN)
        cc[cc.index('-o') + 1] = str(out / 'main.o')
        excluded = {cc.index('-c'), cc.index('-o'), cc.index('-o') + 1}
        deps = execute([v for i, v in enumerate(cc) if i not in excluded] + ['-M', '-MT', 'object'], 'deps')
        paths = [Path(x).resolve(strict=True) for x in
                 shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1])]
        s.merge_pins(pins, s.hashes(paths))
        s.verify_pins(pins)
        execute(cc, 'compile')
        elf = out / 'threeway_attention.elf'
        link = [str(out / 'main.o') if x == str(base / 'main.o') else
                '-Wl,-Map=' + str(out / 'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
        link[link.index('-o') + 1] = str(elf)
        execute(link, 'link')
        assembly = execute([objdump, '-d', elf], 'disassembly')
        predecessor.verify_disassembly(assembly)
        s.require('<threeway_qk>:' in assembly and '<archived_strided_main>:' not in assembly,
                  'Live shared callback absent or archived entry retained')
        spec = importlib.util.spec_from_file_location('threeway_elf_sections', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sections = module.alloc_sections(elf)
        s.require(sections and min(x['address'] for x in sections) >= 0x80000000 and
                  max(x['address'] + x['bytes'] for x in sections) < 0x81000000 - 65536,
                  'ELF exceeds reserved 16MiB bounds')
        execute(['bash', contract, simv.parent, elf], 'image-contract')
        s.require(s.hashes(s.image_files(simv)) == image, 'Simulator changed during build')
        s.verify_pins(pins)
        s.atomic_json(out / 'source-pins.json', pins)
        updated = dict(report)
        updated.update(state='THREEWAY_ENTRY_BUILT_NOT_EXECUTED', execution='NOT_RUN',
                       elf=str(elf), elf_sha256=s.digest(elf), sections=sections,
                       predecessor_strided_build=str(base), trials=6,
                       trial_order=[0, 1, 2, 2, 1, 0], threeway_entry=True,
                       scope='Same-ELF head-major RVV / shared RVV / QBS shared; '
                             'actual strided K, identical V decoder and arithmetic primitives; not model timing',
                       source_pins_sha256=s.digest(out / 'source-pins.json'), post_pins_match=True,
                       artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()))
        s.atomic_json(out / 'build.json', updated)
        return updated
    except BaseException as exc:
        s.atomic_json(out / 'build.json', dict(state='FAIL', execution='NOT_RUN', error=repr(exc)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.base, args.output)
    print(result['state'], result['kind'], 'sim_launched=0')
