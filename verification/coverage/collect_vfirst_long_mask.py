"""Offline full vfirst qualification and raw775 evidence; never simulate/admit."""
import argparse
import json
from pathlib import Path
import shlex
import re

import run_vfirst_long_mask as runner
import collect_opivx_vsbc_strict as common
import qualify_queue_mask_source_lifetime_terminal as control
import qualify_sv39_alias770_known_tail as memory
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log, parse_contract_summary

life, require, p = runner.life, runner.require, runner.p


def reference_prefix(pre):
    commits = p.build.parse_spike_commits(Path(pre['reference']))
    start = next(i for i, c in enumerate(commits) if c.pc == 0x80000000)
    require(start == 5, 'Exact Spike boot-ROM prefix')
    reference = commits[start:start + 9918]
    require(len(reference) == 9918 and reference[-1].memory_accesses == ((pre['symbols']['tohost'], 1),),
            'Complete architectural entry-to-tohost prefix')
    require(p.validate(Path(pre['reference']), pre['symbols']) ==
            {k: v for k, v in pre['counts'].items() if k != 'runtime'}, 'Original gold replay')
    return reference


def terminal(run, manifest):
    state = json.loads((run / 'simulation-status.json').read_bytes())
    actual = json.loads((run / 'manifest.json').read_bytes())
    started = json.loads((run / 'started.json').read_bytes())
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and
            type(state.get('returncode')) is int and state['returncode'] == 0 and
            state.get('timeout') is False and state.get('case') == runner.NAME and
            state.get('coverage_admitted') is False and state.get('admission_performed') is False,
            'Actual successful simulator terminal required, not selfcheck alone')
    require(actual == dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL') and
            started['command'] == manifest['command'] and started['input_elf'] == str(runner.ELF) and
            started['elf_sha256'] == runner.ELF_SHA and started['image'] == str(life.IMAGE) and
            started['image_sha256'] == runner.IMAGE_SHA and type(started['pid']) is int and started['pid'] > 0 and
            started['pid'] == started['process_group'] == state['pid'] and started['budget_s'] == 600 and
            started['foreground_lifetime'] is True and type(state['wall_seconds']) in (int, float) and
            state['wall_seconds'] >= 0,
            'Exact run/command/ELF/image/PID/budget binding')
    return state


def footprint(rows, symbols):
    wanted = {}
    def region(name, data):
        wanted.update({symbols[name] + i: b for i, b in enumerate(data)})
    guard = p.GUARD.to_bytes(8, 'little') * 2
    image = b''.join(guard + p.mask(pos) + guard for pos in p.POSITIONS)
    region('vfirst_source', image); region('vfirst_snapshot', image)
    region('vfirst_ledger', b''.join(v.to_bytes(8, 'little') for pos in p.POSITIONS for v in p.ledger_gold(pos)))
    required_reads = set(wanted)
    region('g75_result', (384).to_bytes(4, 'little') + bytes(4))
    region('num_failed', bytes(4)); region('vfirst_checks', (384).to_bytes(4, 'little'))
    observed, reads, terminals = {}, set(), []
    retired = [r for r in rows if r['event'] == 'retire']
    require(len(retired) == 9918 and [int(r['order']) for r in retired] == list(range(9918)),
            'Full ordered retirement population')
    for r in retired:
        word = int(r['insn'], 16)
        require(not int(r['trap']) and int(r['pc'], 16) != symbols['trap_fail'], 'Unexpected trap')
        rm, wm = int(r['mem_rmask'], 16), int(r['mem_wmask'], 16)
        access = common.scalar_memory(word)
        if access is None:
            require(not rm and not wm, 'Unknown scalar memory effect'); continue
        kind, width = access; address = int(r['mem_addr'], 16)
        mask = ((1 << width) - 1) << (address & 7)
        require(address % width == 0 and 0x80000000 <= address and address + width <= 0x80040000 and
                rm == (mask if kind == 'read' else 0) and wm == (mask if kind == 'write' else 0),
                'Memory bounds/alignment/mask')
        value = int(r['rd_wdata'] if kind == 'read' else r['mem_wdata'], 16) & ((1 << (width * 8)) - 1)
        if kind == 'read' and any(address + i in required_reads for i in range(width)):
            require(int(r['rd']) != 0, 'Required readback is unobservable')
        if kind == 'write' and address == symbols['tohost']: terminals.append((r, value))
        for i in range(width):
            if address + i in wanted:
                observed[address + i] = value >> (8 * i) & 255
                if kind == 'read': reads.add(address + i)
    require(required_reads <= reads and observed == wanted, 'Every mask/source/guard/CSR byte must match')
    require(terminals == [(retired[-1], 1)], 'Exactly final tohost1')
    operations = [r for r in retired if int(r['pc'], 16) == symbols['vfirst_scalar_op']]
    require(len(operations) == 8, 'Exactly eight retired vfirst')
    for r, pos in zip(operations, p.POSITIONS):
        rd = int(r['insn'], 16) >> 7 & 31
        require(rd != 0 and int(r['rd']) == rd and int(r['rd_wdata'], 16) == p.first_set(p.mask(pos)),
                'Exact independent first-set scalar rd')
    return dict(checks=384, failures=0, scalar_results=8, CSR_values=56,
                whole_v0_bytes=1024, source_guard_bytes=1280, required_read_bytes=len(required_reads),
                retirements=9918)


