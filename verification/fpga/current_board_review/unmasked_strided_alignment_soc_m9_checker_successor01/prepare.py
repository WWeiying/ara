#!/usr/bin/env python3
"""Offline pin verification only. No simulator, build or service entry point."""
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import checker as c

PLAN_SHA = '0e73362c293a7b4937f8a03a580371e0b92c1b3ae21303f50d800af5c19eafdf'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main(out):
    c.need(not out.exists(), 'No output overwrite')
    planpath = c.BASE/'vcs_m9_prepared01/plan.json'
    c.need(sha(planpath) == PLAN_SHA, 'Sealed original plan identity')
    plan = json.loads(planpath.read_text())
    host = json.loads((c.HERE/'host01.json').read_text())
    c.need(host['status'] == 'HOST_PROTOCOL_SUCCESSOR_PASS_NOT_DUT' and host['negatives'] == 80
           and host['checker_sha256'] == sha(c.HERE/'checker.py')
           and host['test_sha256'] == sha(c.HERE/'test_checker.py')
           and host['sealed_checker_sha256'] == sha(c.BASE/'dut_check.py'), 'Actual host/code binding')
    pins = dict(plan['pins'])
    pins[str(planpath)] = PLAN_SHA
    for p in (c.HERE/'checker.py', c.HERE/'test_checker.py', c.HERE/'host01.json', Path(__file__),
              c.BASE.parents[3]/'verification/ara_verify/trace.py',
              c.HERE.parent/'unmasked_strided_alignment_repair_zeno01/M9_SOC_CHECKER_FOLLOWUP01.md'):
        pins[str(p)] = sha(p)
    image = json.loads((Path(plan['image'])/'image.json').read_text())
    for rel in ('hardware/tb/ara_commit_monitor.sv', 'hardware/include/ara_pkg.sv'):
        p = Path(image['snapshot'])/'sources'/rel
        c.need(str(p) in pins and pins[str(p)] == sha(p), 'Frozen monitor/package identity')
    failures = [p for p, expected in pins.items() if sha(p) != expected]
    c.need(not failures, 'Preflight pin drift: '+repr(failures))
    scopes = []
    for case in plan['cases']:
        if case['kind'] != 'directed':
            continue
        spec = json.loads(Path(case['spec']).read_text())
        c.need(spec['elf'] == case['elf'] and spec['elf_sha256'] == case['sha256'] == sha(case['elf']),
               'Original SoC ELF/spec identity')
        scopes.append(dict(member=case['member'], elf=case['elf'], elf_sha256=case['sha256'],
                           memory_sites=c.recipe(spec), checks=698 if case['member'].startswith('store') else 697))
    c.need(len(scopes) == 4, 'Exact four directed members')
    original_output = c.BASE/'vcs_m9_prepared01'
    result = dict(status='CHECKER_PREPARED_HOST_PASS_NOT_DUT', original_plan_sha256=PLAN_SHA,
                  original_output=str(original_output), image=plan['image'], image_sha256=plan['image_sha256'],
                  original_launch_record_exists=(original_output/'launch.json').exists(),
                  original_complete_record_exists=(original_output/'complete.json').exists(),
                  original_output_entries=sorted(p.name for p in original_output.iterdir()),
                  scopes=scopes, pins=pins, pin_count=len(pins),
                  checker_command=[sys.executable, '-B', str(c.HERE/'checker.py'),
                                   '<member>', '<closed_commit_trace.csv>', '<original_soc.spec.json>', '<new_csv.json>'],
                  launch_authorized=False, launched=False, original_worker_unchanged=True,
                  future_integration='New worker/plan must bind this checker; original worker still calls sealed check_case.py. '
                                     'Keep generic trace validation, original data oracle, child outcome, image and resource gates. '
                                     'Do not launch the original prepared worker as though it uses this successor.',
                  budgets_unchanged=dict(directed_s=900, controls_s=180, jobs=2, service_s=4200))
    with out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps(dict(status=result['status'], pins=len(pins), ready=str(out), sha256=sha(out))))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
