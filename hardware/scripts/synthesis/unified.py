#!/usr/bin/env python3
"""Single production reduction configuration. Only `run` launches DC."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import area_pair
import flow


CONFIG = flow.ROOT / 'config/reduction.json'
SPEC = json.loads(CONFIG.read_text())
# Keep the already validated report and topology checks. Historical profiles
# remain readable for reproducibility, but are not exposed by this entry.
assert SPEC['defines'] == area_pair.PROFILES['area_pair_timing']
flow.PROFILES = {SPEC['name']: SPEC['defines']}
original_template = area_pair.bounded_report_template


def unified_template(text):
    text = original_template(text)
    old = '*i_shared_ordered_adder*gen_unit*i_add'
    assert text.count(old) == 1
    text = text.replace(old, '*i_shared_ordered_adder*gen_unit*i_format_shared_add')
    old = 'set expected_slices [expr {$RCE_PROFILE in {area_pair_timing area_pair_direct_read} ? 3 : 1}]'
    assert text.count(old) == 1
    text = text.replace(old, 'set expected_slices 1')
    marker = '            finalizer fp32_exact_reduction_finalize*'
    assert text.count(marker) == 1
    return text.replace(marker, marker + '\n            exact_seed fp32_exact_reduction_seed*')



def prepare(args, out):
    area_pair.bounded_report_template = unified_template
    area_pair.PROFILES = flow.PROFILES
    area_pair.POLICY = {
        'scope': 'Single production reduction configuration',
        'profiles': flow.PROFILES,
        'selected_evidence': SPEC['selected_evidence'],
        'limits': 'Shared scalar arithmetic integrated; full PPA pending; historical timing unclosed.'
    }
    area_pair.prepare(args, out)
    extra = []
    for source in (CONFIG, flow.ROOT / 'config/reduction.mk', Path(__file__)):
        target = out / 'provenance' / source.name
        shutil.copy2(source, target)
        extra.append({'snapshot': str(target.relative_to(out)), 'sha256': flow.sha(target)})
    manifest = json.loads((out / 'manifest.json').read_text())
    manifest['frozen_files'].extend(extra)
    manifest['unified_configuration'] = SPEC
    flow.write_json(out / 'manifest.json', manifest)
    flow.check(out, environment=True)


if __name__ == '__main__':
    flow.prepare = prepare
    if '--profile' not in sys.argv and not any(a.startswith('--profile=') for a in sys.argv):
        sys.argv.extend(['--profile', SPEC['name']])
    try:
        flow.main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