def native_state(reference, activities, mapping, symbols):
    require(all(seq in mapping for seq in activities), 'Unmapped native activity')
    loads, firsts, records, bytes_compared = 0, 0, [], 0
    for seq, index in sorted(mapping.items()):
        c = reference[index]; activity = activities.get(seq)
        load = c.pc == symbols['vfirst_mask_load']
        first = c.pc == symbols['vfirst_scalar_op']
        require(not c.vector_writes or load, 'Unexpected reference VRF writer')
        if activity is None:
            require(not load and not first, 'Missing mask/vfirst backend activity'); continue
        require(activity.instruction == c.instruction and activity.allocations > 0 and
                activity.allocations == activity.completions, 'Native opcode/lifecycle incomplete')
        if not load:
            require(not activity.writes, 'vfirst/store/config/CSR must not write VRF')
            if first: firsts += 1
            continue
        require(loads < 8 and c.vector_writes == {0: int.from_bytes(p.mask(p.POSITIONS[loads]), 'little')} and
                activity.vstart == 0 and activity.vl == 128 and activity.writes,
                'Exact native vlm context/gold')
        seen = set()
        for w in activity.writes:
            require(w.arch_seq == seq and w.instruction == c.instruction and w.source == 4 and w.eew == 0 and
                    0 < w.be <= 255 and w.be & ~w.known_be == 0 and 0 <= w.lane < 4,
                    'Native vlm owner/source/EEW/known bytes')
            for byte in range(8):
                if w.be & (1 << byte):
                    key = w.addr, w.lane, byte
                    require(key not in seen, 'Duplicate native accepted byte'); seen.add(key)
        actual = vc._architectural_bytes(activity.writes, 4, 1024)
        expected = {(0, i): v for i, v in enumerate(p.mask(p.POSITIONS[loads]))}
        require(set(actual) == set(expected) and all(actual[k][0] == v for k, v in expected.items()),
                'Exact full128-byte native v0 mask, no missing/extra writer')
        records.append(dict(arch_seq=seq, pc=c.pc, opcode=c.instruction, compared_bytes=128,
                            allocations=activity.allocations, completions=activity.completions))
        loads += 1; bytes_compared += len(actual)
    require(loads == firsts == 8 and bytes_compared == 1024, 'Complete8 loads/8 no-VRF vfirst')
    return dict(mask_loads=loads, vfirst_without_VRF_write=firsts, compared_bytes=bytes_compared,
                skipped_bytes=0, duplicate_bytes=0, native_mask_writers=records)


def native(run, reference, symbols):
    lanes, vlen, activities = vc._parse_vector_trace(run / 'vector_trace.csv')
    starts, retires, rejected = vc._parse_architecture_mapping(run / 'commit_trace.csv')
    require((lanes, vlen) == (4, 1024) and not rejected, 'Native geometry/no rejected requests')
    arch = vc._map_architecture_retires(starts, retires, rejected)
    mapping = vc._map_spike_commits(arch, reference)
    return native_state(reference, activities, mapping, symbols)


