#!/usr/bin/env python3
"""Audit matched integrated inputs for the static-state/shared-ADD refinement."""
import argparse
import json
from pathlib import Path
import area_pair


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference', type=Path)
    p.add_argument('candidate', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--direct-read', action='store_true', help='Audit timing profile versus direct-bin-read candidate')
    a = p.parse_args()
    flow = area_pair.flow
    flow.PROFILES = area_pair.PROFILES
    manifests, sources, orders, scripts, configs = [], [], [], [], []
    runs = [a.reference.resolve(), a.candidate.resolve()]
    for run in runs:
        flow.check(run)
        m = json.loads((run/'manifest.json').read_text())
        norm = lambda x: str(x).replace(str(run), '<RUN>')
        sources.append({norm(x['original']): x['sha256'] for x in m['frozen_files'] if 'original' in x})
        _, includes, ordered = flow.entries((run/'backend/flist/ara_soc_dc.f').read_text())
        orders.append(([norm(x) for x in includes], [norm(x) for x in ordered]))
        scripts.append({str(f.relative_to(run/flow.FLOW)): flow.sha(f)
                        for d in ('global_scripts', 'local_scripts')
                        for f in (run/flow.FLOW/d).rglob('*') if f.is_file()})
        cfg = (run/flow.FLOW/'inputs/run_config.tcl').read_text().splitlines()
        assert cfg[0] == 'set RCE_PROFILE '+m['profile']
        configs.append(cfg[1:])
        manifests.append(m)
    assert sources[0] and sources[0] == sources[1], 'HDL/header mismatch'
    assert orders[0] == orders[1], 'File order/include mismatch'
    assert scripts[0] == scripts[1], 'Backend mismatch'
    assert configs[0] == configs[1], 'Run constraints mismatch'
    for key in ('period_ns', 'setup_uncertainty_ns', 'cores', 'scope', 'libraries', 'container', 'dc_home'):
        assert manifests[0][key] == manifests[1][key], key
    profiles = ['area_pair_timing', 'area_pair_direct_read'] if a.direct_read else ['area_pair_arithmetic', 'area_pair_timing']
    changes = {'ARA_RED_EXACT_DIRECT_BIN_READ': '1'} if a.direct_read else area_pair.TIMING_AREA_FLAGS
    assert [m['profile'] for m in manifests] == profiles
    assert manifests[1]['defines'] == dict(manifests[0]['defines'], **changes)
    result = {'complete_input_audit': True, 'source_and_header_files': len(sources[0]),
              'ordered_hdl_files': len(orders[0][1]), 'only_define_changes': changes,
              'runs': [{'directory': str(r), 'manifest_sha256': flow.sha(r/'manifest.json')} for r in runs],
              'scope': 'Identical frozen RTL/libs/constraints; does not establish synthesis results or timing closure'}
    with a.out.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
