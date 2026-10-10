"""Reviewed full CSR core+closure, formal786 -> 787; no simulation or DVE."""
import argparse
import hashlib
import json
from pathlib import Path

import collect_csr_satp_sepc_packed_successor as consumer

f, life, require = consumer.original, consumer.life, consumer.require
BASE, BASE_SHA = f.runner.BASE, f.runner.BASE_SHA
QUAL = life.OUT / 'csr-satp-sepc-packed-qualified-agent-20261008-02'
QUAL_SHA = '08292dd5ee50f8e7b274349b464c2f8f1fedc8ecbb8e6dd0cc1a8cec06195bc1'
CLOSURE_SHA = '6f7324797716c70f54c6aad3c1a63c5fc9b9aad1b03e836cbb3d394078e0cc99'
PLAN = life.OUT / 'csr-satp-sepc-packed-qualification-plan-agent-20261008-01.json'
PLAN_SHA = '2471ec2fec3b10f2ef2f379510f897312b6a57eba43578a7aa377d4e5fcc59ee'
COUNTS = dict(line=1892, cond=2023, branch=2155, fsm=92)
PROOFS = {'scalar-comparison.json', 'vector-comparison.json', 'vpd2vcd.log', 'csr-owner.vcd',
          'single-inputs.txt', 'single-bits.json', 'combined-bits.json', 'raw-delta.json',
          'typed-target-toggle-gain.json', 'architecture-audit.json', 'native-csr-owner-audit.json'}


def joint_gate(q, c, qsha):
    f.runner.exact_fields(q, dict(status='CSR_SATP_SEPC786_FULL_SCALAR_NATIVE_OWNER_QUALIFIED_NOT_ADMITTED',
        run=str(consumer.adapter.packed.RUN), run_seal=consumer.RUN_SEAL, checks=44, observed_bytes=336,
        scalar_retirements=673, scalar_memory_accesses=168, native_CSR_owners=30,
        vector_status='UNOBSERVABLE_ZERO_DESTINATIONS', full_scalar_differential_qualified=True,
        coverage_admitted=False, RTL_changed=False, EDA_launched=False), 'Complete core qualification required')
    require(set(q['output_pins']) == {str(QUAL / n) for n in PROOFS}, 'Complete core output obligations')
    f.runner.exact_fields(c, dict(status='FULL_CSR_PACKED_RVFI_EPOCH_QUALIFIED_NOT_ADMITTED',
        core_qualification=str(QUAL / 'qualification.json'), core_sha256=qsha,
        prepared_plan=str(PLAN), prepared_seal=PLAN_SHA, coverage_admitted=False, EDA_launched=False,
        original_HOLD_preserved=True, core_qualification_not_overwritten=True), 'Exact complete successor closure required')
    require(c['original_core_output_pins'] == q['output_pins'] and c['raw_gain'] == q['raw_gain']
            and c['input_pins'].get(str(PLAN)) == PLAN_SHA, 'Closure/core/plan obligations conflict')
    require(q['input_pins'].get(str(Path(f.__file__).resolve())) == consumer.adapter.packed.COLLECTOR_SHA,
            'Frozen original complete collector authority')
    life.merge_pins(q['input_pins'], c['input_pins'])


def full_union(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 786 and
            single['tests'] == [str(consumer.adapter.packed.RUN / 'code.vdb')] and
            single['tests'][0] not in before['tests'], 'Exact786 prefix and distinct singleton')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    after = f.bitmap.combine(before, single)
    require(before['design'] == single['design'] == after['design'] and
            after['tests'] == before['tests'] + single['tests'] and len(set(after['tests'])) == 787,
            'Exact frozen design/787 prefix')
    require(set(before['metrics']) == set(single['metrics']) == set(after['metrics']) == set(COUNTS), 'All four metrics')
    for metric, count in COUNTS.items():
        old, add, final = (x['metrics'][metric] for x in (before, single, after))
        require(len(old) == count and set(old) == set(add) == set(final), 'Full6162 scope universe')
        for scope, a in old.items():
            b, c = add[scope], final[scope]
            require(all(type(row['width']) is int and row['width'] >= 0 for row in (a, b, c)) and
                    (a['width'], a['checksum']) == (b['width'], b['checksum']) == (c['width'], c['checksum']), 'Exact native shape')
            aa, bb, cc = (int(row['bits'], 16) for row in (a, b, c))
            require(min(aa, bb, cc) >= 0 and max(aa, bb, cc).bit_length() <= a['width'] and
                    cc == aa | bb and cc & aa == aa, 'Independent complete bounded OR')
    return after


