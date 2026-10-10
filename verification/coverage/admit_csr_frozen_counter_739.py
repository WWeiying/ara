"""Direct sealed CSR qualification + formal738 -> reviewed historical739; no EDA."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex

import qualify_csr_frozen_counter_terminal as q
from closure_point_inventory import read_xml

life, require = q.life, q.require
BASE = q.runner.oracle.BASE
BASE_SEAL = '972d4dec87035fb12343d25305666a8d9c5a88ea8215ef330638e468386249f7'
QUAL = life.OUT / 'csr-frozen-counter-qualified-parent-20261007-01/qualification-seal.json'
QUAL_SEAL = 'a103410e06f2f737f3335fbfc66c484500d6db19207026a969a529077049813c'
Q_SHA = 'be0e2888c96407888cf96b425e8434caebd601b2c6c4019ff6bc46457522863d'
DESIGN = Path(str(life.IMAGE) + '.vdb')
PROOFS = {'scalar-comparison.json', 'vector-comparison.json', 'architecture-audit.json', 'source-contract.json',
          'contract-audit.json', 'vdb-inventory.json', 'single-inputs.txt', 'single-bits.json',
          'raw-delta.json', 'target-hits.json'}


def qualification_gate(proof):
    q.runner.exact_fields(proof, dict(status='CSR_FULL_SCALAR_COUNTER_ORACLE_QUALIFIED_NOT_ADMITTED',
        run=str(q.RUN), run_seal=q.RUN_SEAL, full_scalar_differential_qualified=True,
        full_scalar_memory_qualified=True, independent_counter_CSR_qualified=True,
        checks=54, observed_bytes=416, vector_status='UNOBSERVABLE_ZERO_DESTINATIONS', raw_baseline=738,
        coverage_admitted=False, admission_performed=False, simulations_started=False, rtl_changed=False,
        official_denominator_verified=False), 'Qualification scope differs')
    require(set(proof['output_pins']) == {str(QUAL.parent / n) for n in PROOFS}, 'Complete qualification outputs required')


def union(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 738 and
            single['tests'] == [str(q.RUN / 'code.vdb')] and single['tests'][0] not in before['tests'],
            'Exact738 prefix and unique singleton required')
    for data in (before, single):
        require(set(data['metrics']) == set(q.bitmap.METRICS) and
                sum(len(rows) for rows in data['metrics'].values()) == 6162, 'Full6162 universe required')
        for rows in data['metrics'].values():
            for row in rows.values():
                require(type(row['width']) is int and row['width'] >= 0 and
                        0 <= int(row['bits'], 16) < 1 << row['width'], 'Malformed bitmap')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    combined = q.bitmap.combine(before, single)
    require(combined['tests'] == before['tests'] + single['tests'] and len(set(combined['tests'])) == 739,
            'Exact738 prefix lost')
    for metric, rows in before['metrics'].items():
        for scope, row in rows.items():
            require(int(combined['metrics'][metric][scope]['bits'], 16) ==
                    int(row['bits'], 16) | int(single['metrics'][metric][scope]['bits'], 16), 'Full OR differs')
    delta = q.bitmap.delta(before, combined)
    require(sum(delta['metrics'].values()) > 0, 'Zero-gain admission forbidden')
    return combined, delta


def target_hits(before, single, targets):
    require(len(targets) == 7 and {(t['metric'], t['raw_index']) for t in targets} ==
            {('line', 275), ('line', 578), ('line', 585), ('line', 589), ('cond', 90), ('cond', 92), ('branch', 202)},
            'Exact seven targets required')
    hits = []
    for t in targets:
        r = dict(t)
        require(t['scope'] == q.runner.oracle.inventory.SCOPE and t['hit'] is False,
                'Target scope/baseline differs')
        for field, data in (('before_hit', before), ('single_hit', single)):
            row = data['metrics'][t['metric']][t['scope']]
            require((row['width'], row['checksum']) == (t['width'], t['checksum']) and
                    type(t['raw_index']) is int and 0 <= t['raw_index'] < row['width'], 'Target shape differs')
            r[field] = bool(int(row['bits'], 16) & (1 << (row['width'] - 1 - t['raw_index'])))
        require(not r['before_hit'] and r['single_hit'], 'Primary fresh target not hit')
        r['union_hit'] = True
        hits.append(r)
    return hits


def evaluate():
    require(life.digest(Path(q.__file__)) == Q_SHA, 'Frozen qualification implementation drift')
    proof = life.read_bound(QUAL, QUAL_SEAL)
    qualification_gate(proof)
    pins = life.merge_pins(proof['pins'], proof['output_pins'])
    pins = life.merge_pins(pins, {str(QUAL): QUAL_SEAL})
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    require(base['output'] == str(BASE), 'Baseline owner differs')
    pins = life.merge_pins(pins, life.merge_pins(base['input_pins'], base['output_pins']))
    pins = life.merge_pins(pins, {str(BASE / 'admission-manifest.json'): BASE_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_csr_frozen_counter_739.py')):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    def artifact(name):
        return life.read_bound(QUAL.parent / name, proof['output_pins'][str(QUAL.parent / name)])
    before = life.read_bound(BASE / 'combined-bits.json', pins[str(BASE / 'combined-bits.json')])
    q.baseline_gate(base, life.read_bound(BASE / 'status.json', pins[str(BASE / 'status.json')]), before)
    require((BASE / 'combined-inputs.txt').read_text().splitlines() == [str(DESIGN), *before['tests']],
            'Exact baseline membership/order differs')
    record = life.read_bound(q.RUN.with_name(q.RUN.name + '.prepared.json'), q.RUN_SEAL)
    require(life.read_bound(q.RUN / 'manifest.json', q.RUN_SEAL) == record == q.runner.manifest(q.RUN),
            'Frozen execution record differs')
    q.terminal_gate(life.read_bound(q.RUN / 'simulation-status.json', pins[str(q.RUN / 'simulation-status.json')]),
                    life.read_bound(q.RUN / 'started.json', pins[str(q.RUN / 'started.json')]), record)
    members = sorted(p for p in (q.RUN / 'code.vdb').rglob('*') if p.is_file())
    require(artifact('vdb-inventory.json') == {str(p): pins[str(p)] for p in members} and
            not any(p.is_symlink() for p in (q.RUN / 'code.vdb').rglob('*')), 'Terminal VDB membership differs')
    directory = q.RUN / 'code.vdb/snps/coverage/db/testdata' / q.runner.NAME
    require(list(directory.parent.iterdir()) == [directory], 'Ambiguous singleton owner')
    args, info = read_xml(directory / 'vcmArguments.xml'), read_xml(directory / 'siminfo.xml')
    tests = list(info.iter('srctest'))
    options = [n.get('vcm_opt') for n in args.iter('vcm_arg_data') if n.get('vcm_opt') is not None]
    require(args.get('compvdbpath') == str(DESIGN) and len(tests) == 1 and len(options) == 5 and
            set(options) == {'-cm ' + m for m in (*q.bitmap.METRICS, 'tgl')} and
            shlex.split(tests[0].get('cmdline', '')) == record['command'] and
            tests[0].get('workdir') == str(q.RUN) and tests[0].get('seed') == '1', 'Native VDB command/design differs')
    pre = life.read_bound(q.runner.PRE / 'preflight-manifest.json', q.runner.PRE_SEAL)
    reference = q.primitives.reference_prefix(q.spike_trace.parse_spike_commits(q.runner.PRE / 'spike.trace'),
                                               pre['symbols']['tohost'])
    scalar = q.spike_trace.compare_commit_prefix(q.runner.PRE / 'spike.trace', q.RUN / 'commit_trace.csv',
                0x80000000, terminal_tohost_address=pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
    q.scalar_gate(scalar)
    require(scalar == artifact('scalar-comparison.json'), 'Actual scalar replay differs')
    arch = q.architecture(q.primitives.parse_rows(q.RUN / 'commit_trace.csv'), reference, pre['symbols'],
                         q.elf_file_bytes(q.runner.ELF.read_bytes(), pre['symbols']['counter_guards'], 16))
    require(arch == artifact('architecture-audit.json'), 'Actual independent CSR/gold/guards differ')
    q.primitives.zero.vector_zero(q.RUN / 'vector_trace.csv')
    vector = q.vector_commit.compare_vector_commits(q.runner.PRE / 'spike.trace', q.RUN / 'commit_trace.csv',
                                                    q.RUN / 'vector_trace.csv', 0x80000000)
    q.primitives.vector_gate(vector)
    require(vector == artifact('vector-comparison.json'), 'Actual zero-vector replay differs')
    require(q.primitives.log_gate((q.RUN / 'run.vcs.log').read_text()) == artifact('contract-audit.json'),
            'Actual log contract differs')
    console = (q.RUN / 'console.log').read_text()
    q.primitives.log_gate(console, require_contract='[ARA_CONTRACT]' in console)
    single = artifact('single-bits.json')
    require((QUAL.parent / 'single-inputs.txt').read_text().splitlines() == [str(DESIGN), str(q.RUN / 'code.vdb')],
            'Singleton input order differs')
    for metric in q.bitmap.METRICS:
        path = directory / (metric + '.verilog.data.xml')
        require(single['input_hashes'].get(str(path)) == pins[str(path)] and
                single['metrics'][metric] == q.bitmap.read_metric(path), 'Actual singleton raw bits differ')
    combined, delta = union(before, single)
    hits = target_hits(before, single, record['targets'])
    require(delta == artifact('raw-delta.json') and hits == artifact('target-hits.json') and
            delta['metrics'] == dict(line=6, cond=4, branch=5, fsm=0), 'Actual raw delta/targets differ')
    life.check(pins)
    products = {'single-bits.json': single, 'combined-bits.json': combined, 'raw-delta.json': delta,
                'target-hits.json': hits, 'evidence-pins.json': pins,
                'status.json': dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', baseline=738, aggregate_passed=739,
                    new_passed=1, case=q.runner.NAME, coverage_admitted=True, exact738_prefix=True,
                    full_OR_instances=6162, raw_delta=delta['metrics'], primary_targets_hit=7,
                    full_scalar_matched=782, full_scalar_gpr_writes=434, full_scalar_memory_accesses=203,
                    scalar_skips=0, traps=0, checks=54, observed_bytes=416,
                    vector_status='UNOBSERVABLE_ZERO_DESTINATIONS', vector_comparison_pass=False,
                    qualification=str(QUAL), qualification_seal=QUAL_SEAL, inherited_738_all_pins_rechecked=True,
                    historical_fixed_image_only=True, new_RTL_signoff=False, official_denominator_verified=False,
                    rtl_changed=False, simulations_started=False)}
    text = '\n'.join([str(DESIGN), *combined['tests']]) + '\n'
    return products, text


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify', 'admit'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepared-seal')
    p.add_argument('--parent-authorized', action='store_true')
    a = p.parse_args(argv)
    require((a.mode != 'prepare') == bool(a.prepared_seal) and (a.mode == 'admit') == a.parent_authorized,
            'Exact prepared seal and separate admission authorization required')
    out = a.output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    products, text = evaluate()
    hashes = {str(out / n): hashlib.sha256((json.dumps(v, indent=2) + '\n').encode()).hexdigest()
              for n, v in products.items()}
    hashes[str(out / 'combined-inputs.txt')] = hashlib.sha256(text.encode()).hexdigest()
    prepared = dict(schema='CSR_COUNTER_HISTORICAL739_PREPARED_V1', output=str(out), baseline=str(BASE),
                    baseline_seal=BASE_SEAL, qualification=str(QUAL), qualification_seal=QUAL_SEAL,
                    input_pins=products['evidence-pins.json'], output_pins=hashes)
    sidecar = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        require(not sidecar.exists(), 'Fresh review sidecar required')
        life.save(sidecar, prepared)
        print(json.dumps(dict(prepared=str(sidecar), seal=life.digest(sidecar), admitted=False)))
        return
    require(life.read_bound(sidecar, a.prepared_seal) == prepared, 'Prepared admission drift')
    if a.mode == 'verify':
        print('CSR_COUNTER_HISTORICAL739_PREPARED_VERIFY_PASS_NOT_ADMITTED')
        return
    life.check(prepared['input_pins'])
    out.mkdir()
    for name, value in products.items():
        life.save(out / name, value)
    with (out / 'combined-inputs.txt').open('x') as stream:
        stream.write(text)
    life.check(hashes)
    life.save(out / 'admission-manifest.json', dict(prepared, schema='CSR_COUNTER_HISTORICAL739_ADMISSION_V1',
              prepared=str(sidecar), prepared_seal=a.prepared_seal))
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'admission-manifest.json'), aggregate_passed=739)))


if __name__ == '__main__':
    main()
