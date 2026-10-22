"""Sealed764 lifecycle entry: adapt FMA metadata accessor, not native audits."""
import argparse
import copy
import inspect
import json
from pathlib import Path
from types import FunctionType

import report_native_batch764 as report

life, require = report.life, report.require
HERE = Path(__file__).resolve().parent
CONFIG_SHA = 'ac29ddc8ccbf31c21a6a0edbd16a4711799809342c367bedadbd58624cdb587c'
OUTPUT = life.OUT/'native-batch-full764-agent-20261007-01'


def verifier_body():
    body = inspect.getsource(report.old.verify)
    accessor = "len(c['expected_union']['fma'])"
    require(body.count(accessor) == 1, 'Exact metadata accessor anchor differs')
    body = body.replace(accessor, "len(c['expected_union']['retained']['fma'])")
    anchor = '        if path.exists():'
    require(body.count(anchor) == 1, 'Immutable stdout snapshot anchor differs')
    body = body.replace(anchor, '        snapshot_stdout(data,out)\n'+anchor)
    anchor = "    audit_six(out, 'child', c['child_references'])"
    require(body.count(anchor) == 1, 'Full complement audit anchor differs')
    return body.replace(anchor, anchor+"\n    audit_six(out, 'batch_scale', c['batch_scale_references'])")


def prepare_entry():
    c = report.check(OUTPUT, CONFIG_SHA)
    require(not (OUTPUT/'execution.json').exists() and not (OUTPUT/'terminal.json').exists(), 'Already executed')
    verifier_body()
    deps = [Path(__file__).resolve(), HERE/'test_run_native_batch764_entry.py']
    pins = {str(p):life.digest(p) for p in deps}
    pins[str(OUTPUT/'config.json')] = CONFIG_SHA
    life.check(pins)
    entry = dict(schema='SEALED764_METADATA_ACCESSOR_ONLY_LIFECYCLE_V1', output=str(OUTPUT),
                 config_seal=CONFIG_SHA, pins=pins, script=str(Path(__file__).resolve()),
                 five_stage_full_complement_preserved=True, population=764, automatic_retry=False)
    life.save(OUTPUT/'runtime-entry.json',entry)
    print(json.dumps(dict(status='READY_NO_EDA',seal=life.digest(OUTPUT/'runtime-entry.json'))),flush=True)


def namespace(entry_seal):
    entry = life.read_bound(OUTPUT/'runtime-entry.json',entry_seal)
    require(entry['schema']=='SEALED764_METADATA_ACCESSOR_ONLY_LIFECYCLE_V1' and entry['output']==str(OUTPUT) and
            entry['config_seal']==CONFIG_SHA and entry['script']==str(Path(__file__).resolve()), 'Entry identity differs')
    life.check(entry['pins'])
    def check(out,seal):
        require(out==OUTPUT and seal==CONFIG_SHA,'Exact sealed764 only')
        c = copy.deepcopy(report.check(out,seal))
        c['pins'] = report.merge(c['pins'],entry['pins'],{str(OUTPUT/'runtime-entry.json'):entry_seal})
        life.check(c['pins'])
        return c
    ns = report.namespace(); ns.update(check=check)
    exec(compile(verifier_body(),__file__,'exec'),ns)
    ns['run'] = FunctionType(ns['run'].__code__,ns)
    return ns


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare-entry','run','verify'))
    p.add_argument('--entry-seal');a=p.parse_args()
    if a.mode=='prepare-entry':prepare_entry()
    else:
        require(a.entry_seal,'Sealed entry required')
        namespace(a.entry_seal)[a.mode](OUTPUT,CONFIG_SHA)
