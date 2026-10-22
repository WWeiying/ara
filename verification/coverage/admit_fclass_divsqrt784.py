"""Prepare exact783+qualified matrix; admission requires separate parent approval."""
from pathlib import Path
from types import FunctionType
import admit_c910_float_edge_initialized as framework
import collect_fclass_divsqrt783 as case
import collect_fclass_divsqrt783_store75 as successor

life, require, runner = case.life, case.require, case.runner
bitmap, toggle = runner.template.inherited.bitmap, runner.template.inherited.toggle
QUAL = life.OUT / 'fclass-divsqrt783-qualified-agent-20261008-02/qualification.json'
QUAL_SHA = '847a1483c8f02b27e32e07abec9b10684218b36d8ac1dffac4a4e61927a9985b'
CLOSURE = QUAL.parent / 'store75-closure.json'
CLOSURE_SHA = '217b3858b56b19744990b0398756f51ae0e2b76f29e3271e1608d1b5ddbc77ee'
RUN = life.OUT / 'fclass-divsqrt783-old-image-agent-20261008-01'
RUN_SEAL = 'dfc6b43127ef5053bc0164280690451232687a2a6b66dea3af296ac2fcbce153'
COUNTS = dict(line=1892, cond=2023, branch=2155, fsm=92)


def joint_authority(q, c, proof):
    require(q['status'] == 'FCLASS_DIVSQRT783_FULL_ARCHITECTURE_NATIVE_RAW_QUALIFIED_NOT_ADMITTED'
        and q['run'] == str(RUN) and q['prepared_seal'] == RUN_SEAL and q['coverage_admitted'] is False
        and q['RTL_modified'] is False and q['EDA_launched'] is False, 'Exact core qualification')
    require(c['status'] == 'FCLASS_DIVSQRT783_STORE75_FULL_SUCCESSOR_QUALIFIED_NOT_ADMITTED'
        and c['core_qualification'] == str(QUAL) and c['core_qualification_sha'] == QUAL_SHA
        and c['original_collector_sha'] == successor.ORIGINAL_SHA and c['original_checks_preserved'] is True
        and c['core_qualification_unchanged'] is True and c['coverage_admitted'] is False
        and c['RTL_modified'] is False and c['EDA_launched'] is False, 'Exact joint successor authority')
    require(all(c['input_pins'].get(p) == h for p, h in q['input_pins'].items())
        and c['input_pins'].get(str(QUAL)) == QUAL_SHA, 'Closure retains every core obligation')
    for name, sha in (('collect_fclass_divsqrt783_store75.py', '434ea1cafcc383059fe097b62e1a7a62ed2615fa29365f22e76528998c15e66d'),
        ('test_collect_fclass_divsqrt783_store75.py', '22db0aeab685591e9aa7b17b0fe736dd8d85c16d9db571709ebe198811e65c4f')):
        require(c['input_pins'].get(str(Path(__file__).with_name(name))) == sha, 'Reviewed successor helper/tests')
    proof_path = QUAL.parent / 'store75-context-proof.json'
    require(c['proof'] == str(proof_path) and c['input_pins'].get(str(proof_path)) == c['proof_sha']
        and proof['status'] == 'EXACT75_RAW_OWNED_STORE_CONTEXT_RESTORED' and proof['store_count'] == len(proof['records']) == 75
        and proof['changes_only'] == ['eew', 'vl', 'vstart'] and proof['no_writer_or_byte_filtered'] is True, 'Complete owned store proof')
    require(len({r['arch_seq'] for r in proof['records']}) == 75 and all(r['cell'] == i
        and r['before'] == dict(eew=None, vl=None, vstart=None)
        and r['after'] == dict(eew=1 + i // 25, vl=16 >> (i // 25), vstart=0)
        and 0 <= r['vid'] < 8 and r['alloc_cycle'] <= r['done_cycle'] for i, r in enumerate(proof['records'])), 'All75 metadata-only cells')
    case.vector_gate(q['vector'])
    require(len(q['vector']['instructions']) == 228 and all(r['status'] == 'PASS' for r in q['vector']['instructions'])
        and q['native']['operations'] == dict(load_a=75, load_b=75, store=75, arithmetic=75)
        and q['native']['initialization_bytes'] == 3072 and q['native']['active_bytes'] == 7200
        and len(q['native']['writers']) == 225 and q['native']['skip'] == 0, 'All native operations and initialized VRF')
    require(q['signature'] == dict(checks=2251, cases=75, failures=0, required_read_bytes=18000, CSR_values=452)
        and q['scalar_memory'] == dict(instructions=165928, scalar_memory_accesses=30460,
            compressed_memory_accesses=19648, unmodeled_memory_effects=0), 'Full independent gold/CSR/guard/memory authority')
    require(q['lifecycle']['requests'] == q['lifecycle']['responses'] and q['lifecycle']['exceptions'] == 0
        and not q['lifecycle']['rejected_arch_seqs'] and q['lifecycle']['rejected_backend_uops'] == 0
        and q['lifecycle']['rejected_vrf_activities'] == 0, 'No rejected protocol/VRF activity')


def full_union(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 783
        and single['tests'] == [str(RUN / 'code.vdb')] and single['tests'][0] not in before['tests'], 'Exact783 unique prefix and one candidate')
    after = bitmap.combine(before, single)
    require(after['tests'] == before['tests'] + single['tests'] and len(after['tests']) == 784
        and before['design'] == single['design'] == after['design'], '784 unique exact prefix/design')
    require(set(before['metrics']) == set(single['metrics']) == set(after['metrics']) == set(COUNTS), 'Four complete metric families')
    for metric, count in COUNTS.items():
        old, add, final = (v['metrics'][metric] for v in (before, single, after))
        require(len(old) == count and set(old) == set(add) == set(final), 'All6162 exact instance keys')
        for scope, a in old.items():
            b, c = add[scope], final[scope]
            require((a['width'], a['checksum']) == (b['width'], b['checksum']) == (c['width'], c['checksum']), 'Native width/checksum')
            aa, bb, cc = (int(r['bits'], 16) for r in (a, b, c))
            require(min(aa, bb, cc) >= 0 and max(aa, bb, cc).bit_length() <= a['width']
                and cc == aa | bb and cc & aa == aa, 'Independent bounded OR/all historical bits retained')
    return after


def evaluate(qualification, qsha, base_dir, bsha):
    require((qualification, qsha, base_dir, bsha) == (QUAL, QUAL_SHA, runner.BASE, runner.BASE_SHA), 'Fixed reviewed core/closure and formal783 only')
    q = life.read_bound(QUAL, QUAL_SHA); c = life.read_bound(CLOSURE, CLOSURE_SHA)
    life.check(q['input_pins']); life.check(c['input_pins'])
    proof = life.read_bound(Path(c['proof']), c['proof_sha']); joint_authority(q, c, proof)
    _, actual_proof = successor.actual_store_proof(RUN)
    require(actual_proof == proof, 'Independent actual75 raw store replay equals sealed proof')
    pre = runner.preflight(); reference = case.reference_prefix(pre)
    case.common.scalar_exact(q['scalar'], case.common.reference_counts(reference, pre['symbols']))
    record = RUN.with_name(RUN.name + '.prepared.json'); manifest = life.read_bound(record, RUN_SEAL)
    require(manifest == runner.prepare(RUN, existing=True) and case.terminal(RUN, manifest) == q['terminal'], 'Executed exact frozen image/ELF/900s terminal')
    base, before, ledger = runner.baseline()
    life.check(base['input_pins']); life.check(base['output_pins'])
    require(base['output'] == str(base_dir), 'Formal783 output identity')
    status = life.read_bound(base_dir / 'status.json', base['output_pins'][str(base_dir / 'status.json')])
    require(status['coverage_admitted'] is True and type(status['aggregate_passed']) is int
        and status['aggregate_passed'] == 783, 'Authoritative783 status')
    folder = RUN / 'code.vdb/snps/coverage/db/testdata' / runner.NAME
    require(list(folder.parent.iterdir()) == [folder], 'One native test, no failed VDB join')
    native_pins = case.reused.coverage_identity(folder, RUN, manifest, Path(ledger[0]))
    require(all(q['input_pins'].get(p) == h for p, h in native_pins.items()), 'Qualified complete5metric VDB metadata')
    inputs = QUAL.parent / 'single-inputs.txt'
    require(life.digest(inputs) == q['input_pins'][str(inputs)] and
        inputs.read_text().splitlines() == [ledger[0], str(RUN / 'code.vdb')], 'Exact one qualified VDB ledger')
    single = bitmap.collect(inputs)
    stored = life.read_bound(QUAL.parent / 'single-bits.json', q['input_pins'][str(QUAL.parent / 'single-bits.json')])
    require(single == stored and all(q['input_pins'].get(p) == h for p, h in single['input_hashes'].items()), 'Independent single-VDB recollection')
    after = full_union(before, single); delta = bitmap.delta(before, after)
    require(delta == life.read_bound(QUAL.parent / 'raw-delta783.json', q['input_pins'][str(QUAL.parent / 'raw-delta783.json')])
        and delta['metrics'] == q['raw_gain']['four_metrics'] and sum(delta['metrics'].values()) > 0, 'Actual sealed positive gain, no zero-gain admission')
    audit = framework.dedup(ledger, runner.ELF_SHA, base['input_pins'])
    require(audit['ledger_members'] == 783 and audit['duplicate'] is False
        and [r['vdb'] for r in audit['members']] == ledger[1:]
        and all(base['input_pins'].get(p) == h for p, h in audit['pins'].items()), 'Historical-only ELF/command ownership; no candidate evidence fallback')
    cache, pins = case.reused.checked_cache(); scopes = list(cache['instances'])
    old = {s: {k: r[k] for k in ('width', 'checksum', 'bits')} for s, r in cache['instances'].items()}
    prior = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(ledger[:742] == prior.read_text().splitlines(), 'Cached741 exact prefix')
    for db in ledger[742:]:
        paths = list((Path(db) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(paths) == 1, 'One admitted Toggle test per suffix')
        sample, sha = toggle.rows(paths[0], scopes)
        require(base['input_pins'].get(str(paths[0])) == sha, 'Historical Toggle SHA ownership')
        pins[str(paths[0])] = sha; old = toggle.union(old, sample)
    sample, sha = toggle.rows(folder / 'tgl.verilog.data.xml', scopes)
    require(q['input_pins'].get(str(folder / 'tgl.verilog.data.xml')) == sha, 'Qualified native Toggle SHA')
    gained = toggle.gains(old, toggle.union(old, sample))
    for extra in (base['input_pins'], base['output_pins'], q['input_pins'], c['input_pins'], native_pins, audit['pins']):
        pins = life.merge_pins(pins, extra)
    fixed = {QUAL: QUAL_SHA, CLOSURE: CLOSURE_SHA, record: RUN_SEAL,
        base_dir / 'admission-manifest.json': bsha}
    for module in (case, successor, runner, framework, bitmap, toggle):
        path = Path(module.__file__).resolve(); fixed[path] = life.digest(path)
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_fclass_divsqrt784.py'),
        Path(framework.dedup.__code__.co_filename).resolve()): fixed[path] = life.digest(path)
    pins = life.merge_pins(pins, {str(p): h for p, h in fixed.items()}); life.check(pins)
    retained = {}
    for path, sha in base['output_pins'].items():
        path = Path(path)
        if path.parent == base_dir and path.suffix == '.json' and ('toggle-gain' in path.name or path.name.startswith('retained-')):
            retained[path.name] = life.read_bound(path, sha)
    products = dict(retained, **{'combined-bits.json': after, 'single-bits.json': single, 'raw-delta.json': delta,
        'fclass-toggle-gain.json': dict(baseline=783, gained=gained, new_raw_slots=sum(map(len, gained.values())),
            qualified_dynamic_target_slots=q['raw_gain']['target_new_slots'], official_percentage_claimed=False),
        'elf-ledger-dedup.json': audit, 'evidence-pins.json': pins,
        'status.json': dict(aggregate_passed=784, coverage_admitted=True, baseline=783, exact_previous_prefix=True,
            full_OR_metric_instances=6162, raw_delta=delta['metrics'], unique_new_vdb=True, duplicate_ELF=False,
            qualification_mode='FULL_ORDINARY_RVV_SPIKE_SCALAR_MEMORY_NATIVE_CSR_GUARDS_WITH_STORE75_CLOSURE',
            corequal_seal=QUAL_SHA, closure_seal=CLOSURE_SHA, all_scalar_native_memory_CSR_lifecycle_verified=True,
            historical_fixed_image_only=True, new_RTL_signoff=False, official_percentage_claimed=False)})
    return products, '\n'.join([ledger[0], *after['tests']]) + '\n'


def main():
    # Reuse the unchanged prepare/verify/explicit-parent-admit publication lifecycle.
    FunctionType(framework.main.__code__, dict(framework.main.__globals__, evaluate=evaluate))()


if __name__ == '__main__': main()