def logs(run, lifecycle):
    for path in (run / 'run.vcs.log', run / 'console.log'):
        text = path.read_text()
        require(not any(s in text for s in ('Fatal:', 'Fatal-[', 'Error:', 'Error-[',
                                            'Core Test *** FAILED')), 'Simulator/UVM failure diagnostic')
        for line in text.splitlines():
            if re.search(r'\bUVM_(ERROR|FATAL)\b', line):
                require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0+\s*', line), 'Unexpected UVM error')
    log = (run / 'run.vcs.log').read_text()
    require(log.count('Core Test *** SUCCESS ***') == 1 and not check_contract_log(run / 'run.vcs.log'),
            'Software terminal/protocol')
    contracts = [parse_contract_summary(s.strip()) for s in log.splitlines() if '[ARA_CONTRACT]' in s]
    require(len(contracts) == 1 and contracts[0] is not None and
            contracts[0]['requests'] == contracts[0]['responses'] == lifecycle['requests'] and
            all(contracts[0][k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')),
            'Zero-error complete backend protocol')
    require('Exception @' not in (run / 'trace_hart_0.log').read_text(), 'Tracer exception')


def target_gain(before, sample, targets):
    scoped = runner.toggle.gains(before, runner.toggle.union(before, sample))
    hits = [dict(scope=scope, name=t['name'], serialized_position=i)
            for scope in before for t in targets for i in t['serialized_slots'] if i in scoped[scope]]
    return dict(baseline=775, target_hits=hits, target_hit_count=len(hits), target_unhit_count=20 - len(hits),
                scoped_toggle_new_slots=sum(map(len, scoped.values())), official_percentage=None,
                native_direction_order_claimed=False), scoped


def exact_raw_union(before, single, combined):
    counts = dict(line=1892, cond=2023, branch=2155, fsm=92)
    require(set(before['metrics']) == set(single['metrics']) == set(combined['metrics']) == set(counts),
            'Exact four metric families')
    require(before['design'] == single['design'] == combined['design'] and
            len(single['tests']) == 1 and len(before['tests']) == len(set(before['tests'])) == 775 and
            single['tests'][0] not in before['tests'] and
            combined['tests'] == before['tests'] + single['tests'], 'Exact775 prefix/unique candidate/design')
    for metric, count in counts.items():
        old, new, result = (x['metrics'][metric] for x in (before, single, combined))
        require(len(old) == count and set(old) == set(new) == set(result),
                'Exact per-metric instance universe: ' + metric)
        for scope, row in old.items():
            add, final = new[scope], result[scope]
            require((row['width'], row['checksum']) == (add['width'], add['checksum']) ==
                    (final['width'], final['checksum']), 'Exact width/checksum: ' + metric + ':' + scope)
            a, b, c = (int(r['bits'], 16) for r in (row, add, final))
            require(min(a, b, c) >= 0 and max(a, b, c).bit_length() <= row['width'] and c == a | b,
                    'Exact bounded mathematical OR: ' + metric + ':' + scope)
    require(sum(counts.values()) == 6162, 'Total metric-instance records')
    return dict(metric_instance_counts=counts, metric_instance_records=6162,
                unique_hierarchy_scopes=len(set().union(*(set(r) for r in before['metrics'].values()))),
                exact_prefix_verified=True, exact_all_metric_OR_verified=True)


def gain(run, out, manifest):
    base = life.read_bound(runner.BASE / 'admission-manifest.json', runner.BASE_SHA)
    before_path = runner.BASE / 'combined-bits.json'
    before = life.read_bound(before_path, base['output_pins'][str(before_path)])
    ledger = (runner.BASE / 'combined-inputs.txt').read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 776 and before['tests'] == ledger[1:] and
            str(run / 'code.vdb') not in ledger, 'Exact775 prefix/no duplicate')
    design = Path(ledger[0])
    for name, sha in before['design'].items():
        path = design / 'snps/coverage/db' / name
        require(base['input_pins'][str(path)] == sha == life.digest(path), 'Compiled design/hash binding')
    folder = run / 'code.vdb/snps/coverage/db/testdata' / runner.NAME
    require(list(folder.parent.iterdir()) == [folder], 'Exactly one native coverage test')
    records = runner.toggle.xml(folder / 'siminfo.xml').findall('srctest')
    require(len(records) == 1 and shlex.split(records[0].get('cmdline', '')) == manifest['command'] and
            records[0].get('workdir') == str(run) and
            int(records[0].get('finishtime', '0')) > int(records[0].get('starttime', '0')) > 0,
            'Actual native command/cwd/complete witness')
    inputs = out / 'single-inputs.txt'; inputs.write_text(str(design) + '\n' + str(run / 'code.vdb') + '\n')
    single = runner.bitmap.collect(inputs)
    require(single['design'] == before['design'], 'Candidate compiled shape differs')
    combined = runner.bitmap.combine(before, single)
    require(combined['tests'] == ledger[1:] + [str(run / 'code.vdb')], 'Exact775 prefix plus unique candidate')
    union_proof = exact_raw_union(before, single, combined)
    delta = runner.bitmap.delta(before, combined)
    sample, sha = runner.toggle.rows(folder / 'tgl.verilog.data.xml', [manifest['scope']])
    result, scoped = target_gain(manifest['scoped_toggle_before'], sample, manifest['targets'])
    result.update(four_metrics=delta['metrics'], native_toggle_data_sha=sha, full_union=union_proof)
    for name, value in (('single-bits.json', single), ('proposed-combined-bits.json', combined),
                        ('raw-delta.json', delta), ('scoped-toggle-gain.json', scoped)):
        life.save(out / name, value)
    return result


def evidence_pins(run, seal, manifest):
    prepared = {str(run.with_name(run.name + '.prepared.json')): seal}
    outputs = {str(f): life.digest(f) for f in run.rglob('*') if f.is_file()}
    return life.merge_pins(life.merge_pins(manifest['pins'], prepared), outputs)


def collect(run, seal, out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh offline qualification output')
    manifest = life.read_bound(run.with_name(run.name + '.prepared.json'), seal)
    require(manifest == runner.prepare(run, existing=True), 'Reconstructed run contract/pins differ')
    life.check(manifest['pins']); terminal(run, manifest)
    pre = runner.preflight(); reference = reference_prefix(pre)
    # Hash all evidence before reading and require no change at phase end.
    pins = evidence_pins(run, seal, manifest)
    out.mkdir()
    try:
        rows = common.read_csv((run / 'commit_trace.csv').read_bytes(), common.COMMIT_FIELDS)
        vectors = common.read_csv((run / 'vector_trace.csv').read_bytes(), common.VECTOR_FIELDS)
        lifecycle = control.lifecycle(rows, vectors)
        signature = footprint(rows, pre['symbols']); logs(run, lifecycle)
        scalar = common.spike_trace.compare_commit_prefix(Path(pre['reference']), run / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'], rtl_exception_log=run / 'trace_hart_0.log',
            rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar, common.reference_counts(reference, pre['symbols']))
        exact_memory = memory.scalar_memory_exact(rows, reference)
        native_proof = native(run, reference, pre['symbols'])
        raw_gain = gain(run, out, manifest)
        pins = life.merge_pins(pins, {str(f): life.digest(f) for f in out.iterdir() if f.is_file()})
        life.check(pins)
        result = dict(status='VFIRST_FULL_SCALAR_NATIVE_MASK_CSR_RAW775_PASS_NOT_ADMITTED',
            run=str(run), prepared_seal=seal, terminal=terminal(run, manifest), scalar=scalar,
            scalar_memory=exact_memory, native=native_proof, signature=signature, lifecycle=lifecycle,
            raw_gain=raw_gain, input_pins=pins, coverage_admitted=False, RTL_modified=False, EDA_launched=False)
        life.save(out / 'qualification.json', result)
        print('QUALIFIED_NOT_ADMITTED', life.digest(out / 'qualification.json'), raw_gain, flush=True)
    except Exception as error:
        life.save(out / 'failure.json', dict(status='FAIL_OR_HOLD_NOT_ADMITTED',
            reason=type(error).__name__ + ': ' + str(error), coverage_admitted=False, no_retry=True))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True); parser.add_argument('--seal', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); collect(args.run.resolve(), args.seal, args.output.resolve())
