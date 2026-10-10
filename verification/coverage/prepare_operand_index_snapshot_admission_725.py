"""Exact724->725 proposal from cached raw diagnostics; admit requires parent authorization."""
import argparse
from collections import Counter
import json
from pathlib import Path

import collect_operand_index_snapshot_raw_724 as raw

life,require = raw.life,raw.require
AUTHORIZATION = 'PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'
PRODUCTS = {'combined-bits.json','combined-inputs.txt','raw-delta.json','gained-compiled-points.json',
            'target-reconciliation724.json','evidence-pins.json','status.json'}


def gate(state,targets,points):
    raw.qualified.old.exact(state,dict(status='SNAPSHOT_RESTART_RAW724_DIAGNOSTIC_NOT_ADMITTED',
        baseline_tests=724,proposed_tests=725,new_admitted=0,coverage_admitted=False,
        baseline_seal=raw.BASE_SEAL,qualification_seal=raw.QUAL_SEAL,exact724_prefix=True,
        full_scalar_differential_qualified=True,all_scalar_memory_differential_qualified=True,
        whole_destination_CSR_neighbors_qualified=True,checks=457,exceptions=0,targets_total=16,
        inherited724_replayed=False,inherited724_pins_rechecked=True,new_RTL_signoff=False,
        rtl_changed=False,simulations_started=False),'Incomplete exact725 eligibility')
    delta = state['raw_delta']
    require(set(delta) == set(raw.bitmap.METRICS) and
            all(type(n) is int and n >= 0 for n in delta.values()) and sum(delta.values()) > 0,
            'Zero/malformed actual gain cannot prepare admission')
    coordinates = [(t['scope'],t['metric'],t['point']['raw_index']) for t in targets]
    require(len(coordinates) == len(set(coordinates)) == 16 and all(
        t['baseline724_hit'] is False and type(t['sample_hit']) is bool and
        t['proposed_hit'] == t['sample_hit'] and t['new_vs724'] == t['sample_hit'] and
        t['native_GUI_ID_qualification'] is False for t in targets),'Incomplete exact16 target reconciliation')
    require(type(state['targets_hit']) is int and state['targets_hit'] == sum(t['sample_hit'] for t in targets),
            'Invented target hit count')
    coords = [(r['scope'],r['metric'],r['point']['raw_index']) for r in points]
    require(len(coords) == len(set(coords)) and all(r['baseline_hit'] is False and
        r['sample_hit'] is True and r['proposed_hit'] is True and r['native_GUI_ID_qualification'] is False
        and r['source_sha256'] for r in points),'Duplicate/unproved compiled gain')
    counts = Counter(r['metric'] for r in points if r['scope'] == 'ara_tb.dut.i_ara_soc.i_system' or
                     r['scope'].startswith('ara_tb.dut.i_ara_soc.i_system.'))
    require(all(counts[m] == delta[m] for m in raw.bitmap.METRICS),'Compiled product gain count differs')


def fresh(output):
    require(output.parent == life.OUT and output.resolve() == output and not output.exists() and
            '-parent-' not in output.name,'Fresh agent-owned direct output required')


def diagnostic(path,seal):
    require(path.parent == life.OUT and path.resolve() == path,'Canonical diagnostic path required')
    receipt = life.read_bound(path/'diagnostic-seal.json',seal)
    require(not (path/'failure.json').exists() and receipt['coverage_admitted'] is False and
            receipt['qualification_seal'] == raw.QUAL_SEAL and
            set(receipt['output_pins']) == {str(path/n) for n in raw.PRODUCTS},
            'Rejected/missing diagnostic products')
    life.check(receipt['input_pins'])
    life.check(receipt['output_pins'])
    pins,before,q = raw.context()
    single = life.read_bound(path/'single-raw-bits.json',receipt['output_pins'][str(path/'single-raw-bits.json')])
    require((path/'single-inputs.txt').read_text().splitlines() == [str(raw.DESIGN),str(raw.RUN/'code.vdb')],
            'Foreign singleton collector ledger')
    pins,artifacts = raw.evaluate(single,receipt['output_pins'][str(path/'single-raw-bits.json')],pins,before,q)
    for name,value in artifacts.items():
        require(life.read_bound(path/name,receipt['output_pins'][str(path/name)]) == value,
                'Independent cached union/target/source audit differs: '+name)
    require((path/'proposed-inputs.txt').read_text().splitlines() ==
            [str(raw.DESIGN),*artifacts['proposed-combined-bits.json']['tests']],
            'Wrong full proposed725 ledger')
    gate(artifacts['status.json'],artifacts['target-reconciliation724.json'],artifacts['gained-compiled-points.json'])
    pins = life.merge_pins(pins,receipt['input_pins'])
    pins = life.merge_pins(pins,receipt['output_pins'])
    pins = life.merge_pins(pins,{str(path/'diagnostic-seal.json'):seal})
    life.check(pins)
    return pins,artifacts,receipt


def prepare(output,formal_output,path,seal):
    fresh(output)
    fresh(formal_output)
    require(output != formal_output,'Prepare is not admission')
    pins,artifacts,_ = diagnostic(path,seal)
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_prepare_operand_index_snapshot_admission_725.py')):
        pins = life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    output.mkdir()
    values = {'combined-bits.json':artifacts['proposed-combined-bits.json'],
        'raw-delta.json':artifacts['raw-delta.json'],
        'gained-compiled-points.json':artifacts['gained-compiled-points.json'],
        'target-reconciliation724.json':artifacts['target-reconciliation724.json'],
        'evidence-pins.json':pins,'status.json':dict(artifacts['status.json'],
            status='SNAPSHOT_HISTORICAL725_PREPARED_NOT_ADMITTED',formal_output=str(formal_output))}
    for name,value in values.items():
        life.save(output/name,value)
    with (output/'combined-inputs.txt').open('x') as stream:
        stream.write((path/'proposed-inputs.txt').read_text())
    life.check(pins)
    life.save(output/'prepared-seal.json',dict(schema='SNAPSHOT_RESTART_HISTORICAL725_PREPARE_V1',
        output=str(output),formal_output=str(formal_output),baseline=str(raw.BASE),baseline_seal=raw.BASE_SEAL,
        diagnostic=str(path),diagnostic_seal=seal,qualification_seal=raw.QUAL_SEAL,input_pins=pins,
        output_pins={str(output/n):life.digest(output/n) for n in PRODUCTS},coverage_admitted=False,
        new_admitted=0,requires_parent_authorization=True))
    return life.digest(output/'prepared-seal.json')


