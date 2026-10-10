"""Authorized exact742+GAP114 architecture-qualified admission; no simulation/DVE."""
import argparse
import csv
import json
from pathlib import Path
import coverage_bitmap_delta as bitmap
import run_gap95_simulation as life
import postprocess_gap114_traps_v2 as qtool
import admit_gap113_cached742 as native

require = qtool.require
BASE = life.OUT/'gap113-full8-cached-offline-admitted-742-agent-20261007-01'
BASE_SHA = 'f07f7ccdcfc7257faad21aabdc45a48008658c70ee26abda275065f1e204a730'
QUAL = qtool.OUT
DESIGN = native.DESIGN
VDB = qtool.RUN/'code.vdb'
NAME = 'vgap114_spec_load_flush'
QUAL_SEALS = {
    'qualification.json': 'f5703569a73c045de4cac35bbb65c048ec0f7e79bb868011f9100292ffc9f2e2',
    'input-pins.json': 'f1dcce4e1a4b3caf6da68a4a1004a22fdae4c17a498d778a26f91c497680bcb2',
    'single-bits.json': '4dab7beacf36e373fdc0e115956494405dbe7ec189413b7143a4c03b19477cc8',
    'trap-audit.json': 'bd6d4396353f26b6ac2700600edd9ae6c62ad8566dfd895b402609284dd4cea0',
    'scalar-comparison.json': '97a1683a000810d15f5f86b65b12b6d3f71f733021dd79969f2b75e66a16cf87',
    'vector-comparison.json': 'c71996ed92bc3868cf7f3cca0bb39a9373303fb1a6f58066134c2247df973c96',
}


def exact_prefix(before, inputs):
    require(len(before) == len(set(before)) == 742 and inputs == [str(DESIGN), *before] and
            str(VDB) not in before, 'Exact unique742 prefix/novel VDB required')


def verify_union(before, single, combined):
    require(combined['tests'] == before['tests']+[str(VDB)] and len(set(combined['tests'])) == 743,
            'Exact742 prefix/unique743 membership differs')
    require(before['design'] == single['design'] == combined['design'] and
            set(before['metrics']) == set(single['metrics']) == set(combined['metrics']) == set(bitmap.METRICS),
            'Frozen design/metric set differs')
    count = 0
    for metric, rows in before['metrics'].items():
        require(rows.keys() == single['metrics'][metric].keys() == combined['metrics'][metric].keys(),
                'Metric universe differs')
        for scope, old in rows.items():
            new, result = single['metrics'][metric][scope], combined['metrics'][metric][scope]
            require((old['width'], old['checksum']) == (new['width'], new['checksum']) ==
                    (result['width'], result['checksum']) and int(result['bits'], 16) ==
                    int(old['bits'], 16)|int(new['bits'], 16), 'Exact independent OR/identity differs')
            count += 1
    require(count == 6162, 'Frozen6162 metric universe differs')
    return count


def positive_gain(delta):
    require(delta['metrics'] == dict(line=0, cond=0, branch=0, fsm=1), 'Measured GAP114 gain differs/zero gain')
    require(len(delta['instances']) == 1 and delta['instances'][0]['instance'] ==
            'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.i_load_unit' and
            delta['instances'][0]['metric'] == 'fsm' and delta['instances'][0]['new_bits'] == 1,
            'Unexpected gaining scope')


