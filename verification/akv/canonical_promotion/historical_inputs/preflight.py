#!/usr/bin/env python3
"""Host-only source consumption and actual promotion-patch isolation proof."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import archive as a

PLAN = 'verification/akv/canonical_promotion/coherent_package/prepared-01/plan.json'
PLAN_SHA = 'cfda0a82d1c909fb2a0ab3b90278ff339060c96ed4ac81e2f6c69118a3257cba'
SOFTWARE = 'verification/akv/paired_heads/ordinary_resource/historical_sources.py'
HISTORY = 'verification/out/ordinary-rvv-unified-20261025-01/historical-source'


def merge(pins, extra):
    for name, sha in extra.items():
        a.require(name not in pins or pins[name] == sha, 'Pin collision: ' + name)
        pins[name] = sha


def software_history(root):
    spec = importlib.util.spec_from_file_location('existing_ordinary_history', root / SOFTWARE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tools = SimpleNamespace(require=a.require, read_json=a.read_json, verify_pins=a.verify_pins,
                            merge_pins=merge, hashes=lambda ps: {str(p): a.digest(p) for p in ps})
    return module.HistoricalSources(root, root / HISTORY, tools)


def run(directory, reviewed, output):
    archive = a.Archive(directory, reviewed)
    root = archive.root
    output = output.resolve()
    a.require(output.is_relative_to(a.HERE) and output != a.HERE and not output.exists(),
              'Use a fresh owned output')
    plan_path = root / PLAN
    a.require(a.digest(plan_path) == PLAN_SHA, 'Promotion plan differs')
    plan = a.read_json(plan_path)
    patch = plan_path.parent / 'coherent.patch'
    a.require(a.digest(patch) == plan['patch_sha256'], 'Promotion patch differs')
    history = software_history(root)
    external = {str(plan_path): PLAN_SHA, str(patch): plan['patch_sha256'],
                str(root / SOFTWARE): a.digest(root / SOFTWARE)}
    merge(external, history.checked_pins())
    own = {str(p): a.digest(p) for p in a.HERE.iterdir() if p.suffix in ('.py', '.md')}
    # The two software bindings are applied by the unchanged, separate helper.
    # They are never added to the five-entry canonical mapping allowlist.
    consumed = {}
    counts = {}
    for receipt in a.RECEIPTS:
        pins = history.translate(archive.mapped_pins(archive.pins(receipt)))
        merge(consumed, pins)
        counts[receipt] = len(pins)
    a.verify_pins(consumed)
    output.mkdir()
    tree = output / 'after-tree'
    tree.mkdir()
    before = {}
    for row in plan['files']:
        source = root / row['target']
        if row['before_sha256'] is not None:
            a.require(a.digest(source) == row['before_sha256'], 'Not the original canonical tree')
            before[str(source)] = row['before_sha256']
            dest = tree / row['target']
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
            dest.chmod(int(row['mode'], 8))
    for name in ['Bender.lock', *('hardware/include/' + n for n in archive.report['include_files'])]:
        dest = tree / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((archive.payload / name).read_bytes())
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(output))
    commands = []
    for check in (True, False):
        cmd = ['git', '-C', str(tree), 'apply', *(['--check'] if check else []), str(patch)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=env, timeout=30, check=False)
        commands.append(dict(argv=cmd, exit=result.returncode, output=result.stdout.decode()))
        a.require(result.returncode == 0, 'Isolated git apply failed: ' + result.stdout.decode())
    after = {row['target']: a.digest(tree / row['target']) for row in plan['files']}
    a.require(after == {row['target']: row['after_sha256'] for row in plan['files']}, 'After-tree bytes differ')
    expected_additions = {'admission_assertions.svh', 'shared_reader_types.svh', 'vlsu_shared_reader.svh'}
    live_include = a.files_under(tree / 'hardware/include')
    a.require(set(live_include) - set(archive.report['include_files']) == expected_additions,
              'Wrong promoted header additions')
    scoped = {str(root / p): sha for p, sha in a.CHANGED.items()}
    scoped.update({str(root / 'Bender.lock'): archive.report['payload']['Bender.lock']})
    scoped.update({str(root / 'hardware/include' / p): sha for p, sha in archive.report['include_files'].items()})
    # Simulate a changed live root. Only the explicit five map to the archive;
    # unchanged lock/include pins must still match the new-root counterparts.
    mapped = archive.mapped_pins(scoped)
    model = {str(tree / Path(p).relative_to(root)) if p in scoped else p: sha for p, sha in mapped.items()}
    a.verify_pins(model)
    historical = archive.historical_include()
    a.require(len(historical) == 7 and all(Path(p).is_relative_to(archive.payload) for p in historical),
              'Historical scan escaped archive')
    a.require(all(a.digest(tree / p) != sha for p, sha in a.CHANGED.items()), 'After-tree did not exercise all five changes')
    a.verify_pins(consumed)
    a.verify_pins(before)
    a.verify_pins(external)
    a.verify_pins(own)
    a.Archive(directory, reviewed)
    report = dict(state='HOST_HISTORY_PREFLIGHT_PASS_NOT_PROMOTED', archive_sha256=reviewed,
                  receipt_pin_counts=counts, unique_consumed_pins=len(consumed), changed_paths=list(a.CHANGED),
                  historical_include_files=7, promoted_include_additions=sorted(expected_additions),
                  after_tree=after, commands=commands, external_pins=external, helper_pins=own,
                  consumed_pins=consumed, canonical_before_pins=before, post_pins_match=True,
                  old_workers_modified=False, compiler_invoked=False, simulator_invoked=False,
                  scope='All six original pin sets verified with exact separate software history; '
                        'isolated actual after-tree consumption exercises five changed files and unchanged lock/headers; '
                        'not a complete historical compilegraph rebase, image acceptance or runtime PASS')
    a.save(output / 'result.json', report)
    return a.digest(output / 'result.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--reviewed-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(run(args.archive, args.reviewed_sha256, args.output))
