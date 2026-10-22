#!/usr/bin/env python3
"""Rebind one frozen native-byte stimulus to 723; no ELF or EDA execution."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import preflight_qbs_m8_phase8_payload_722 as p
from closure_point_inventory import definition, points, read_xml

BASE = p.ROOT / 'verification/out/narrow-reject-r1-cached-offline-admitted-723-20261006-01'
SEAL = '2f68f64b880b95164f8db6aa2b569d305bd831ad4a05056563b2ab42eade45a4'
PARENT = p.ROOT / 'verification/out/qbs-m8-phase8-payload-static-preflight-722-20261006-01/preflight.json'
PARENT_SEAL = '8eaef804c567e76b93a92b482af7c55cecd034df92cbe3612c59bb5fc96d74e4'


def reconcile(previous, current, metric):
    p.require(metric['width'] == 21503 and str(metric['checksum']) == '2947893042',
              '723 metric identity differs')
    p.require(len(previous) == len(current) == 12, 'target count differs')
    for index, (old, new) in enumerate(zip(previous, current)):
        p.require(old == new, 'full compiled target identity differs')
        p.validate_point(new, p.TARGETS[index], index//3)
        p.require(not int(metric['bits'], 16) & (1 << (metric['width']-1-new['raw_index'])),
                  '723 target already hit')


def prepare(out):
    p.require(not out.exists(), 'output exists')
    pins = {}

    def bind(path, sha):
        raw = path.read_bytes()
        p.require(hashlib.sha256(raw).hexdigest() == sha, 'input differs: '+str(path))
        p.require(str(path) not in pins or pins[str(path)] == sha, 'conflicting expected pin')
        pins[str(path)] = sha
        return json.loads(raw)

    parent = bind(PARENT, PARENT_SEAL)
    for section in ('input_pins', 'fixture_pins'):
        for path, sha in parent[section].items():
            p.require(p.digest(Path(path)) == sha, 'parent input differs: '+path)
            p.require(path not in pins or pins[path] == sha, 'conflicting expected pin')
            pins[path] = sha
    manifest = bind(BASE/'admission-manifest.json', SEAL)
    bits = bind(BASE/'combined-bits.json', manifest['output_pins'][str(BASE/'combined-bits.json')])
    status = bind(BASE/'status.json', manifest['output_pins'][str(BASE/'status.json')])
    p.require(status['aggregate_passed'] == 723 and status['coverage_admitted'] is True,
              'not formal 723')
    db = p.old.DESIGN/'snps/coverage/db'
    for relative, sha in bits['design'].items():
        path = db/relative
        p.require(p.digest(path) == sha and pins.get(str(path)) == sha, 'design differs')
    metric = bits['metrics']['cond'][p.SCOPE]
    design = p.old.shared.proof.old.shared.Design(p.old.DESIGN)
    node = definition(read_xml(db/'shape/cond.verilog.shape.xml'),
                      design.hierarchy[p.SCOPE], metric['checksum'])
    mapped = {point['raw_index']: point for point in points('cond', node, metric['width'])}
    current = [mapped[target[0]] for target in p.TARGETS]
    reconcile(parent['targets'], current, metric)
    for path in (Path(__file__), Path(__file__).with_name('test_rebind_qbs_m8_phase8_payload_723.py')):
        pins[str(path)] = p.digest(path)
    record = copy.deepcopy(parent)
    record.update(baseline=str(BASE), baseline_seal=SEAL, input_pins=pins, targets=current,
                  parent_preflight=str(PARENT), parent_preflight_seal=PARENT_SEAL,
                  latest_target_zero_rechecked=723)
    for path, sha in pins.items():
        p.require(p.digest(Path(path)) == sha, 'input changed during rebind')
    out.mkdir(parents=True)
    path = out/'preflight.json'
    path.write_text(json.dumps(record, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(path), seal=p.digest(path), targets=len(current), elf_ready=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    prepare(parser.parse_args().out.resolve())
