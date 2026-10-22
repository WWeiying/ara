"""One parent-reviewed 120s scalar misalignment run; no implicit launch."""
import argparse
import json
import re
from pathlib import Path
from types import FunctionType

import build_scalar_misalign789 as oracle
import run_csr_satp_sepc786 as prior

life, require, template = prior.life, prior.require, prior.template
converter, exact_fields, IMAGE_SHA = prior.converter, prior.exact_fields, prior.IMAGE_SHA
BASE, BASE_SHA = oracle.BASE, oracle.BASE_SHA
PRE = life.OUT / 'scalar-misalign789-preflight-agent-20261008-02'
PRE_SEAL = '01352b7d72be5c4605faa231ba78d4555ee26788edfedcebb66c326f480ab94f'
ELF = PRE / 'input.elf'
ELF_SHA = '0868507309b2aa5cc972e158c08bfbe8f41d18f64ad43ff1bccee70639276c63'
NAME, BUDGET = 'scalar_misalign789', 120
SERVICE = 'ara-scalar-misalign789-parent-20261008-01.service'
PROBE = Path(__file__).with_name('scalar_misalign789_probe.tcl').resolve()


def reference(pre):
    cs = list(oracle.shared.parse_spike_commits(PRE / 'spike.trace'))
    start = next(i for i, c in enumerate(cs) if c.pc == 0x80000000)
    end = next(i for i, c in enumerate(cs) if (pre['symbols']['tohost'], 1) in c.memory_accesses)
    return cs[start:end + 1]


def command(out):
    return FunctionType(prior.command.__code__, dict(prior.command.__globals__,
        ELF=ELF, NAME=NAME, PROBE=PROBE))(out)


def manifest(out, service=SERVICE):
    import collect_scalar_misalign789 as collector
    out = Path(out).absolute()
    require(out.parent == life.OUT and out.resolve() == out, 'Canonical direct output')
    require(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service', service) is not None, 'Exact service')
    pre = life.read_bound(PRE / 'preflight-manifest.json', PRE_SEAL)
    require(pre['baseline_seal'] == BASE_SHA and pre['VCS_authorized'] is False
        and pre['coverage_admitted'] is False and pre['output_pins'][str(ELF)] == ELF_SHA,
        'Frozen software-only preflight')
    ledger = oracle.traps((PRE / 'spike.trace').read_text(), pre['symbols'])
    ref = reference(pre)
    require(oracle.validate(ref, pre['symbols'], ledger) == pre['validation'], 'Complete independent software oracle')
    counts = template.reference_counts(ref, 0x80000000, pre['symbols']['tohost'])
    require(counts['matched_instructions'] == 866 and counts['matched_scalar_memory_accesses'] == 226,
        'Frozen terminal reference counts')
    counts = {k: counts[k] for k in ('matched_instructions', 'matched_scalar_writes', 'matched_scalar_memory_accesses')}
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    status = life.read_bound(BASE / 'status.json', base['output_pins'][str(BASE / 'status.json')])
    require(type(status['aggregate_passed']) is int and status['aggregate_passed'] == 789
        and status['coverage_admitted'] is True, 'Formal789 authority')
    inputs = BASE / 'combined-inputs.txt'
    require(life.digest(inputs) == base['output_pins'][str(inputs)], 'Exact ledger binding')
    members = inputs.read_text().splitlines()
    require(len(members) == len(set(members)) == 790, 'Exact789 membership')
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(len(image['image']) == 66 and image['image'][str(life.IMAGE)] == IMAGE_SHA, 'Frozen image66')
    proof = collector.source_proof()
    pins = life.merge_pins(pre['pins'], pre['output_pins'])
    for more in (image['image'], image['design_files'], proof['pins'],
                 {str(PRE / 'preflight-manifest.json'): PRE_SEAL, str(BASE / 'admission-manifest.json'): BASE_SHA,
                  str(life.PLAN): life.PLAN_SEAL},
                 {str(BASE / n): base['output_pins'][str(BASE / n)] for n in ('status.json', 'combined-inputs.txt', 'combined-bits.json')}):
        pins = life.merge_pins(pins, more)
    files = [Path(__file__).resolve(), Path(collector.__file__), PROBE,
             Path(__file__).with_name('test_run_scalar_misalign789.py'),
             Path(__file__).with_name('test_collect_scalar_misalign789.py'),
             Path(__file__).with_name('test_scalar_misalign789_reference.py'),
             Path(prior.__file__), Path(template.__file__), Path(template.frozen.__file__),
             Path(life.__file__), converter.CONVERTER]
    files += list((life.ROOT / 'verification/ara_verify').rglob('*.py'))
    require(life.digest(converter.CONVERTER) == converter.CONVERTER_SHA, 'Converter identity')
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files})
    life.check(pins)
    return dict(case=NAME, output=str(out), pins=pins, command=command(out), timeout_s=BUDGET,
        input_elf=str(ELF), input_spike_trace=str(PRE / 'spike.trace'), elf_sha256=ELF_SHA,
        image_sha256=IMAGE_SHA, preflight_seal=PRE_SEAL, raw_baseline=str(BASE),
        raw_baseline_seal=BASE_SHA, raw_baseline_population=789, source_contract=proof,
        scalar_reference_counts=counts, expected_traps=ledger, expected_checks=56,
        old_image_files_checked=66, automatic_retry=False, no_FSDB=True, focused_readonly_VPD=True,
        systemd_policy=dict(RuntimeMaxSec=170, TimeoutStopSec=10, KillMode='control-group'),
        coverage_admitted=False, RTL_changed=False, terminal_oracle_verified=False,
        service=service, authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED_BEFORE_RUN')


def verify_prepared(out, record, terminal=False):
    require(terminal or not Path(out).exists(), 'Fresh pre-run output')
    require(record == manifest(out, record['service']), 'Full prepared command/source/pin drift')
    return record


def lifecycle_namespace(out, record):
    return FunctionType(prior.lifecycle_namespace.__code__, dict(prior.lifecycle_namespace.__globals__,
        PRE=PRE, ELF_SHA=ELF_SHA, IMAGE_SHA=IMAGE_SHA, BUDGET=BUDGET, NAME=NAME, command=command))(out, record)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify', 'run'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--prepared-seal')
    p.add_argument('--service', default=SERVICE); p.add_argument('--parent-authorized', action='store_true')
    a = p.parse_args()
    require((a.mode != 'prepare') == bool(a.prepared_seal), 'Prepared seal required')
    require((a.mode == 'run') == a.parent_authorized, 'Explicit parent authorization')
    out = a.output.absolute(); sidecar = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        require(not out.exists() and not sidecar.exists(), 'Exclusive fresh prepare')
        life.save(sidecar, manifest(out, a.service))
        print(json.dumps(dict(prepared=str(sidecar), seal=life.digest(sidecar), VCS_started=False)))
    else:
        record = life.read_bound(sidecar, a.prepared_seal); verify_prepared(out, record)
        if a.mode == 'run': lifecycle_namespace(out, record)['run'](out, record)
        else: print('SCALAR_MISALIGN789_PREPARED_VERIFY_PASS_NO_VCS')


if __name__ == '__main__': main()
