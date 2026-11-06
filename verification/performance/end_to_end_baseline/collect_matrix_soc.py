#!/usr/bin/env python3
"""Audit completed matrix SoC builds without rewriting failed worker evidence."""
import argparse
import importlib.util
import json
from pathlib import Path

from audit import digest, require, verify_pins
import build_matrix_soc as b


def check_graph(planned, actual, reference, wide):
    # Make appends one empty line after Bender. Admit only that exact difference.
    require(actual == planned + b'\n', 'Not the proven single trailing blank line')
    require([s.strip() for s in planned.decode().splitlines() if s.strip()] ==
            b.expected_graph(reference, wide), 'Source/order/macro difference')
    return dict(only_one_appended_empty_line=True, meaningful_graph_equal=True)


def audit_build(run):
    run = run.resolve(strict=True)
    require(run.is_relative_to(b.VERIFY/'verification/out'), 'Wrong build root')
    recorded = json.loads((run/'result.json').read_text())
    require(recorded['state'] == 'FAIL' and recorded['error'] ==
            "ValueError('Rendered graph changed at compile')" and
            recorded['simulations_launched'] == 0 and
            recorded['source_root'] == str(b.VERIFY), 'Different failure or build')
    wide = recorded['wide']; require(type(wide) is int and wide in (0, 1), 'Width')
    pins = json.loads((run/'source-pins.json').read_text())
    require(pins.get(str(Path(b.__file__).resolve())) == digest(b.__file__), 'Builder identity')
    verify_pins(pins)
    require(digest(b.BASE/'result.json') == b.BASE_SHA, 'Baseline changed')
    baseline = json.loads((b.BASE/'result.json').read_text())
    graph = run/'hardware-build/vcs/bender_script_default'
    difference = check_graph((run/'planned.f').read_bytes(), graph.read_bytes(),
                            (b.BASE/'expected-sources.f').read_text(), wide)
    commands = json.loads((run/'commands.json').read_text())
    require([r['label'] for r in commands] == ['dry-run', 'render-graph', 'compile'], 'Recipe order')
    command = commands[-1]['argv']
    require(commands[0]['argv'] == [command[0], '-n', *command[1:]], 'Dry/actual command mismatch')
    expected = list(json.loads((b.BASE/'make.command.json').read_text())['argv'])
    for i, word in enumerate(expected):
        if word.startswith('buildpath='): expected[i] = 'buildpath='+str(run/'hardware-build')
        elif word.startswith('sim_dir='): expected[i] = 'sim_dir='+str(run/'sim')
    expected.append('qbs_matrix_dot='+str(wide))
    require(command == expected, 'Actual make command differs from approved baseline')
    approval = json.loads((run/'approval.json').read_text())
    require(set(approval['source_hashes']) == {str(b.VERIFY/p) for p in (*b.CORE, *b.GLUE)},
            'Wrong seven-file approval')
    require(all(pins.get(p) == sha for p, sha in approval['source_hashes'].items()), 'Approval pins')
    old = json.loads((b.BASE/'sim/vcs_source_manifest.json').read_text())
    for row in old['files']:
        require(digest(row['path']) == approval['source_hashes'].get(row['path'], row['sha256']),
                'Unrelated baseline source drift: '+row['path'])
    sim = run/'sim'
    config = b.check_config(sim/'simulator.conf', baseline['config'], wide)
    manifest = json.loads((sim/'vcs_source_manifest.json').read_text())
    uvm = [Path(s) for s in next(w for w in command if w.startswith('verify_extra_sources=')).split('=', 1)[1].split()]
    extras = [run/'hardware-build/work-dpi/elfloader.o', *uvm]
    require(manifest['repo_root'] == str(b.VERIFY) and manifest['filelist'] == str(graph) and
            manifest['extra_sources'] == list(map(str, extras)) and
            manifest['files'] == b.collect(graph, b.VERIFY, extras), 'Compiled inventory mismatch')
    for row in manifest['files']:
        require(row['path'] in (str(graph), str(extras[0])) or pins.get(row['path']) == row['sha256'],
                'Unapproved compile input: '+row['path'])
    spec = importlib.util.spec_from_file_location('matrix_compile_readonly_audit',
        b.VERIFY/'verification/akv/canonical_promotion/canonical_soc/build.py')
    base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
    compiler = base.load_common()
    lint = compiler.check_soc_compile((sim/'comp.vcs.log').read_text(), 0,
                                     base.expected_vcs(run, Path(b.compiler_tool('vcs'))), b.VERIFY)
    require((run/'compile.log').read_text().rstrip().endswith(
        json.dumps(dict(changed=[], file_count=len(manifest['files']), status='PASS'))),
        'Missing Make source-manifest completion')
    image = compiler.s.hashes(compiler.s.image_files(sim/'simv'))
    require(image and (sim/'simv').is_file(), 'No complete image')
    verify_pins(pins)
    artifacts = {str(p): digest(p) for p in (run/'result.json', run/'status.json',
        run/'commands.json', run/'approval.json', run/'source-pins.json', run/'compile.log',
        run/'planned.f', sim/'comp.vcs.log', sim/'simulator.conf', sim/'vcs_source_manifest.json', graph, extras[0])}
    return dict(state='MATRIX_SOC_COMPILE_REAUDITED_NOT_EXECUTED', build=str(run), wide=wide,
        original_state='FAIL', original_failure_preserved=True, graph_difference=difference,
        config=config, lint=lint, simv=str(sim/'simv'), image_pins=image,
        source_pins_sha256=digest(run/'source-pins.json'), input_count=len(pins),
        artifact_pins=artifacts, performance_measured=False, simulations_launched=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--wide', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(b.VERIFY/'verification/out'), 'Fresh output root')
    out.mkdir(parents=True, exist_ok=False)
    result = dict(state='PREPARING', performance_measured=False)
    try:
        rows = [audit_build(args.base), audit_build(args.wide)]
        require([r['wide'] for r in rows] == [0, 1], 'Wrong pair order')
        require(rows[0]['config'] == dict(rows[1]['config'], qbs_matrix_dot='0'), 'Nonpaired configuration')
        pair = [json.loads((Path(r['build'])/'source-pins.json').read_text()) for r in rows]
        # Planned file paths and hashes are intentionally distinct; every shared input is identical.
        for pins, row in zip(pair, rows):
            pins.pop(str(Path(row['build'])/'planned.f'))
        require(pair[0] == pair[1], 'Nonpaired source/tool inputs')
        result.update(state='MATRIX_SOC_PAIR_REAUDITED_NOT_EXECUTED', builds=rows,
                      source_pins={str(p): digest(p) for p in (Path(__file__), Path(b.__file__))})
        for row in rows: verify_pins(row['artifact_pins']); verify_pins(row['image_pins'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally: (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__': main()
