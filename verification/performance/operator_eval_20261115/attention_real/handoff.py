#!/usr/bin/env python3
"""Combine prepared firmware manifests and host evidence without launching jobs."""
import argparse
import json
from pathlib import Path
import re

import check
from contract import HERE, OUT, require, save, sha, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--build',action='append',type=Path,required=True)
    parser.add_argument('--host-tests',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a = parser.parse_args()
    out = a.output.absolute()
    require(out == out.resolve() and out.parent == OUT.resolve() and
            re.fullmatch(r'operator_attention_real_prepare_20261115_[A-Za-z0-9_.-]+',out.name)
            and not out.exists(), 'Fresh owned output required')
    host = a.host_tests.resolve(strict=True)
    host_report = json.loads((host/'result.json').read_text())
    require(host_report['state'] == 'HOST_TEST_PASS_NOT_RTL' and host_report['post_pins_match']
            and not host_report['failures'] and not host_report['errors'] and not host_report['skipped']
            and sha(host/'source-pins.json') == host_report['source_pins_sha256'] and
            sha(host/'host-tests.log') == host_report['log_sha256'], 'Passing pinned host evidence required')
    pins = {}
    def merge(values):
        for path,digest in values.items():
            require(path not in pins or pins[path] == digest,'Input identity conflict: '+path)
            pins[path] = digest
    merge(json.loads((host/'source-pins.json').read_text()))
    for p in host.iterdir():
        require(p.is_file(),'Unknown host evidence member')
        pins[str(p)] = sha(p)
    cases,reports,seen = [],[],set()
    for directory in a.build:
        directory = directory.resolve(strict=True)
        require(directory.parent == OUT.resolve() and
                directory.name.startswith('operator_attention_real_prepare_20261115_'), 'Unowned firmware input')
        m = check.receipt(directory)
        merge(json.loads((directory/'source-pins.json').read_text()))
        merge(m['artifacts'])
        pins[str(directory/'build.json')] = sha(directory/'build.json')
        plan = json.loads((directory/'run-plan.json').read_text())
        for case in plan['cases']:
            require(case['id'] not in seen, 'Duplicate run identity')
            seen.add(case['id'])
            case['source_pins'] = str(out/'source-pins.json')
            cases.append(case)
        f = m['fixture']; c = f['case']
        reports.append(dict(build=str(directory),elf_sha256=m['elf_sha256'],
            case=c['id'],provenance=c['provenance'],flags=f['result']['expected_fcsr'],
            natural_flags=f['result']['natural_flags'],model_comparison=f['model_comparison'],
            independent_golden_sha256=sha(directory/'inputs/golden.bin'),
            scalar_expf_audit=m['scalar_expf_audit'],trials=m['modes'],order=m['order'],
            qk_and_pv_fmas_each_per_call=c['heads']*c['tokens']*c['dimension'],
            expected_akv_commands=len(check.expected_work(f)[0]),
            expected_resident_commands=sum(1 for arm in f['order'] if arm == 2)*
                2*c['kv_heads']*((c['tokens']+63)//64),
            runtime_default_resident_enabled=False,rtl_executed=False))
    for p in (Path(__file__).resolve(),HERE/'REVIEW.md'):
        pins[str(p)] = sha(p)
    verify(pins)
    out.mkdir()
    save(out/'source-pins.json',pins)
    save(out/'run-plan.json',dict(cases=cases))
    report = dict(state='REAL_CONTEXT_FIRMWARE_READY_NOT_RTL_ACCEPTED',
        source_pins_sha256=sha(out/'source-pins.json'),run_plan_sha256=sha(out/'run-plan.json'),
        builds=reports,host_tests=str(host),host_tests_run=host_report['tests_run'],
        rtl_executed=False,hardware_cycles_measured=False,performance_acceptance=False,
        parent_image='operator_soc_20261115_activity_02',parent_max_simulator_slots=4,
        image_checked=False,protocol_checked=False,review=str(HERE/'REVIEW.md'),
        unprepared=['Full model/query-head groups, complete Llama GQA4 and multiple KV groups',
            'Real native D96/D256, contexts beyond KV1025, other layers/models/cache types',
            'Prefill, batches, noncausal/sliding masks, features and numerical-mode expansion',
            'Balanced repeated RTL measurements, actual target results and performance curves',
            'GGML graph/runtime default enablement, FPGA memory admission and end-to-end benefit'])
    save(out/'result.json',report)
    print(json.dumps(dict(state=report['state'],manifest=str(out/'run-plan.json'),
        source_pins=str(out/'source-pins.json'),host_tests=host_report['tests_run'],cases=len(cases))),flush=True)


if __name__ == '__main__': main()