def positive(delta, fields):
    require(set(delta['metrics']) == set(COUNTS) and all(type(n) is int and n >= 0 for n in delta['metrics'].values()), 'Typed raw delta')
    require(fields and all(type(i) is int and 0 <= i for field in fields for i in field['gained']), 'Typed Toggle coordinates')
    require(sum(delta['metrics'].values()) + sum(len(field['gained']) for field in fields) > 0, 'Zero-gain admission forbidden')


def historical_dedup(base, ledger, authority):
    path = BASE / 'elf-ledger-dedup.json'
    audit = life.read_bound(path, base['output_pins'][str(path)])
    require(audit['ledger_members'] == len(audit['members']) == 785 and audit['duplicate'] is False and
            [r['vdb'] for r in audit['members']] == ledger[1:786], 'Sealed first785 exact ELF ownership')
    for row in audit['members']:
        require(row['ELF_candidates'], 'Missing historical ELF owner')
        for name, sha in row['ELF_candidates'].items():
            require(authority.get(name) == sha and sha != f.runner.ELF_SHA, 'Duplicate/drifting historical ELF')
    command_path = Path(ledger[-1]).parent / 'manifest.json'
    command = life.read_bound(command_path, authority[str(command_path)])['command']
    preload = [word.split('=', 1)[1] for word in command if word.startswith('+PRELOAD=')]
    require(len(preload) == 1 and preload[0] in authority and authority[preload[0]] != f.runner.ELF_SHA,
            'Actual786 last-member ELF duplicate/owner')
    return dict(ledger_members=786, duplicate=False, first785_audit=str(path),
        first785_audit_sha256=base['output_pins'][str(path)], final786_command=str(command_path),
        final786_ELF=preload[0], new_ELF_sha256=f.runner.ELF_SHA,
        historical_authority_only=True, candidate_not_used_as_historical_owner=True)


