"""Offline formal770 plus one parent-replayed Sv39 alias run; no EDA."""
import argparse
import hashlib
import json
from pathlib import Path

import qualify_sv39_alias770_cut_metadata as qualification
from admit_stride_metadata768 import dedup

case = qualification.p
life, require = case.life, case.require
BASE = case.run.BASE
BASE_SHA = case.runner.BASE_SEAL
QUAL = life.OUT / 'sv39-alias770-cut-terminal-qualified-agent-20261007-01'
QUAL_SHA = 'ee9686be58b3b6630e50d03dd5c5ba82c44c6995c4223806358890f63ab64f1d'
REPLAY = life.OUT / 'sv39-alias770-cut-terminal-qualified-parent-20261007-01'
REPLAY_SHA = '6b5741c9eecdee77f204dd85bdbb46ea1fb45b06123ac634784ec111d3267ced'
DESIGN = Path(str(life.IMAGE) + '.vdb')
LEGACY_PLAN = 'verification/out/sv39-alias770-cut-terminal-plan-agent-20261007-01/plan.json'
LEGACY_PLAN_SHA = '36fd518f2a589cdedc5121cd92ebd8db93f1ff9dbb481b9fa03b3728d0b963f2'


def qualification_pins(pins):
    # The sealed collector stored its CLI plan spelling relative to repo root.
    # Normalize only that exact historical spelling, retaining its expected SHA.
    result = {}
    for name, expected in pins.items():
        path = Path(name)
        if not path.is_absolute():
            require(name == LEGACY_PLAN and expected == LEGACY_PLAN_SHA,
                    'Unreviewed relative qualification pin')
            path = life.ROOT / name
            require(path.resolve() == path and all(not p.is_symlink()
                    for p in (path, *path.parents)), 'Historical plan path alias')
            require(life.digest(path) == expected, 'Historical plan hash differs')
        result = life.merge_pins(result, {str(path): expected})
    return result


def contract(q):
    require(q['status'] == 'FULL_ARCHITECTURE_TRAPS_TRANSLATION_METADATA_QUALIFIED_NOT_ADMITTED'
            and q['baseline'] == 770 and q['coverage_admitted'] is False
            and q['admission_performed'] is False and q['run'] == str(case.RUN)
            and q['elf_sha256'] == case.run.ELF_SEAL, 'Exact qualified run identity')
    s = q['scalar']['scalar']
    require(s['status'] == 'TERMINAL_TOHOST_MATCH' and s['matched_instructions'] == 55215
            and s['ara_committed_instructions'] == 55215 and s['ara_retired_instructions'] == 55263
            and s['ara_trap_events'] == 48 and s['mismatch'] is None
            and s['skipped_unobservable_register_values'] == 0
            and s['stopped_at_unobservable'] is None, 'Complete scalar/trap accounting')
    require(s['complete_scalar_memory_postaudit'] == dict(instructions=55215,
            scalar_memory_accesses=8155, compressed_memory_accesses=3714,
            unmodeled_memory_effects=0), 'Complete compressed scalar memory audit')
    v = q['vector']
    require(v['status'] == 'PASS' and v['compared_instructions'] == 55
            and v['skipped_unknown_bytes'] == v['non_bit_exact_instructions'] ==
            v['unobservable_instructions'] == 0 and v['first_mismatch'] is None
            and not v['trapped_requests'] and not v['incomplete_requests']
            and not v['unretired_requests'], 'Complete vector oracle')
    require(len(v['instructions']) == 55 and all(r['status'] == 'PASS'
            and r['skipped_unknown_bytes'] == r['unknown_write_bytes'] == r['mismatch_count'] == 0
            and r['first_mismatch'] is None for r in v['instructions']), 'Every vector record exact')
    n = q['native']
    require(n['known_active_bytes'] == 7360 and n['unknown_bytes'] == 0
            and n['full_tail_checked_by_3_VRF_snapshots'] is True,
            'Required active bytes and independent full preservation')
    require(q['observations'] == dict(checks=3113, failed_checks=0, full_VRF_bytes=12288,
            full_page_phase_bytes=12288, CSR_words=21, immutable_source_bytes=40,
            full_guard_readback=True), 'Complete page/VRF/CSR/guard oracle')
    c = q['lifecycle']
    require(c['requests'] == c['responses'] == 217 and c['exceptions'] == 0
            and c['backend_uops'] == 201 and c['current_SID_owner_checked'] is True
            and c['traps'] == dict(supervisor_ecalls=48, exact_cause_pc_handler_return=True,
                                   unexpected_traps=0), 'Exact native lifecycle')
    p = q['protocol']
    require(p['requests'] == p['responses'] == 217 and all(p[k] == 0 for k in
            ('exceptions', 'protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')),
            'Complete protocol conservation')
    m = q['metadata']
    require(m['status'] == 'ACTUAL_PREEDGE48_PUSHES_ORDERED_AXI_CUT_DATA_DRAIN_PASS'
            and m['preedge_sampling'] is True and m['stores'] == m['loads'] == 48
            and m['total_internal_final_W_pushes'] == m['total_external_final_W'] == 147
            and m['all16slots_both_virtual_directions'] is True
            and m['no_retiming_or_waveform_rewrite'] is True and len(m['pushes']) == 48,
            'Exact preedge FIFO/AXI-cut complete drain')
    for phase in range(3):
        rows = [r for r in m['pushes'] if r['phase'] == phase]
        require(len(rows) == 16 and {r['pointer'] for r in rows} == set(range(16))
                and all(r['vaddr'] == case.run.reference.prior.address(phase)
                        and r['external_last_W_100fs'] > r['accepted_at_100fs'] for r in rows),
                'Every phase has16 exact translated owners')
    g = q['raw_gain']
    require(g['baseline'] == 770 and g['four_metrics']['metrics'] ==
            dict(line=0, cond=1, branch=0, fsm=0)
            and g['toggle_binary_new_positions'] == 7052 and g['binary_scope_count'] == 2989
            and g['official_percentage'] is None, 'Exact qualified raw gain only')


