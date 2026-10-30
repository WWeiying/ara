#!/usr/bin/env python3
"""Explicit build factory; no build or simulator is run on import."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render

FACTORY = HERE.parent / 'build_threeway_attention.py'
FACTORY_SHA256 = '310f2da47b3c6d261193bd705d1748a9bd67186bc30cce7b492248049c9b5221'
VARIANT = 'FAST_HEX32_PUTCHAR_STDOUT_IDENTICAL'


def load_factory(main):
    if render.digest(FACTORY.read_bytes()) != FACTORY_SHA256:
        raise ValueError('Immutable three-way build factory changed')
    name = '_akv_fast_hex_factory_' + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, FACTORY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        module.MAIN = main
        return module
    except BaseException:
        sys.modules.pop(name, None)
        raise


def reused_inputs(link, base):
    old_main = str(base / 'main.o')
    if link.count(old_main) != 1:
        raise ValueError('Ambiguous original main object')
    return [Path(arg) for arg in link if arg.endswith(('.o', '.a')) and arg != old_main]


def finish_report(factory, build_dir, report, source_pins, provenance, reused):
    s = factory.s
    s.require(report.get('state') == 'THREEWAY_ENTRY_BUILT_NOT_EXECUTED' and
              report.get('execution') == 'NOT_RUN', 'Factory did not complete a fresh build')
    pins = s.read_json(build_dir / 'source-pins.json')
    s.merge_pins(pins, source_pins)
    s.require(all(pins.get(path) == sha for path, sha in reused.items()),
              'Reused link input missing from source pins')
    s.verify_pins(pins)
    s.atomic_json(build_dir / 'source-pins.json', pins)
    updated = dict(report)
    updated.update(producer=str(Path(__file__).resolve()), source_variant=VARIANT,
                   source_provenance=provenance, build_factory=str(FACTORY),
                   build_factory_sha256=FACTORY_SHA256, reused_link_inputs=reused,
                   rebuilt_link_inputs=[str(build_dir / 'main.o')],
                   io_only_successor=True, stdout_protocol_unchanged=True,
                   performance_claim='NOT_MEASURED; no under-three-hour guarantee',
                   source_pins_sha256=s.digest(build_dir / 'source-pins.json'),
                   artifact_sha256=s.hashes(p for p in build_dir.iterdir()
                                           if p.is_file() and p.name != 'build.json'))
    s.atomic_json(build_dir / 'build.json', updated)
    return updated


def build(base, output):
    base, output = base.resolve(strict=True), output.resolve()
    if output.exists() or output.is_relative_to(base) or base.is_relative_to(output):
        raise ValueError('Require a fresh output independent of the sealed base')
    original = render.ORIGINAL.read_bytes()
    generated = render.render(original)
    proof = render.provenance(original, generated)
    source_dir, build_dir = output / 'source', output / 'build'
    main = source_dir / 'attention_threeway_fast_hex.c'
    factory = load_factory(main)
    s = factory.s
    own = [HERE / name for name in ('build.py', 'render.py', 'hex32.h',
                                    'test_fast_hex.py', 'test_hex.c', 'README.md')]
    before = s.hashes([*own, FACTORY, render.ORIGINAL])
    s.require(before[str(render.ORIGINAL)] == render.ORIGINAL_SHA256 and
              before[str(FACTORY)] == FACTORY_SHA256, 'Original source changed during preparation')
    # Admission and reused object inventory use the unchanged factory policy.
    _report, inherited = factory.checked_build(base)
    _cc, link = factory.templates(s.read_json(base / 'commands.json'), base)
    reused = s.hashes(reused_inputs(link, base))
    s.require(all(inherited.get(path) == sha for path, sha in reused.items()),
              'Reused object is not covered by the sealed base')
    s.verify_pins(before)
    source_dir.mkdir(parents=True, exist_ok=False)
    main.write_bytes(generated)
    proof.update(generated_source=str(main), emitter=str(HERE / 'hex32.h'),
                 emitter_sha256=before[str(HERE / 'hex32.h')])
    proof_path = source_dir / 'render.json'
    s.atomic_json(proof_path, proof)
    s.merge_pins(before, s.hashes([main, proof_path]))
    try:
        report = factory.build(base, build_dir)
        s.verify_pins(before)
        s.require(render.inverse(main.read_bytes()) == original,
                  'Generated main changed during compilation')
        return finish_report(factory, build_dir, report, before, proof, reused)
    except BaseException as exc:
        # Never leave a predecessor PASS-looking build after wrapper validation fails.
        if build_dir.is_dir():
            s.atomic_json(build_dir / 'build.json', dict(state='FAIL', execution='NOT_RUN',
                          producer=str(Path(__file__).resolve()), source_variant=VARIANT,
                          error=repr(exc)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--base', type=Path, required=True,
                        help='Accepted strided build, not a three-way ELF')
    parser.add_argument('--output', type=Path, required=True,
                        help='Fresh container; consumable build is OUTPUT/build')
    args = parser.parse_args()
    report = build(args.base, args.output)
    print(json.dumps(dict(state=report['state'], build=str(args.output.resolve() / 'build'),
                          elf=report['elf'], source_variant=report['source_variant'],
                          simulator_launched=False)))
