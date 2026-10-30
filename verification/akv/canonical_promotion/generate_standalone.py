#!/usr/bin/env python3
"""Generate test-only compositions for future canonical Makefiles; no EDA calls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parent / 'shared_reader_integration'
sys.path.insert(0, str(INTEGRATION))
import compose_canonical_standalone as composer


def sha(path):
    return composer.digest(path)


def source_contract(root, kind):
    if kind not in ('qbs', 'akv'):
        raise ValueError('Known engine required')
    engine = root / f'hardware/src/vlsu/{kind}/{kind}_engine.sv'
    text = engine.read_text()
    for pattern in (r'parameter\s+type\s+reader_req_t', r'parameter\s+type\s+reader_rsp_t',
                    r'output\s+reader_req_t\s+reader_req_o', r'input\s+reader_rsp_t\s+reader_rsp_i'):
        if not re.search(pattern, text):
            raise ValueError('Need promoted external-reader engine, not old canonical ports')
    if re.search(r'\bqbs_read_engine\s*#', text):
        raise ValueError('Private reader in selected engine')
    paths = [engine, root / 'hardware/src/vlsu/qbs/qbs_read_engine.sv',
             root / 'hardware/src/vlsu/qbs_akv_shared_reader.sv',
             root / 'hardware/include/shared_reader_types.svh']
    if kind == 'akv':
        if not re.search(r'\bakv_unified_context\s+i_unified_context\s*\(', text):
            raise ValueError('Need unified AKV context')
        paths += [root / ('hardware/src/vlsu/akv/' + name + '.sv') for name in
                  ('akv_unified_context', 'akv_q_store', 'akv_legacy_repacker', 'akv_v2_context')]
    for path in paths:
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('Missing/out-of-root canonical dependency: ' + str(path))
    return paths


def generate(root, kind, bench, output):
    root, bench = root.resolve(strict=True), bench.resolve(strict=True)
    output = output.resolve()
    paths = source_contract(root, kind)
    wrapper = composer.compose(kind)
    adapted = composer.adapt_tb(bench.read_text(), kind)
    entry, _ = composer.contract(kind)
    if hashlib.sha256(wrapper.encode()).hexdigest() != entry['origin_wrapper_sha256']:
        raise ValueError('Composition differs from accepted original-suite wrapper')
    paths += [bench, Path(__file__).resolve(), Path(composer.__file__).resolve(),
              Path(composer.original.__file__).resolve(), composer.CONTRACTS / 'manifest.json',
              composer.CONTRACTS / entry['file'], Path(sys.executable).resolve()]
    if any(p.is_relative_to(output) for p in paths):
        raise ValueError('Generated directory overlaps inputs')
    pins = {str(path): sha(path) for path in paths}
    names = {'composed_engine.sv', 'original_suite.sv', 'generation.json'}
    if output.exists() and (not output.is_dir() or
            any(p.name not in names or p.is_symlink() or not p.is_file() for p in output.iterdir())):
        raise ValueError('Use a dedicated generation directory without unrelated files/symlinks')
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name, text in (('composed_engine.sv', wrapper), ('original_suite.sv', adapted)):
        path = output / name
        temporary = path.with_suffix('.tmp')
        temporary.write_text(text)
        temporary.replace(path)
        artifacts[str(path)] = sha(path)
    if any(sha(Path(path)) != expected for path, expected in pins.items()):
        raise ValueError('Generation input drift')
    report = dict(state='COMPOSITION_GENERATED_NOT_COMPILED', kind=kind, source_root=str(root),
                  original_tb=str(bench), input_pins=pins, artifact_pins=artifacts,
                  original_tb_assertions_preserved=True, original_wrapper_sha256=entry['origin_wrapper_sha256'],
                  full_compilation_inventory=False, performance_measured=False, production_promoted=False)
    path = output / 'generation.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--kind', choices=('qbs', 'akv'), required=True)
    parser.add_argument('--tb', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.source_root, args.kind, args.tb, args.output)