def check(output,seal):
    require(output.parent == life.OUT and output.resolve() == output,'Canonical prepared path required')
    receipt = life.read_bound(output/'prepared-seal.json',seal)
    raw.qualified.old.exact(receipt,dict(schema='SNAPSHOT_RESTART_HISTORICAL725_PREPARE_V1',output=str(output),
        baseline=str(raw.BASE),baseline_seal=raw.BASE_SEAL,qualification_seal=raw.QUAL_SEAL,
        coverage_admitted=False,new_admitted=0,requires_parent_authorization=True),'Prepared identity drift')
    require(set(receipt['output_pins']) == {str(output/n) for n in PRODUCTS},'Missing/foreign prepared product')
    life.check(receipt['input_pins'])
    life.check(receipt['output_pins'])
    _,artifacts,_ = diagnostic(Path(receipt['diagnostic']),receipt['diagnostic_seal'])
    expected = {'combined-bits.json':artifacts['proposed-combined-bits.json'],'raw-delta.json':artifacts['raw-delta.json'],
        'gained-compiled-points.json':artifacts['gained-compiled-points.json'],
        'target-reconciliation724.json':artifacts['target-reconciliation724.json'],
        'status.json':dict(artifacts['status.json'],status='SNAPSHOT_HISTORICAL725_PREPARED_NOT_ADMITTED',
                          formal_output=receipt['formal_output']),'evidence-pins.json':receipt['input_pins']}
    for name,value in expected.items():
        require(life.read_bound(output/name,receipt['output_pins'][str(output/name)]) == value,
                'Prepared independent product mismatch: '+name)
    require((output/'combined-inputs.txt').read_bytes() ==
            (Path(receipt['diagnostic'])/'proposed-inputs.txt').read_bytes(),'Prepared full ledger drift')
    return receipt


def admit(prepared,seal,output,authorization):
    require(authorization == AUTHORIZATION,'Separate explicit parent authorization required')
    receipt = check(prepared,seal)
    require(str(output) == receipt['formal_output'],'Different formal output requires fresh prepare')
    fresh(output)
    pins = life.merge_pins(receipt['input_pins'],receipt['output_pins'])
    pins = life.merge_pins(pins,{str(prepared/'prepared-seal.json'):seal})
    life.check(pins)
    output.mkdir()
    for name in PRODUCTS-{'status.json','evidence-pins.json'}:
        with (output/name).open('xb') as stream:
            stream.write((prepared/name).read_bytes())
    life.save(output/'evidence-pins.json',pins)
    state = life.read_bound(prepared/'status.json',receipt['output_pins'][str(prepared/'status.json')])
    life.save(output/'status.json',dict(state,status='PASS_RAW_UNION_HISTORICAL_ONLY',baseline=724,
        aggregate_passed=725,new_passed=1,new_admitted=1,coverage_admitted=True))
    life.check(pins)
    life.save(output/'admission-manifest.json',dict(schema='SNAPSHOT_RESTART_HISTORICAL725_ADMISSION_V1',
        output=str(output),baseline=str(raw.BASE),baseline_seal=raw.BASE_SEAL,prepared=str(prepared),prepared_seal=seal,
        diagnostic=receipt['diagnostic'],diagnostic_seal=receipt['diagnostic_seal'],qualification_seal=raw.QUAL_SEAL,
        authorization=authorization,output_pins={str(output/n):life.digest(output/n) for n in PRODUCTS}))
    return life.digest(output/'admission-manifest.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check','admit'))
    for name in ('output','formal-output','diagnostic','prepared'):
        parser.add_argument('--'+name,type=Path)
    for name in ('diagnostic-seal','seal','authorization'):
        parser.add_argument('--'+name)
    a = parser.parse_args()
    if a.mode == 'prepare':
        require(a.output and a.formal_output and a.diagnostic and a.diagnostic_seal and
                not(a.prepared or a.seal or a.authorization),'Exact prepare arguments required')
        seal = prepare(a.output.absolute(),a.formal_output.absolute(),a.diagnostic.absolute(),a.diagnostic_seal)
        print(json.dumps(dict(status='PREPARED_NOT_ADMITTED',output=str(a.output.absolute()),seal=seal)))
    elif a.mode == 'check':
        require(a.prepared and a.seal and not(a.output or a.formal_output or a.diagnostic or a.diagnostic_seal or a.authorization),
                'Exact readonly check arguments required')
        check(a.prepared.absolute(),a.seal)
        print('PREPARED725_CHECK_PASS_NOT_ADMITTED')
    else:
        require(a.prepared and a.seal and a.output and a.authorization and
                not(a.formal_output or a.diagnostic or a.diagnostic_seal),'Exact parent admit arguments required')
        seal = admit(a.prepared.absolute(),a.seal,a.output.absolute(),a.authorization)
        print(json.dumps(dict(output=str(a.output.absolute()),seal=seal,status='PASS_RAW_UNION_HISTORICAL_ONLY')))


if __name__ == '__main__':
    main()
