#!/usr/bin/env python3
"""Require identical frozen HDL, libraries and constraints for the area pair."""
import argparse
import json
from pathlib import Path

import area_pair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('compact', type=Path)
    parser.add_argument('arithmetic', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    flow = area_pair.flow
    flow.PROFILES = area_pair.PROFILES
    runs = [p.resolve() for p in (args.reference, args.compact, args.arithmetic)]
    manifests, sources, source_orders, scripts, configs = [], [], [], [], []
    for run in runs:
        flow.check(run)
        manifest = json.loads((run / 'manifest.json').read_text())
        normalize = lambda path: str(path).replace(str(run), '<RUN>')
        source = {}
        for record in manifest['frozen_files']:
            if 'original' in record:
                key = normalize(record['original'])
                assert key not in source, 'Duplicate input: ' + key
                source[key] = record['sha256']
        assert source, 'Missing HDL/header closure'
        _, includes, ordered = flow.entries((run / 'backend/flist/ara_soc_dc.f').read_text())
        source_orders.append(([normalize(p) for p in includes],
                              [normalize(p) for p in ordered]))
        scripts.append({str(p.relative_to(run / flow.FLOW)): flow.sha(p)
                        for name in ('global_scripts', 'local_scripts')
                        for p in (run / flow.FLOW / name).rglob('*') if p.is_file()})
        config = (run / flow.FLOW / 'inputs/run_config.tcl').read_text().splitlines()
        assert config[0] == 'set RCE_PROFILE ' + manifest['profile']
        configs.append(config[1:])
        manifests.append(manifest)
        sources.append(source)
    assert sources[0] == sources[1] == sources[2], 'Different HDL/header content'
    assert source_orders[0] == source_orders[1] == source_orders[2], 'Different HDL order/includes'
    assert scripts[0] == scripts[1] == scripts[2], 'Different backend scripts/constraints'
    assert configs[0] == configs[1] == configs[2], 'Different run configuration'
    for field in ('period_ns', 'setup_uncertainty_ns', 'cores', 'scope',
                  'libraries', 'container', 'dc_home'):
        assert manifests[0][field] == manifests[1][field] == manifests[2][field], field
    before, compact, arithmetic = [m['defines'] for m in manifests]
    assert compact == dict(before, **area_pair.AREA_FLAGS)
    assert arithmetic == dict(compact, ARA_RED_ARITHMETIC_ONLY_FORWARD='1')
    profiles = ['area_pair_reference', 'area_pair_compact', 'area_pair_arithmetic']
    assert [m['profile'] for m in manifests] == profiles
    result = {
        'complete_input_audit': True,
        'scope': 'Frozen inputs only; no synthesis/performance acceptance',
        'source_and_header_files': len(sources[0]),
        'ordered_hdl_files': len(source_orders[0][1]),
        'area_flags': area_pair.AREA_FLAGS,
        'arithmetic_extra_flag': 'ARA_RED_ARITHMETIC_ONLY_FORWARD=1',
        'runs': [{'directory': str(run), 'manifest_sha256': flow.sha(run / 'manifest.json'),
                  'status': json.loads((run / 'status.json').read_text())}
                 for run in runs],
    }
    flow.write_json(args.out, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
