#!/usr/bin/env python3
"""Separate admission for an option-order-only rejected canonical compilation."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
from audit_filelist import audit

spec = importlib.util.spec_from_file_location('retire_canonical_builder', ROOT /
    'verification/akv/canonical_promotion/canonical_soc/build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def admit(directory):
    b = builder
    directory = directory.resolve(strict=True)
    prior = b.read(directory/'result.json')
    b.require(prior.get('state') == 'FAIL' and prior.get('compile_exit_code') == 0 and
              prior.get('error') == "ValueError('Actual canonical Bender graph/order/defines differs')",
              'Only the specific post-compile ordering rejection can be reviewed')
    b.require(b.read(directory/'status.json').get('child_pid') is None, 'Build still active')
    b.guard()
    c = b.load_common()
    pins = b.read(directory/'source-pins.json')
    b.verify(pins)
    tools = b.tool_paths()
    # auxiliary_inputs includes imported modules. These two review-only helpers
    # did not participate in compilation; pin them in the new receipt instead.
    review_helpers = {str(Path(__file__).resolve()), str(HERE/'audit_filelist.py')}
    auxiliary = {p: h for p, h in b.auxiliary_inputs(tools).items()
                 if p not in review_helpers}
    b.require(auxiliary.items() <= pins.items(), 'Build helper/tool drift')
    expected = directory/'expected-sources.f'
    filelist = directory/'hardware-build/vcs/bender_script_default'
    b.check_graph(expected.read_text(), b.expected_graph(b.OLD_LIST.read_text()), c.SOC_REPEAT_HASHES)
    ordering = audit(expected, filelist)
    b.require(ordering['state'] == 'ORDER_AUDIT_PASS', 'Unresolved include/option difference')
    planned = b.read(directory/'planned-command.json')
    b.require(b.read(directory/'make.command.json')['argv'] == planned, 'Compile command changed')
    sim = directory/'sim'
    config = b.check_config(sim/'simulator.conf')
    extras = [directory/'hardware-build/work-dpi/elfloader.o', *b.UVM]
    manifest = b.read(sim/'vcs_source_manifest.json')
    b.require(manifest.get('schema_version') == 1 and manifest.get('repo_root') == str(ROOT)
              and manifest.get('filelist') == str(filelist) and
              manifest.get('extra_sources') == list(map(str, extras)), 'Manifest identity')
    actual = c.latency.tools.collect(filelist, ROOT, extras)
    b.require(manifest['files'] == actual, 'Current source/compiled manifest drift')
    for row in actual:
        if row['path'] not in (str(filelist), str(extras[0])):
            b.require(pins.get(row['path']) == row['sha256'], 'Missing pre-build source pin')
    lint = c.check_soc_compile((sim/'comp.vcs.log').read_text(), 0,
                               b.expected_vcs(directory, tools['vcs']), ROOT)
    image = c.s.hashes(c.s.image_files(sim/'simv'))
    b.require(all(str(sim/name) in image for name in
                  ('simv', 'simulator.conf', 'vcs_source_manifest.json')), 'Incomplete image')
    artifacts = c.s.hashes([directory/name for name in ('result.json', 'status.json',
        'source-pins.json', 'make.command.json', 'planned-command.json', 'make.log')])
    artifacts.update(c.s.hashes([filelist, expected, *extras[:1],
        directory/'hardware-build/work-dpi/ara_dpi.so', sim/'comp.vcs.log',
        Path(__file__), HERE/'audit_filelist.py']))
    artifacts.update(image)
    b.verify(pins)
    return dict(state='ORDER_REVIEWED_SOC_BUILT_NOT_EXECUTED', original_state='FAIL',
        source_root=str(ROOT), source_pins_sha256=b.digest(directory/'source-pins.json'),
        post_pins_match=True, config=config, lint=lint, image_pins=image,
        artifact_pins=artifacts, ordering=ordering, simv=str(sim/'simv'),
        execution='NOT_RUN', performance_measured=False, simulations_launched=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = admit(args.build)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(result['state'])