def evaluate(qsha, csha):
    require((qsha, csha) == (QUAL_SHA, CLOSURE_SHA), 'Exact parent-reviewed core/closure seals')
    q = life.read_bound(QUAL / 'qualification.json', qsha)
    c = life.read_bound(QUAL / 'packed-epoch-closure.json', csha); joint_gate(q, c, qsha)
    pins = life.merge_pins(life.merge_pins(q['input_pins'], q['output_pins']), c['input_pins'])
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    require(base['coverage_admitted'] is True and base['output'] == str(BASE), 'Formal786 authority')
    authority = life.merge_pins(base['input_pins'], base['output_pins'])
    pins = life.merge_pins(pins, authority)
    fixed = {str(QUAL / 'qualification.json'): qsha, str(QUAL / 'packed-epoch-closure.json'): csha,
             str(BASE / 'admission-manifest.json'): BASE_SHA}
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_csr_satp_sepc787.py')):
        fixed[str(path)] = life.digest(path)
    pins = life.merge_pins(pins, fixed); life.check(pins)
    def qdoc(name): return life.read_bound(QUAL / name, q['output_pins'][str(QUAL / name)])
    before = life.read_bound(BASE / 'combined-bits.json', authority[str(BASE / 'combined-bits.json')])
    status = life.read_bound(BASE / 'status.json', authority[str(BASE / 'status.json')])
    require(type(status['aggregate_passed']) is int and status['aggregate_passed'] == 786 and status['coverage_admitted'] is True, 'Actual786 status')
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    require(ledger == [str(life.IMAGE) + '.vdb', *before['tests']] and len(ledger) == len(set(ledger)) == 787, 'Exact786 membership')
    run = consumer.adapter.packed.RUN
    record = life.read_bound(run / 'manifest.json', consumer.RUN_SEAL)
    f.runner.verify_prepared(run, record, terminal=True)
    f.terminal_gate(*[life.read_bound(run / n, pins[str(run / n)]) for n in
                     ('simulation-status.json', 'started.json', 'live-identity.json')], record)
    pre = life.read_bound(f.runner.PRE / 'preflight-manifest.json', f.runner.PRE_SEAL)
    scalar = f.spike_trace.compare_commit_prefix(f.runner.PRE / 'spike.trace', run / 'commit_trace.csv',
        0x80000000, terminal_tohost_address=pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
    f.scalar_gate(scalar); require(scalar == qdoc('scalar-comparison.json'), 'Full scalar replay differs')
    arch = f.architecture(f.primitive.parse_rows(run / 'commit_trace.csv'), f.runner.reference(pre), pre['symbols'], f.runner.ELF.read_bytes())
    require(arch == qdoc('architecture-audit.json'), 'Full independent44 CSR/gold/guards/memory differs')
    owners = consumer.adapter.wave_audit(QUAL / 'csr-owner.vcd', arch['expected_CSR'])
    require(owners == qdoc('native-csr-owner-audit.json'), 'All30 native owner replay differs')
    f.primitive.zero.vector_zero(run / 'vector_trace.csv')
    vector = f.vector_commit.compare_vector_commits(f.runner.PRE / 'spike.trace', run / 'commit_trace.csv', run / 'vector_trace.csv', 0x80000000)
    f.primitive.vector_gate(vector); require(vector == qdoc('vector-comparison.json'), 'Exact zero-vector replay differs')
    for name in ('console.log', 'run.vcs.log'): f.primitive.log_gate((run / name).read_text())
    lines = (run / 'console.log').read_text().splitlines()
    require(lines.count('CSR_OWNER_PROBE_READY') == 1 and not any(f.re.match(r'^CSR_OWNER_PROBE_ERROR(?:\s|$)', line) for line in lines), 'Exact probe markers')
    members = sorted(p for p in (run / 'code.vdb').rglob('*') if p.is_file())
    require(members and not any(p.is_symlink() for p in (run / 'code.vdb').rglob('*')) and
            {str(p) for p in members} == {p for p in q['input_pins'] if p.startswith(str(run / 'code.vdb') + '/')}, 'Complete VDB membership')
    folder = run / 'code.vdb/snps/coverage/db/testdata' / f.runner.NAME
    require(list(folder.parent.iterdir()) == [folder], 'One actual native candidate')
    native = f.coverage.coverage_identity(folder, run, record, Path(ledger[0]))
    require(all(pins.get(path) == sha for path, sha in native.items()), 'All five native metrics/command identity')
    require((QUAL / 'single-inputs.txt').read_text().splitlines() == [ledger[0], str(run / 'code.vdb')], 'Exact qualified singleton ledger')
    single = qdoc('single-bits.json')
    for metric in COUNTS:
        path = folder / (metric + '.verilog.data.xml')
        require(single['metrics'][metric] == f.bitmap.read_metric(path) and single['input_hashes'].get(str(path)) == pins[str(path)], 'Actual singleton raw bits')
    after = full_union(before, single); delta = f.bitmap.delta(before, after)
    require(after == qdoc('combined-bits.json') and delta == qdoc('raw-delta.json') and delta['metrics'] == q['raw_gain']['four_metrics'], 'Qualified786 full OR/delta')
    fields = qdoc('typed-target-toggle-gain.json'); target = life.read_bound(f.runner.PRE / 'target-before.json', pins[str(f.runner.PRE / 'target-before.json')])
    suffix_path = next((Path(ledger[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    scopes = [f.CORE, f.CSR]
    suffix, sha = f.oracle.toggle.rows(suffix_path, scopes); require(authority.get(str(suffix_path)) == sha, 'Bound786 Toggle suffix')
    sample, sha = f.oracle.toggle.rows(folder / 'tgl.verilog.data.xml', scopes); require(pins[str(folder / 'tgl.verilog.data.xml')] == sha, 'Bound candidate Toggle')
    actual_fields = []
    for t in target['fields']:
        old, new = suffix[t['scope']], sample[t['scope']]
        require(old['width'] == new['width'] and old['checksum'] == new['checksum'] == t['checksum'], 'Exact typed target shape')
        remaining = [i for i in t['missing_coordinates'] if not int(old['bits'], 16) >> (old['width'] - 1 - i) & 1]
        gained = [i for i in remaining if int(new['bits'], 16) >> (new['width'] - 1 - i) & 1]
        actual_fields.append(dict(scope=t['scope'], checksum=t['checksum'], name=t['name'], before_missing=remaining, gained=gained))
    require(fields == actual_fields and sum(len(t['gained']) for t in fields) == q['raw_gain']['typed_target_new_directions'], 'Exact measured target directions')
    positive(delta, fields); dedup = historical_dedup(base, ledger, authority); life.check(pins)
    retained = {Path(p).name: life.read_bound(Path(p), sha) for p, sha in base['output_pins'].items()
        if Path(p).parent == BASE and Path(p).suffix == '.json' and ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    values = dict(retained, **{'single-bits.json': single, 'combined-bits.json': after, 'raw-delta.json': delta,
        'csr-satp-sepc-toggle-gain.json': dict(baseline=786, fields=fields, new_serialized_directions=q['raw_gain']['typed_target_new_directions'], official_percentage_claimed=False),
        'elf-ledger-dedup.json': dedup, 'evidence-pins.json': pins,
        'status.json': dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', coverage_admitted=True, aggregate_passed=787,
            baseline=786, exact786_prefix=True, full_OR_instances=6162, unique_new_vdb=True, duplicate_ELF=False,
            full_scalar_ISA_verified=True, full_scalar_memory_verified=True, native_CSR_owners=30, checks=44,
            observed_bytes=336, vector_status='UNOBSERVABLE_ZERO_DESTINATIONS', vector_comparison_PASS=False,
            raw_delta=delta['metrics'], typed_target_new_directions=q['raw_gain']['typed_target_new_directions'],
            qualification_seal=qsha, closure_seal=csha, inherited_all_pins_rechecked=True,
            historical_fixed_image_only=True, new_RTL_signoff=False, official_percentage_claimed=False)})
    return values, '\n'.join([ledger[0], *after['tests']]) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('mode', choices=('prepare', 'verify', 'admit'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--qualification-seal', required=True)
    parser.add_argument('--closure-seal', required=True); parser.add_argument('--seal'); parser.add_argument('--parent-authorized', action='store_true')
    a = parser.parse_args(); require((a.mode == 'admit') == a.parent_authorized and (a.mode != 'prepare') == bool(a.seal), 'Separate parent admission authority/seal')
    out = a.output.absolute(); require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh formal output')
    values, text = evaluate(a.qualification_seal, a.closure_seal)
    hashes = {str(out / name): hashlib.sha256((json.dumps(value, indent=2) + '\n').encode()).hexdigest() for name, value in values.items()}
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'): hashes[str(out / name)] = hashlib.sha256(text.encode()).hexdigest()
    proposal = dict(schema='CSR_SATP_SEPC_HISTORICAL787_ADMISSION_V1', output=str(out), baseline=str(BASE), baseline_seal=BASE_SHA,
        qualification=str(QUAL / 'qualification.json'), qualification_seal=a.qualification_seal, closure_seal=a.closure_seal,
        input_pins=values['evidence-pins.json'], output_pins=hashes, coverage_admitted=False)
    sidecar = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        life.save(sidecar, proposal); print('PREPARED_NOT_ADMITTED', life.digest(sidecar)); return
    require(life.read_bound(sidecar, a.seal) == proposal, 'Prepared admission drift')
    if a.mode == 'verify': print('PREPARED787_VERIFY_PASS_NO_ADMISSION'); return
    out.mkdir()
    for name, value in values.items(): life.save(out / name, value)
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
        with (out / name).open('x') as stream: stream.write(text)
    life.check(proposal['input_pins']); life.check(hashes)
    life.save(out / 'admission-manifest.json', dict(proposal, coverage_admitted=True, prepared=str(sidecar), prepared_seal=a.seal,
        authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION'))
    print('ADMITTED787', life.digest(out / 'admission-manifest.json'))


if __name__ == '__main__': main()
