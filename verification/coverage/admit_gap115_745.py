"""Authorized744+focused GAP115 admission; independent AXI contract, not UVM PASS."""
import argparse
from pathlib import Path
import audit_gap115_axi_v2 as audit
import admit_gap114_743 as prior

life, bitmap, require = audit.life, prior.bitmap, audit.require
BASE = life.OUT/'rvv-lmul8-payload-walk-offline-admitted-744-agent-20261007-01'
BASE_SHA = '06bc169ca882a44b382bea694b2dfc4ffcdb23a353b73fb117d6b29cbc70168a'
QUAL = audit.OUT
QUAL_SHA = '02789325e010ff99cb78f78751ea0f17a19eadbbb9be6ae88a14cabe222d10e4'
RUN, DESIGN = audit.capture.OUT, prior.DESIGN
VDB = RUN/'code.vdb'


def exact_prefix(before, inputs):
    require(len(before) == len(set(before)) == 744 and inputs == [str(DESIGN), *before]
            and str(VDB) not in before, 'Exact unique744 prefix/novel VDB required')


def verify_union(before, single, combined):
    require(single['tests'] == [str(VDB)] and combined['tests'] == before['tests']+[str(VDB)]
            and len(set(combined['tests'])) == 745, 'Exact744 prefix/unique745 differs')
    require(before['design'] == single['design'] == combined['design'] and
            set(before['metrics']) == set(single['metrics']) == set(combined['metrics']) == set(bitmap.METRICS),
            'Design/metric universe differs')
    count = 0
    for metric, rows in before['metrics'].items():
        require(rows.keys() == single['metrics'][metric].keys() == combined['metrics'][metric].keys(),
                'Instance universe differs')
        for scope, old in rows.items():
            new, result = single['metrics'][metric][scope], combined['metrics'][metric][scope]
            require((old['width'], old['checksum']) == (new['width'], new['checksum']) ==
                    (result['width'], result['checksum']) and int(result['bits'], 16) ==
                    (int(old['bits'], 16) | int(new['bits'], 16)), 'Independent exact OR/identity differs')
            count += 1
    require(count == 6162, 'Frozen6162 metric universe differs')
    return count


def qualification_exact(q):
    require(q['status'] == 'GAP115_FOCUSED_AXI_AND_TRACE_EQUIVALENT_ARCHITECTURE_PASS_NOT_ADMITTED'
            and q['exact_commit_and_vector_bytes_equal'] is True and q['software_checks'] == 679
            and q['restored_vrf_bytes'] == 4096 and q['recovery_vector_compared_bytes'] == 7168
            and q['axi_burst_conservation_verified'] is True and q['uvm_check_report_pass'] is False
            and q['original_failures_preserved'] is True and q['coverage_admitted'] is False,
            'Exact independent AXI/architecture boundary required')


def positive_gain(delta):
    require(delta['metrics'] == dict(line=0, cond=0, branch=0, fsm=4), 'Exact fresh four-FSM gain required')
    expected = {audit.ROOT+'.gen_lanes[%d].i_lane.i_vfus.i_vmfpu.i_simd_div'%i for i in range(4)}
    require(len(delta['instances']) == 4 and {r['instance'] for r in delta['instances']} == expected
            and all(r['metric'] == 'fsm' and r['new_bits'] == 1 for r in delta['instances']),
            'Only four lane divider FSM gains allowed')