def replay_equal(q, replay):
    contract(replay)
    require(set(q) == set(replay) and
            {k: v for k, v in q.items() if k != 'pins'} ==
            {k: v for k, v in replay.items() if k != 'pins'}, 'Complete parent replay differs')


def union(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 770
            and single['tests'] == [str(case.RUN / 'code.vdb')]
            and single['tests'][0] not in before['tests'], 'Exact770 plus unique candidate VDB')
    after = case.bitmap.combine(before, single)
    count = 0
    require(set(before['metrics']) == set(single['metrics']) == set(case.bitmap.METRICS),
            'Complete four-metric population')
    for metric, rows in before['metrics'].items():
        require(set(rows) == set(single['metrics'][metric]) == set(after['metrics'][metric]),
                'Complete scope population')
        for scope, old in rows.items():
            new, merged = single['metrics'][metric][scope], after['metrics'][metric][scope]
            require(int(merged['bits'], 16) == int(old['bits'], 16) | int(new['bits'], 16),
                    'Independent raw OR')
            count += 1
    require(count == 6162 and after['tests'] == before['tests'] + single['tests']
            and len(set(after['tests'])) == 771, 'Full6162 OR/770prefix/771unique')
    return after


def measured_toggle(q, ledger, pins):
    cachepath = case.toggle.frozen.CACHE
    cache = life.read_bound(cachepath, case.toggle.frozen.CACHE_SHA)
    require(pins.get(str(cachepath)) == case.toggle.frozen.CACHE_SHA, 'Pinned Toggle cache')
    prefix = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    life.check(cache['input_pins'])
    require(ledger[:742] == prefix.read_text().splitlines(), 'Exact741 cache prefix')
    before = {s: {k: r[k] for k in ('width', 'checksum', 'bits')}
              for s, r in cache['instances'].items()}
    scopes = list(before)
    for name in ledger[742:]:
        files = list((Path(name) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'Unique historical Toggle member')
        rows, sha = case.toggle.t.rows(files[0], scopes)
        require(pins.get(str(files[0])) == sha, 'Sealed historical Toggle bytes')
        before = case.toggle.t.union(before, rows)
    member = case.RUN / 'code.vdb/snps/coverage/db/testdata' / case.run.NAME
    rows, sha = case.toggle.t.rows(member / 'tgl.verilog.data.xml', scopes)
    require(pins.get(str(member / 'tgl.verilog.data.xml')) == sha, 'Sealed candidate Toggle bytes')
    after = case.toggle.t.union(before, rows)
    gains = []
    for scope, old in before.items():
        bits = int(after[scope]['bits'], 16) & ~int(old['bits'], 16)
        if bits:
            gains.append(dict(scope=scope, new_binary_positions=bin(bits).count('1'),
                width=old['width'], checksum=old['checksum'], positions=[i for i, c in
                enumerate(format(bits, '0%db' % old['width'])) if c == '1']))
    require(gains == q['raw_gain']['toggle_binary_instances'] and
            sum(r['new_binary_positions'] for r in gains) == 7052,
            'Independent exact binary Toggle gain positions')


def evaluate(replay_path, replay_seal):
    require(replay_path == REPLAY and replay_seal == REPLAY_SHA, 'Approved parent replay identity')
    qpath, rpath = QUAL / 'qualification.json', replay_path / 'qualification.json'
    q = life.read_bound(qpath, QUAL_SHA)
    replay = life.read_bound(rpath, replay_seal)
    contract(q)
    replay_equal(q, replay)
    pins = life.merge_pins(qualification_pins(q['pins']), qualification_pins(replay['pins']))
    pins = life.merge_pins(pins, {str(qpath): QUAL_SHA, str(rpath): replay_seal})
    basepath = BASE / 'admission-manifest.json'
    base = life.read_bound(basepath, BASE_SHA)
    require(base['coverage_admitted'] is True and base['output'] == str(BASE), 'Formal770 admission')
    pins = life.merge_pins(pins, life.merge_pins(base['input_pins'], base['output_pins']))
    pins = life.merge_pins(pins, {str(basepath): BASE_SHA})
    life.check(pins)
    before = life.read_bound(BASE / 'combined-bits.json', pins[str(BASE / 'combined-bits.json')])
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    require(ledger == [str(DESIGN), *before['tests']] and len(set(ledger)) == 771,
            'Formal770 exact design/input prefix')
    inputs = QUAL / 'candidate-inputs.txt'
    require(inputs.read_text().splitlines() == [str(DESIGN), str(case.RUN / 'code.vdb')],
            'Exact candidate input identity')
    single = case.bitmap.collect(inputs)
    require(all(pins.get(p) == h for p, h in single['input_hashes'].items()), 'Sealed native singleton')
    require(all(pins.get(str(DESIGN / 'snps/coverage/db' / p)) == h
                for p, h in single['design'].items()), 'Sealed design/shape')
    after = union(before, single)
    delta = case.bitmap.delta(before, after)
    require(delta == q['raw_gain']['four_metrics'], 'Qualified four-metric delta')
    for name, expected in [('candidate-bits.json', single), ('combined-bits.json', after)]:
        path = QUAL / name
        require(json.loads(path.read_bytes()) == expected, 'Saved qualification bitmap differs')
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    pins = life.merge_pins(pins, {str(inputs): life.digest(inputs)})
    member = case.RUN / 'code.vdb/snps/coverage/db/testdata' / case.run.NAME
    folders = list(member.parent.iterdir())
    require(folders == [member], 'Exact native member population')
    info = qualification.checked.siminfo_exact(case.toggle.t.xml(member / 'siminfo.xml'),
                                               case.run.command(case.RUN))
    require(info == q['raw_gain']['native_end'], 'Exact VDB command/workdir/start/finish')
    measured_toggle(q, ledger, pins)
    elf = dedup(ledger, q['elf_sha256'], pins)
    require(elf['ledger_members'] == 770 and not elf['duplicate'], 'Unique sealed ELF')
    elf['baseline'] = 770
    pins = life.merge_pins(pins, elf['pins'])
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_sv39_alias771.py'),
                 Path(dedup.__code__.co_filename).resolve()):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    status = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', coverage_admitted=True,
        aggregate_passed=771, baseline=770, new_passed=1, exact770_prefix=True,
        full_OR_instances=6162, unique_new_vdb=True, duplicate_ELF=False,
        full_scalar_ISA_verified=True, compressed_scalar_memory_verified=True,
        full_vector_verified=True, required_active_vector_bytes=7360,
        supervisor_ecalls=48, full_VRF_snapshot_bytes=12288, full_page_phase_bytes=12288,
        source_guard_bytes=40, CSR_words=21, actual_translated_FIFO_pushes=48,
        all16slots_three_phases=True, target_new_binary_toggle_positions=7052,
        raw_delta=delta['metrics'], official_percentage_claimed=False,
        RTL_changed=False, new_simulation=False, qualification=str(qpath),
        qualification_seal=QUAL_SHA, parent_replay=str(rpath), parent_replay_seal=replay_seal)
    return {'combined-bits.json': after, 'single-bits.json': single, 'raw-delta.json': delta,
            'sv39-toggle-gain.json': q['raw_gain'], 'elf-ledger-dedup.json': elf,
            'historical-pin-spelling.json': dict(original=LEGACY_PLAN,
                absolute=str(life.ROOT / LEGACY_PLAN), expected_sha256=LEGACY_PLAN_SHA,
                authority_qualifications={str(qpath): QUAL_SHA, str(rpath): replay_seal}),
            'evidence-pins.json': pins, 'status.json': status}, '\n'.join([str(DESIGN), *after['tests']]) + '\n'