def check():
    base = life.read_bound(BASE/'admission-manifest.json', BASE_SHA)
    def baseline(name): return life.read_bound(BASE/name, base['output_pins'][str(BASE/name)])
    before, status = baseline('combined-bits.json'), baseline('status.json')
    require(status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and status['aggregate_passed'] == 742 and
            status['coverage_admitted'] is True, 'Formal742 required')
    values = {name: life.read_bound(QUAL/name, sha) for name, sha in QUAL_SEALS.items()}
    q = values['qualification.json']
    require(q['status'] == 'EIGHT_ECALL_ARCHITECTURE_PASS_RAW_DIAGNOSTIC_NOT_ADMITTED' and
            q['coverage_admitted'] is False and q['checks'] == 2619 and q['original_failure_is_rtl_bug'] is False,
            'Exact eight-ECALL architecture qualification required')
    pins = life.merge_pins(base['input_pins'], base['output_pins'])
    pins = life.merge_pins(pins, values['input-pins.json'])
    pins = life.merge_pins(pins, {str(QUAL/n): sha for n, sha in QUAL_SEALS.items()})
    pins = life.merge_pins(pins, {str(BASE/'admission-manifest.json'): BASE_SHA})
    pins = life.merge_pins(pins, before['input_hashes'])
    for relative, sha in before['design'].items():
        pins = life.merge_pins(pins, {str(DESIGN/'snps/coverage/db'/relative): sha})
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_gap114_743.py'),
              Path(bitmap.__file__).resolve(), Path(life.__file__).resolve(), Path(native.__file__).resolve()):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins)
    inputs = (BASE/'combined-inputs.txt').read_text().splitlines(); exact_prefix(before['tests'], inputs)
    pre = life.read_bound(qtool.PRE/'successor-preflight.json', pins[str(qtool.PRE/'successor-preflight.json')])
    require(str(qtool.PRE/'input.elf') in pins and pins[str(qtool.PRE/'input.elf')] not in base['input_pins'].values(),
            'ELF unbound/already admitted')
    manifest = life.read_bound(qtool.RUN/'manifest.json', pins[str(qtool.RUN/'manifest.json')])
    require(manifest['pins'][str(qtool.PRE/'successor-preflight.json')] == pins[str(qtool.PRE/'successor-preflight.json')],
            'Executed preflight differs')
    terminal = life.read_bound(qtool.RUN/'simulation-status.json', pins[str(qtool.RUN/'simulation-status.json')])
    require(terminal['returncode'] == 0, 'Simulation not clean terminal')
    with (qtool.RUN/'commit_trace.csv').open() as stream: rows = list(csv.DictReader(stream))
    require(qtool.traps_exact(rows, pre['symbols']) == values['trap-audit.json'] == q['traps'], 'Trap replay differs')
    memory = {}
    for r in rows:
        if r['event'] == 'retire':
            store = qtool.run.shared.scalar_store(r)
            if store: memory.update({store[0]+i: b for i, b in enumerate(store[1])})
    def value(name, offset=0, size=8):
        address = pre['symbols'][name]+offset
        require(all(address+i in memory for i in range(size)), 'Missing independent software oracle byte')
        return int.from_bytes(bytes(memory[address+i] for i in range(size)), 'little')
    qtool.run.oracle(value, pre['symbols'])
    scalar = qtool.run.shared.spike_trace.compare_commit_prefix(qtool.PRE/'spike.trace', qtool.RUN/'commit_trace.csv',
        0x80000000, terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
    qtool.scalar_exact(scalar, pre['counts'])
    require(scalar == values['scalar-comparison.json'], 'Full scalar replay differs')
    vector = qtool.run.shared.compare_vector_commits(qtool.PRE/'spike.trace', qtool.RUN/'commit_trace.csv',
                                                   qtool.RUN/'vector_trace.csv', 0x80000000)
    require(vector == values['vector-comparison.json'] and vector['status'] == 'PASS', 'Full vector replay differs')
    require((qtool.RUN/'console.log').read_text().count('Core Test *** SUCCESS ***') == 1 and
            not qtool.run.shared.check_contract_log(qtool.RUN/'run.vcs.log'), 'Contract/terminal differs')
    single = values['single-bits.json']
    require(single['tests'] == [str(VDB)] and all(pins.get(p) == sha for p, sha in single['input_hashes'].items()),
            'Qualified singleton unbound')
    for metric in (*bitmap.METRICS, 'tgl'):
        files = list((VDB/'snps/coverage/db/testdata').glob('*/%s.verilog.data.xml'%metric))
        require(len(files) == 1 and files[0].parent.name == NAME and pins.get(str(files[0])) == life.digest(files[0]),
                'Native five-metric identity/pin differs')
        if metric != 'tgl': require(bitmap.read_metric(files[0]) == single['metrics'][metric], 'Native bitmap differs')
        else:
            prior = list((Path(before['tests'][0])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
            require(len(prior) == 1 and pins.get(str(prior[0])) == life.digest(prior[0]) and
                    native.toggle_shape(files[0]) == native.toggle_shape(prior[0]), 'Native Toggle shape differs')
    combined = bitmap.combine(before, single); count = verify_union(before, single, combined)
    delta = bitmap.delta(before, combined); positive_gain(delta)
    require(delta == q['delta'], 'Sealed qualified delta differs')
    life.check(pins)
    return dict(single=single, combined=combined, delta=delta, inputs=inputs+[str(VDB)], pins=pins, count=count)


def payload(record):
    return dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=743, baseline=742, new_passed=1,
                exact742_prefix=True, unique_new_vdb=True, full_OR_instances=record['count'],
                raw_delta=record['delta']['metrics'], coverage_admitted=True, qualification_replayed=True,
                software_checks=2619, exact_ecall_traps=8, native_metrics_complete=['line','cond','branch','fsm','tgl'],
                historical_fixed_image_only=True, new_RTL_signoff=False, whole_ISA_qualified=False,
                official_denominator_verified=False, simulations_started=False, rtl_changed=False,
                gap115_included=False)


def admit(out, record):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    out.mkdir()
    for name, value in [('single-bits.json', record['single']), ('combined-bits.json', record['combined']),
                        ('raw-delta.json', record['delta']), ('status.json', payload(record))]: life.save(out/name, value)
    with (out/'combined-inputs.txt').open('x') as stream: stream.write('\n'.join(record['inputs'])+'\n')
    with (out/'single-inputs.txt').open('x') as stream: stream.write(str(DESIGN)+'\n'+str(VDB)+'\n')
    life.check(record['pins'])
    life.save(out/'admission-manifest.json', dict(schema='GAP114_EIGHT_ECALL743_ADMISSION_V1', output=str(out),
        baseline=str(BASE), baseline_seal=BASE_SHA, qualification=str(QUAL/'qualification.json'),
        qualification_seal=QUAL_SEALS['qualification.json'], input_pins=record['pins'],
        output_pins={str(p): life.digest(p) for p in out.iterdir() if p.is_file()}, explicit_parent_authorized=True))
    print(json.dumps(dict(status=payload(record), seal=life.digest(out/'admission-manifest.json'))))


def verify(out, seal, record):
    m = life.read_bound(out/'admission-manifest.json', seal)
    require(m['schema'] == 'GAP114_EIGHT_ECALL743_ADMISSION_V1' and m['output'] == str(out) and
            m['baseline_seal'] == BASE_SHA and m['qualification_seal'] == QUAL_SEALS['qualification.json'] and
            m['input_pins'] == record['pins'] and m['explicit_parent_authorized'] is True, 'Admission contract differs')
    life.check(m['output_pins'])
    require(set(m['output_pins']) == {str(out/n) for n in ('single-bits.json', 'combined-bits.json', 'raw-delta.json',
            'status.json', 'combined-inputs.txt', 'single-inputs.txt')}, 'Output inventory differs')
    for name, value in [('single-bits.json', record['single']), ('combined-bits.json', record['combined']),
                        ('raw-delta.json', record['delta']), ('status.json', payload(record))]:
        require(life.read_bound(out/name, m['output_pins'][str(out/name)]) == value, 'Admission replay differs: '+name)
    require((out/'combined-inputs.txt').read_text() == '\n'.join(record['inputs'])+'\n' and
            (out/'single-inputs.txt').read_text() == str(DESIGN)+'\n'+str(VDB)+'\n', 'Input ledger replay differs')
    print(json.dumps(dict(status='GAP114_HISTORICAL743_OFFLINE_REVERIFIED', seal=seal)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path); parser.add_argument('--parent-authorized', action='store_true')
    parser.add_argument('--verify-seal'); parser.add_argument('--check', action='store_true'); args = parser.parse_args()
    require((args.check and not args.output and not args.parent_authorized and not args.verify_seal) or
            (args.output and not args.check and bool(args.parent_authorized) != bool(args.verify_seal)), 'Exact CLI mode required')
    record = check()
    if args.check: print(json.dumps(dict(status='READY743_NOT_ADMITTED', delta=record['delta']['metrics'])))
    elif args.verify_seal: verify(args.output.absolute(), args.verify_seal, record)
    else: admit(args.output.absolute(), record)