def check():
    base = life.read_bound(BASE/'admission-manifest.json', BASE_SHA)
    pins = life.merge_pins(base['input_pins'], base['output_pins'])
    pins = life.merge_pins(pins, {str(BASE/'admission-manifest.json'): BASE_SHA})
    before = life.read_bound(BASE/'combined-bits.json', pins[str(BASE/'combined-bits.json')])
    state = life.read_bound(BASE/'status.json', pins[str(BASE/'status.json')])
    require(state['coverage_admitted'] is True and state['aggregate_passed'] == 744
            and state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY', 'Formal744 required')
    q = life.read_bound(QUAL/'qualification.json', QUAL_SHA); qualification_exact(q)
    pins = life.merge_pins(pins, q['output_pins'])
    pins = life.merge_pins(pins, life.read_bound(QUAL/'evidence-pins.json', pins[str(QUAL/'evidence-pins.json')]))
    pins = life.merge_pins(pins, {str(QUAL/'qualification.json'): QUAL_SHA})
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_gap115_745.py'),
              Path(prior.__file__).resolve()):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins)
    inputs = (BASE/'combined-inputs.txt').read_text().splitlines(); exact_prefix(before['tests'], inputs)
    terminal = life.read_bound(RUN/'simulation-status.json', pins[str(RUN/'simulation-status.json')])
    require(terminal['returncode'] == 0, 'Clean terminal required')
    for name in ('commit_trace.csv', 'vector_trace.csv'):
        require(pins[str(RUN/name)] == pins[str(audit.capture.OLD/name)], 'Qualified architecture trace differs')
    setup = audit.markers((RUN/'console.log').read_text())
    require(setup == life.read_bound(QUAL/'setup-audit.json', pins[str(QUAL/'setup-audit.json')]), 'Setup replay differs')
    saved = life.read_bound(QUAL/'axi-audit.json', pins[str(QUAL/'axi-audit.json')])
    replay = audit.read_bursts(audit.WAVE, saved['bursts'][0]['address'], 0x123456789abcdef0*(1+(1<<64)))
    require(all(saved[k] == v for k, v in replay.items()), 'Independent AXI replay differs')
    _, cr = audit.architecture.run.reset.read_csv(RUN/'commit_trace.csv')
    _, vr = audit.architecture.run.reset.read_csv(RUN/'vector_trace.csv')
    epochs, _ = audit.architecture.run.reset.split_epochs(cr, vr)
    prepath = audit.architecture.run.PRE/'preflight.json'
    pre = life.read_bound(prepath, pins[str(prepath)])
    original = life.read_bound(QUAL/'uvm-original-contract-audit.json', pins[str(QUAL/'uvm-original-contract-audit.json')])
    events = audit.architecture.events_audit((RUN/'run.vcs.log').read_text(), epochs, original, pre['symbols'])
    require(events == life.read_bound(QUAL/'event-audit.json', pins[str(QUAL/'event-audit.json')]), 'Event replay differs')
    single = dict(design=before['design'], tests=[str(VDB)], input_hashes={}, metrics={})
    for rel, sha in before['design'].items():
        pins = life.merge_pins(pins, {str(DESIGN/'snps/coverage/db'/rel): sha})
    for metric in (*bitmap.METRICS, 'tgl'):
        files = list((VDB/'snps/coverage/db/testdata').glob('*/%s.verilog.data.xml'%metric))
        require(len(files) == 1, 'Missing/ambiguous metric')
        source = files[0]
        pins = life.merge_pins(pins, {str(source): life.digest(source)})
        if metric != 'tgl':
            single['metrics'][metric] = bitmap.read_metric(source)
            single['input_hashes'][str(source)] = pins[str(source)]
        else:
            old = list((Path(before['tests'][0])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
            require(len(old) == 1 and str(old[0]) in pins and
                    prior.native.toggle_shape(source) == prior.native.toggle_shape(old[0]), 'Toggle identity differs')
    combined = bitmap.combine(before, single); count = verify_union(before, single, combined)
    delta = bitmap.delta(before, combined); positive_gain(delta); life.check(pins)
    return dict(single=single, combined=combined, delta=delta, inputs=inputs+[str(VDB)], pins=pins, count=count)


def payload(r):
    return dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=745, baseline=744, new_passed=1,
        exact744_prefix=True, unique_new_vdb=True, coverage_admitted=True, full_OR_instances=r['count'],
        raw_delta=r['delta']['metrics'], software_checks=679, independent_axi_and_events_contract_pass=True,
        uvm_check_report_pass=False, original_missing_uvm_summary_failure_preserved=True,
        whole_ISA_qualified=False, official_denominator_verified=False, rtl_changed=False, simulations_started=False)


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--parent-authorized', action='store_true'); p.add_argument('--verify-seal'); a = p.parse_args()
    require(bool(a.parent_authorized) != bool(a.verify_seal), 'One authorized admission or verification mode required')
    out = a.output.absolute(); r = check()
    values = {'single-bits.json': r['single'], 'combined-bits.json': r['combined'],
              'raw-delta.json': r['delta'], 'status.json': payload(r)}
    texts = {'combined-inputs.txt': '\n'.join(r['inputs'])+'\n',
             'single-inputs.txt': str(DESIGN)+'\n'+str(VDB)+'\n'}
    if a.verify_seal:
        m = life.read_bound(out/'admission-manifest.json', a.verify_seal)
        require(m['schema'] == 'GAP115_INDEPENDENT_AXI745_ADMISSION_V1' and m['output'] == str(out)
                and m['baseline_seal'] == BASE_SHA and m['qualification_seal'] == QUAL_SHA
                and m['input_pins'] == r['pins'] and m['explicit_parent_authorized'] is True, 'Manifest differs')
        require(set(m['output_pins']) == {str(out/n) for n in (*values, *texts)}, 'Output inventory differs')
        life.check(m['output_pins'])
        for n, v in values.items(): require(life.read_bound(out/n, m['output_pins'][str(out/n)]) == v, 'Output replay differs')
        for n, v in texts.items(): require((out/n).read_text() == v, 'Input replay differs')
        print('GAP115_HISTORICAL745_OFFLINE_REVERIFIED '+a.verify_seal); return
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    out.mkdir()
    for n, v in values.items(): life.save(out/n, v)
    for n, v in texts.items():
        with (out/n).open('x') as f: f.write(v)
    life.check(r['pins'])
    life.save(out/'admission-manifest.json', dict(schema='GAP115_INDEPENDENT_AXI745_ADMISSION_V1', output=str(out),
        baseline=str(BASE), baseline_seal=BASE_SHA, qualification=str(QUAL/'qualification.json'), qualification_seal=QUAL_SHA,
        input_pins=r['pins'], output_pins={str(f): life.digest(f) for f in out.iterdir()}, explicit_parent_authorized=True))
    print('GAP115_HISTORICAL745_ADMITTED '+life.digest(out/'admission-manifest.json'))


if __name__ == '__main__': main()
