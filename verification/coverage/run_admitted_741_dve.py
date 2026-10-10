"""One raw DVE741 export using the existing reporter and reviewed tool environment."""
import argparse
import csv
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess

import admit_targeted_toggle741 as admission
import dve_tool_identity as tools

life, require = admission.life, admission.require
BASE = life.OUT / 'targeted-toggle-offline-admitted-741-parent-20261007-01'
SEAL = 'ad53b488eb12de7c8fe1a470d72c5a36dbea5cb349383dcf9c3c8068cebfb0f1'
PRIOR = life.OUT / 'final-raw740-dve-agent-20261007-01/summary.csv'
PRIOR_SHA = '86ddb63b4be564884d9f3a3fe96fb9c6091da99fe02a5eda6b04e6f62821649a'


def system_row(path):
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 2989, 'Full raw hierarchy row count differs')
    selected = [r for r in rows if r['Name'] == 'i_system']
    require(len(selected) == 1, 'Ambiguous/missing system row')
    for metric in ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch'):
        text = selected[0][metric]
        require(text.endswith('%') and 0 <= Decimal(text[:-1]) <= 100, 'Invalid percentage')
    return selected[0]


def run(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh DVE output required')
    book = life.read_bound(BASE / 'admission-manifest.json', SEAL)
    pins = life.merge_pins(book['input_pins'], book['output_pins'])
    pins = life.merge_pins(pins, {str(BASE / 'admission-manifest.json'): SEAL,
                                str(PRIOR): PRIOR_SHA,
                                str(Path(__file__).resolve()): life.digest(Path(__file__).resolve())})
    life.check(pins)
    status = life.read_bound(BASE / 'status.json', pins[str(BASE / 'status.json')])
    require(status['coverage_admitted'] is True and status['aggregate_passed'] == 741 and
            status['exact740_prefix'] is True, 'Not admitted741')
    raw = life.read_bound(admission.RAW, admission.RAW_SHA)
    inputs = (BASE / 'combined-inputs.txt').read_text().splitlines()
    require(inputs == raw['input_ledger'] + [str(admission.VDB)] and
            len(inputs) == len(set(inputs)) == 742, '741 report input identities differ')
    script = life.ROOT / 'verification/coverage/run_dve_coverage.sh'
    require(str(script) in pins, 'Unbound existing DVE reporter')
    env = tools.controlled_environment(raw['tool_identity'], os.environ)
    env.pop('DVE', None)
    env['PATH'] = str(Path(raw['tool_identity']['roles']['launcher']).parent) + ':/usr/bin:/bin'
    env.update(DVE_WAIVERS='off', DVE_COVERAGE_TIMEOUT='900', PYTHONDONTWRITEBYTECODE='1')
    command = ['/bin/bash', str(script), str(out), '--inputs-file', str(BASE / 'combined-inputs.txt')]
    subprocess.run(command, cwd=life.ROOT, env=env, check=True, timeout=960)
    life.check(pins)
    prior, current = system_row(PRIOR), system_row(out / 'summary.csv')
    for metric in ('Line', 'FSM', 'Condition', 'Branch'):
        require(current[metric] == prior[metric], 'Unexpected non-Toggle score change: ' + metric)
    require(Decimal(current['Toggle'][:-1]) >= Decimal(prior['Toggle'][:-1]), 'Toggle score decreased')
    life.save(out / 'report-result.json', dict(status='RAW741_DVE_REPORT_VERIFIED', tests=741,
        admission_seal=SEAL, raw740=prior, raw741=current,
        percentage_point_delta={k: str(Decimal(current[k][:-1]) - Decimal(prior[k][:-1]))
                                for k in ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch')},
        summary_sha256=life.digest(out / 'summary.csv'), waiver_mode='off',
        simulations_started=False, new_RTL_signoff=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--parent-authorized', action='store_true', required=True)
    args = parser.parse_args()
    run(args.output.absolute())