def verify_admitted(out, proposal, seal):
    manifest = life.read_bound(out / 'admission-manifest.json', seal)
    record = out.with_name(out.name + '.prepared.json')
    require(manifest == dict(proposal, coverage_admitted=True, prepared=str(record),
        prepared_seal=manifest.get('prepared_seal'),
        authorization_source='EXPLICIT_PARENT_REPLAY_PASS_AND_ADMISSION_AUTHORIZATION'),
        'Complete admitted manifest differs')
    require(life.read_bound(record, manifest['prepared_seal']) == proposal,
            'Original prepared contract differs')
    life.check(proposal['input_pins'])
    life.check(proposal['output_pins'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify', 'admit'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--parent-replay', type=Path, default=REPLAY)
    p.add_argument('--parent-replay-seal', default=REPLAY_SHA)
    p.add_argument('--seal')
    p.add_argument('--parent-authorized', action='store_true')
    a = p.parse_args()
    require(a.parent_authorized == (a.mode == 'admit'), 'Separate parent admission authorization')
    out = a.output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and
            (not out.exists() or a.mode == 'verify'), 'Fresh formal771 output')
    values, text = evaluate(a.parent_replay.absolute(), a.parent_replay_seal)
    outputs = {str(out / n): hashlib.sha256((json.dumps(v, indent=2) + '\n').encode()).hexdigest()
               for n, v in values.items()}
    outputs[str(out / 'combined-inputs.txt')] = hashlib.sha256(text.encode()).hexdigest()
    proposal = dict(output=str(out), baseline=str(BASE), baseline_seal=BASE_SHA,
        qualification=str(QUAL / 'qualification.json'), qualification_seal=QUAL_SHA,
        parent_replay=str(a.parent_replay.absolute() / 'qualification.json'),
        parent_replay_seal=a.parent_replay_seal, input_pins=values['evidence-pins.json'],
        output_pins=outputs, coverage_admitted=False)
    record = out.with_name(out.name + '.prepared.json')
    if a.mode == 'verify' and out.exists():
        require(a.seal, 'Admitted manifest seal required')
        verify_admitted(out, proposal, a.seal)
        print('FORMAL771_OFFLINE_REVERIFIED', flush=True)
        return
    if a.mode == 'prepare':
        life.save(record, proposal)
        print('PREPARED771', record, life.digest(record), flush=True)
        return
    require(a.seal and life.read_bound(record, a.seal) == proposal, 'Exact prepared contract')
    if a.mode == 'verify':
        print('VERIFY_PASS_NO_ADMISSION', flush=True)
        return
    out.mkdir()
    for name, value in values.items():
        life.save(out / name, value)
    with (out / 'combined-inputs.txt').open('x') as stream:
        stream.write(text)
    life.check(proposal['input_pins'])
    life.check(outputs)
    life.save(out / 'admission-manifest.json', dict(proposal, coverage_admitted=True,
        prepared=str(record), prepared_seal=a.seal,
        authorization_source='EXPLICIT_PARENT_REPLAY_PASS_AND_ADMISSION_AUTHORIZATION'))
    print('ADMITTED771', out, life.digest(out / 'admission-manifest.json'), flush=True)


if __name__ == '__main__':
    main()
