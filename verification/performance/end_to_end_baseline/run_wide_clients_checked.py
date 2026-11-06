#!/usr/bin/env python3
"""Syntax-only fixture successor; original FAIL and all DUT/checker pins stay sealed."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

import run_wide_clients as original

HERE = Path(__file__).resolve().parent
FIRST = original.OUTPUT
OUTPUT = original.VERIFY/'verification/out/e2e_wide_clients_checked_20261106_01'
FIRST_SHA = 'e399f56fcafdf48863175fd0683f1c752f39c526cf63fa3e98c68acce7b37964'
FIRST_PINS_SHA = 'af67e242aafbfe2518d81aaa441bd36766f358e47aeed237480ceb0a50a7583e'
BENCH_SHA = '8655b972891f6373012a73501c3b6094d7b88e371ac9084da055fe09f28dddb9'
OLD_HELPERS = {
    'run_wide_clients.py': 'b454cd3e82ae881f9204bf3719a4420a2f4ddc7dc3434c2d554e04ac6ae5a6d2',
    'test_wide_clients.py': '3f4cbcbe9a189466c777ffa7813c0b12d014941a21520f2da5e2f3156abe5c80',
}
OWNED = ('run_wide_clients_checked.py', 'test_wide_clients_checked.py')
OLD_TYPEDEF = 'typedef logic [0:0] id_t, user_t;'
NEW_TYPEDEF = 'typedef logic [0:0] id_t;\n  typedef logic [0:0] user_t;'
require, digest, write = original.require, original.digest, original.write


def typedef_inventory(text):
    """Find top-level typedef commas without confusing struct members/comments."""
    clean = re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"',
                   lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)
    rows = []
    for match in re.finditer(r'\btypedef\b', clean):
        depth = {'(': 0, '[': 0, '{': 0}
        pairs = {')': '(', ']': '[', '}': '{'}
        commas = []
        for end in range(match.end(), len(clean)):
            c = clean[end]
            if c in depth:
                depth[c] += 1
            elif c in pairs:
                depth[pairs[c]] -= 1
                require(depth[pairs[c]] >= 0, 'Unbalanced typedef')
            elif c == ',' and not any(depth.values()):
                commas.append(end)
            elif c == ';' and not any(depth.values()):
                rows.append(dict(line=text.count('\n', 0, match.start())+1,
                                 start=match.start(), end=end+1, commas=commas,
                                 statement=text[match.start():end+1]))
                break
        else:
            raise ValueError('Unterminated typedef')
    return rows


def repaired_fixture(data):
    require(hashlib.sha256(data).hexdigest() == BENCH_SHA, 'Wrong sealed original bench hash')
    text = data.decode('ascii')
    before = typedef_inventory(text)
    combined = [row for row in before if row['commas']]
    require(len(before) == 5 and len(combined) == 1 and
            combined[0]['statement'] == OLD_TYPEDEF and combined[0]['line'] == 11,
            'Unexpected combined typedef inventory; no compile authorized')
    row = combined[0]
    fixed = text[:row['start']] + NEW_TYPEDEF + text[row['end']:]
    after = typedef_inventory(fixed)
    require(len(after) == 6 and not any(row['commas'] for row in after),
            'Combined typedef remains after mechanical repair')
    require(fixed.replace(NEW_TYPEDEF, OLD_TYPEDEF, 1) == text,
            'Nonmechanical fixture change')
    return fixed, dict(original_sha256=BENCH_SHA,
                       generated_sha256=hashlib.sha256(fixed.encode('ascii')).hexdigest(),
                       declarations_before=5, declarations_after=6,
                       combined_declarations_before=combined, combined_declarations_after=[],
                       replacement_count=1, only_typedef_syntax_changed=True)


def workers():
    owned = {str(HERE/n) for n in OWNED}
    rows = []
    for directory in sorted((original.VERIFY/'verification/out').iterdir()):
        path = directory/'source-pins.json'
        if path.is_file():
            pins = json.loads(path.read_text())
            require(not owned.intersection(pins), 'Successor helper already sealed: '+str(path))
            rows.append(dict(path=str(path), sha256=digest(path),
                             inherited_documentation=[k for k in pins if k.lower().endswith('.md')]))
    return rows


def pin_first(c):
    c.pin(FIRST/'result.json', FIRST_SHA)
    c.pin(FIRST/'source-pins.json', FIRST_PINS_SHA)
    first = json.loads((FIRST/'result.json').read_text())
    require(first['state'] == 'WIDE_CLIENTS_COMPONENT_FAIL' and
            first['error'] == "ValueError('First compile failure; preserved, do not rerun')",
            'Unexpected first worker terminal')
    for path, expected in json.loads((FIRST/'source-pins.json').read_text()).items():
        c.pin(path, expected)
    for path, expected in first['artifacts'].items():
        c.pin(path, expected)
    commands = json.loads((FIRST/'commands.json').read_text())
    require([(r['label'], r['returncode']) for r in commands] == [('unit-tests', 0), ('compile', 255)],
            'First worker execution inventory changed')
    require(not (FIRST/'build/simv').exists() and not (FIRST/'normal.log').exists(),
            'First worker unexpectedly has simulation artifacts')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-frozen', action='store_true')
    args = parser.parse_args()
    require(args.execute_frozen, 'Explicit syntax-successor execution required')
    inventory = workers()
    OUTPUT.mkdir(exist_ok=False)
    c = original.Campaign(OUTPUT)
    result = dict(state='WIDE_CLIENTS_CHECKED_COMPONENT_FAIL', original_worker=str(FIRST),
                  original_result_sha256=FIRST_SHA, original_worker_state='WIDE_CLIENTS_COMPONENT_FAIL',
                  original_worker_relabelled=False, original_sealed_inputs_modified=False,
                  soc_integrated=False, full_engines_executed=False, real_mmu_pmp_tested=False,
                  performance_measured=False, area_measured=False, production_deployment_approved=False,
                  rtl_changed=False, historical_simulations_rerun=False,
                  actual_compiles=0, actual_simulations=0)
    try:
        write(OUTPUT/'worker-pin-inventory.json', inventory)
        pin_first(c)
        snapshot = OUTPUT/'source-snapshot'
        inputs = [(original.MAIN/name, sha, Path(name)) for name, sha in original.INPUTS.items()]
        inputs += [(HERE/name, sha, Path('tests')/name) for name, sha in OLD_HELPERS.items()]
        inputs += [(HERE/name, None, Path('tests')/name) for name in OWNED]
        for source, expected, relative in inputs:
            value = c.pin(source, expected)
            target = snapshot/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(source.read_bytes())
            c.pin(target, value)
        old_bench = FIRST/'source-snapshot/tests/qbs_wide_clients_tb.sv'
        c.pin(old_bench, BENCH_SHA)
        fixed, audit = repaired_fixture(old_bench.read_bytes())
        preserved = snapshot/'original-bench/qbs_wide_clients_tb.sv'
        preserved.parent.mkdir()
        with preserved.open('xb') as stream:
            stream.write(old_bench.read_bytes())
        c.pin(preserved, BENCH_SHA)
        generated = snapshot/'tests/qbs_wide_clients_tb.sv'
        with generated.open('x') as stream:
            stream.write(fixed)
        c.pin(generated, audit['generated_sha256'])
        write(OUTPUT/'fixture-syntax-audit.json', audit)
        with (OUTPUT/'fixture-syntax.patch').open('x') as stream:
            stream.writelines(difflib.unified_diff(old_bench.read_text().splitlines(True), fixed.splitlines(True),
                                                fromfile=str(old_bench), tofile=str(generated)))
        c.verify()
        code, text = c.run([sys.executable, '-B', snapshot/'tests/test_wide_clients_checked.py'], 'unit-tests', 60)
        require(code == 0, 'Successor host checks failed before EDA')
        vcs = shutil.which('vcs')
        require(vcs is not None, 'VCS unavailable')
        c.pin(vcs)
        c.pin(Path(vcs).resolve().parent.parent/'linux64/bin/vcs1')
        write(OUTPUT/'source-pins-precompile.json', c.pins)
        build = OUTPUT/'build'; build.mkdir()
        image = build/'simv'
        sv = [snapshot/name for name in original.INPUTS if name.endswith('.sv')]+[generated]
        code, text = c.run([vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
                           '+incdir+'+str(snapshot/'hardware/include'),
                           '+incdir+'+str(snapshot/'hardware/deps/axi/include'), *sv,
                           '-top', 'qbs_wide_clients_tb', '-Mdir='+str(build/'csrc'), '-o', image], 'compile', 180)
        require(code == 0 and not re.search(original.BAD, text), 'Successor compile failed; first evidence preserved')
        c.pin(image)
        for path in sorted(build.rglob('*.so')):
            c.pin(path)
        write(OUTPUT/'source-pins-presimulation.json', c.pins)
        code, text = c.run([image, '-no_save'], 'normal', 120)
        measured = original.check_normal(code, text)
        write(OUTPUT/'measured.json', measured)
        code, text = c.run([image, '-no_save', '+NEGATIVE_UPPER_MASK'], 'negative-upper-mask', 30)
        negative = original.check_negative(code, text, snapshot/'hardware/src/vlsu/qbs_reader_narrow_view.sv')
        c.verify()
        result.update(state='WIDE_CLIENTS_SHARED_WRAPPER_NARROW_VIEW_COMPONENT_PASS',
                      post_pins_match=True, fixture_syntax_audit=audit,
                      measured=measured['summaries'], direct_copy_vectors=128, negative=negative,
                      unchanged_original_checkers=True,
                      limitations=['Actual wrapper/reader/narrow view with synthetic clients, not full engines',
                                   'Synthetic footprint permission and translation exception only, not real MMU/PMP',
                                   'No physical SoC selection, SDK, deployment or PPA acceptance'])
    except Exception as exc:
        result.update(error=repr(exc), post_pins_match=False)
    finally:
        result['actual_compiles'] = sum(r['label'] == 'compile' and 'pid' in r for r in c.commands)
        result['actual_simulations'] = sum(r['label'] in ('normal', 'negative-upper-mask') and 'pid' in r for r in c.commands)
        write(OUTPUT/'source-pins.json', c.pins)
        write(OUTPUT/'path-identities.json', c.identities)
        write(OUTPUT/'commands.json', c.commands)
        result['source_pins_sha256'] = digest(OUTPUT/'source-pins.json')
        result['artifacts'] = {str(p):digest(p) for p in sorted(OUTPUT.rglob('*'))
                               if p.is_file() and not p.is_relative_to(OUTPUT/'build') and p.name != 'result.json'}
        write(OUTPUT/'result.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return int(result['state'] != 'WIDE_CLIENTS_SHARED_WRAPPER_NARROW_VIEW_COMPONENT_PASS')


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.exit(main())
