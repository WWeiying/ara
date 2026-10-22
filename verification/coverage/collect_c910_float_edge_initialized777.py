"""Strict offline floating-edge qualification and formal777 raw OR; no EDA/admit."""
import argparse
import json
from pathlib import Path
from types import FunctionType
import run_c910_float_edge_initialized777 as runner
import collect_c910_float_edge777 as frozen
import collect_c910_store_context_parent as store_adapter
import collect_vfirst_long_mask as inherited

life, require, p = runner.life, runner.require, runner.p
common, control, memory, vc = inherited.common, inherited.control, inherited.memory, inherited.vc
toggle, bitmap = runner.inherited.toggle, runner.inherited.bitmap
CACHE_SHA = '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'


def coverage_identity(folder, run, manifest, design):
    import shlex
    names = {'siminfo.xml', 'vcmArguments.xml', *{m + '.verilog.data.xml' for m in ('line', 'cond', 'branch', 'fsm', 'tgl')}}
    require({f.name for f in folder.iterdir()} == names and
        all(f.is_file() and not f.is_symlink() for f in folder.iterdir()), 'Exact five-metric raw membership')
    args = toggle.xml(folder / 'vcmArguments.xml')
    options = [x.get('vcm_opt') for x in args.iter('vcm_arg_data') if x.get('vcm_opt') is not None]
    records = toggle.xml(folder / 'siminfo.xml').findall('srctest')
    require(args.get('compvdbpath') == str(design) and len(options) == 5 and
        set(options) == {'-cm ' + m for m in ('line', 'cond', 'branch', 'fsm', 'tgl')}, 'Compiled VDB/five metrics identity')
    require(len(records) == 1 and shlex.split(records[0].get('cmdline', '')) == manifest['command']
        and records[0].get('workdir') == str(run) and records[0].get('seed') == '1'
        and records[0].get('teststatus') == 'unknown'
        and int(records[0].get('finishtime', '0')) > int(records[0].get('starttime', '0')) > 0,
        'Actual coverage command/cwd/seed/finish')
    return {str(f): life.digest(f) for f in folder.iterdir()}


def checked_cache():
    cache = life.read_bound(runner.inherited.CACHE, CACHE_SHA)
    require(bool(cache['input_pins']), 'Cache provenance must be nonempty')
    life.check(cache['input_pins'])
    return cache, life.merge_pins(cache['input_pins'], {str(runner.inherited.CACHE): CACHE_SHA})


def reference_prefix(pre):
    commits = p.build.parse_spike_commits(Path(pre['reference']))
    start = next(i for i, c in enumerate(commits) if c.pc == 0x80000000)
    require(start == 5, 'Exact reference ROM entry prefix')
    reference = commits[start:start + 36997]
    require(len(reference) == 36997 and reference[-1].memory_accesses == ((pre['symbols']['tohost'], 1),), 'Complete entry-to-tohost prefix')
    require(p.validate(Path(pre['reference']), pre['symbols']) == {k: v for k, v in pre['counts'].items() if k != 'runtime'}, 'Sealed gold replay')
    return reference


def terminal(run, manifest):
    # Frozen terminal checker depends only on runner NAME/ELF/image/budget, not the vfirst oracle.
    namespace = dict(inherited.terminal.__globals__, runner=runner)
    return FunctionType(inherited.terminal.__code__, namespace)(run, manifest)


def expected_footprint(symbols):
    wanted = {}
    def region(name, data): wanted.update({symbols[name] + i: byte for i, byte in enumerate(data)})
    for name, index in [('edge_a', 0), ('edge_b', 1), ('edge_dst', 2)]:
        image = bytearray()
        for phase in range(48):
            width = 16 << (phase // 16)
            value = p.gold(width, phase % 8, phase // 8 % 2)[index]
            image.extend(p.GUARD.to_bytes(8, 'little') * 2)
            image.extend(value.to_bytes(width // 8, 'little') * (256 // width))
            image.extend(p.GUARD.to_bytes(8, 'little') * 2)
        region(name, image)
    ledger = []
    for phase in range(48):
        fmt, rm = phase // 16, phase // 8 % 2
        flags = p.gold(16 << fmt, phase % 8, rm)[3]
        ledger.extend([16 >> fmt, 16 >> fmt, 11 + fmt * 8, 0, 0, rm * 32 + flags])
    region('edge_ledger', b''.join(value.to_bytes(8, 'little') for value in ledger))
    required_reads = set(wanted)
    region('edge_initial_ledger', b''.join(value.to_bytes(8, 'little') for value in (1024,1024,3,0,0)))
    region('g75_result', (1440).to_bytes(4, 'little') + bytes(4))
    region('num_failed', bytes(4)); region('edge_checks', (1440).to_bytes(4, 'little'))
    return wanted, required_reads


def footprint(rows, symbols, reference):
    wanted, required_reads = expected_footprint(symbols)
    observed, reads, terminals = {}, set(), []
    retired = [row for row in rows if row['event'] == 'retire']
    require(len(retired) == len(reference) == 36997 and [int(r['order']) for r in retired] == list(range(36997)), 'Full ordered retirement stream')
    for row, expected in zip(retired, reference):
        word = int(row['insn'], 16)
        require(word == expected.instruction and int(row['pc'], 16) == expected.pc and not int(row['trap'])
            and expected.pc != symbols['trap_fail'], 'Exact ELF/reference retirement identity; no trap')
        rm, wm = int(row['mem_rmask'], 16), int(row['mem_wmask'], 16)
        access = common.scalar_memory(word)
        if access is None:
            require(not rm and not wm, 'Unknown scalar memory effect'); continue
        kind, width = access; address = int(row['mem_addr'], 16)
        mask = ((1 << width) - 1) << (address & 7)
        require(address % width == 0 and 0x80000000 <= address and address + width <= 0x80040000
            and rm == (mask if kind == 'read' else 0) and wm == (mask if kind == 'write' else 0), 'Memory alignment/range/byte masks')
        value = int(row['rd_wdata'] if kind == 'read' else row['mem_wdata'], 16) & ((1 << (8 * width)) - 1)
        if kind == 'read' and any(address + i in required_reads for i in range(width)):
            require(int(row['rd']) != 0, 'Unobservable required memory read')
        if kind == 'write' and address == symbols['tohost']: terminals.append((row, value))
        for i in range(width):
            if address + i in wanted:
                observed[address + i] = value >> (8 * i) & 255
                if kind == 'read': reads.add(address + i)
    require(required_reads <= reads and observed == wanted, 'Full source/destination/guard/CSR/selfcheck footprint')
    require(terminals == [(retired[-1], 1)], 'Exactly final tohost1')
    div_pcs = {symbols['edge_div' + str(width)]: width for width in (16, 32, 64)}
    divisions = [i for i, c in enumerate(reference) if c.pc in div_pcs]
    require(len(divisions) == 48, 'Exactly48 retired FP divisions')
    flags_records = []
    for phase, start in enumerate(divisions):
        end = divisions[phase + 1] if phase < 47 else len(reference)
        matches = [i for i in range(start + 1, end) if reference[i].instruction & 127 == 0x73
            and reference[i].instruction >> 20 == 3 and reference[i].instruction >> 12 & 7 in (2, 3)
            and reference[i].instruction >> 15 & 31 == 0]
        require(len(matches) == 1, 'Exactly one post-division fcsr read')
        index = matches[0]; row = retired[index]; rd = reference[index].instruction >> 7 & 31
        width = 16 << (phase // 16); rm = phase // 8 % 2
        expected = rm * 32 + p.gold(width, phase % 8, rm)[3]
        require(div_pcs[reference[start].pc] == width and rd != 0 and int(row['rd']) == rd
            and int(row['rd_wdata'], 16) == expected, 'Every division fcsr/fflags must match')
        flags_records.append(dict(phase=phase, div_pc=reference[start].pc, fcsr_read_pc=reference[index].pc, fcsr=expected))
    return dict(checks=1440, failures=0, retirements=36997, required_read_bytes=len(required_reads),
        CSR_values=288, source_destination_guard_bytes=9216, per_division_fcsr=flags_records)


def native_state(reference, activities, mapping, symbols):
    init_pcs = {symbols['edge_initial_v' + str(base)]: base for base in (8, 16, 24)}
    init = {seq: init_pcs[reference[i].pc] for seq, i in mapping.items() if reference[i].pc in init_pcs}
    require(len(init) == 3 and set(init.values()) == {8, 16, 24}, 'All three native initialization requests')
    records = []
    for seq, base in init.items():
        activity = activities.get(seq); commit = reference[mapping[seq]]
        require(activity is not None and activity.instruction == commit.instruction and activity.use_vd
            and activity.vd == base and activity.eew == 0 and activity.vl == 1024 and activity.vstart == 0
            and activity.allocations > 0 and activity.allocations == activity.completions, 'Initialization native context/lifecycle')
        require(commit.vector_writes == {reg: 0 for reg in range(base, base + 8)}, 'Initialization independent Spike full-group zero')
        seen = set()
        for write in activity.writes:
            require(write.arch_seq == seq and write.instruction == commit.instruction and write.eew == 0
                and write.source == 0 and 0 <= write.lane < 4 and 0 < write.be <= 255
                and not write.be & ~write.known_be, 'Initialization ALU producer/known accepted bytes')
            for byte in range(8):
                if write.be & (1 << byte):
                    key = (write.addr, write.lane, byte)
                    require(key not in seen, 'Duplicate initialization byte'); seen.add(key)
        actual = vc._architectural_bytes(activity.writes, 4, 1024)
        wanted = {(reg, byte) for reg in range(base, base + 8) for byte in range(128)}
        require(set(actual) == wanted and all(value == 0 for value, write in actual.values()), 'All1024 native group bytes exactly zero')
        records.append(dict(arch_seq=seq, base_register=base, bytes=1024, compared_bytes=1024))
    proof = frozen.native_state(reference, {s:a for s,a in activities.items() if s not in init},
        {s:i for s,i in mapping.items() if s not in init}, symbols)
    proof['initialization'] = dict(requests=records, compared_bytes=3072, unknown_bytes=0)
    return proof


def native(run, reference, symbols):
    lanes, vlen, activities = vc._parse_vector_trace(run / 'vector_trace.csv')
    raw_rows = common.read_csv((run / 'vector_trace.csv').read_bytes(), common.VECTOR_FIELDS)
    activities = store_adapter.restore_stores(activities, raw_rows)
    starts, retires, rejected = vc._parse_architecture_mapping(run / 'commit_trace.csv')
    require((lanes, vlen) == (4, 1024) and not rejected, 'Exact geometry; no trapped request')
    mapping = vc._map_spike_commits(vc._map_architecture_retires(starts, retires, rejected), reference)
    proof = native_state(reference, activities, mapping, symbols)
    result = vc.compare_vector_commits(Path(runner.preflight()['reference']), run / 'commit_trace.csv', run / 'vector_trace.csv', 0x80000000)
    require(result['status'] == 'PASS' and result['stopped_at_spike_index'] is None
        and result['vector_destination_requests'] == result['prefix_vector_destination_requests'] == result['compared_instructions'] == 147
        and result['compared_bytes'] >= 7680 and result['first_mismatch'] is None and
        all(result[k] == 0 for k in ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions'))
        and not result['incomplete_requests'] and not result['unretired_requests'] and not result['trapped_requests']
        and all(r['unknown_write_bytes'] == r['skipped_unknown_bytes'] == r['mismatch_count'] == 0 for r in result['instructions']),
        'Full native accepted writes/identity transports require exact comparison; no skip')
    return dict(primary=proof, complete_vector_diff=result)


def exact_raw_union(before, single, combined):
    counts = dict(line=1892, cond=2023, branch=2155, fsm=92)
    require(set(before['metrics']) == set(single['metrics']) == set(combined['metrics']) == set(counts), 'Four exact metric families')
    require(before['design'] == single['design'] == combined['design'] and len(before['tests']) == len(set(before['tests'])) == 777
        and len(single['tests']) == 1 and single['tests'][0] not in before['tests'] and combined['tests'] == before['tests'] + single['tests'], 'Exact777 prefix/unique candidate/design')
    for metric, count in counts.items():
        old, new, final = (x['metrics'][metric] for x in (before, single, combined))
        require(len(old) == count and set(old) == set(new) == set(final), 'Per-metric instance universe')
        for scope, row in old.items():
            add, result = new[scope], final[scope]
            require((row['width'], row['checksum']) == (add['width'], add['checksum']) == (result['width'], result['checksum']), 'Exact compiled shape')
            a, b, c = (int(r['bits'], 16) for r in (row, add, result))
            require(min(a, b, c) >= 0 and max(a, b, c).bit_length() <= row['width'] and c == a | b, 'All6162 exact mathematical OR')
    return dict(metric_instance_records=6162, metric_counts=counts, exact_prefix=True, exact_OR=True)


def gain(run, out, manifest):
    base, before, ledger = runner.baseline(); design = Path(ledger[0])
    require(str(run / 'code.vdb') not in ledger, 'No duplicate VDB')
    folder = run / 'code.vdb/snps/coverage/db/testdata' / runner.NAME
    require(list(folder.parent.iterdir()) == [folder], 'Exactly one coverage test')
    metadata_pins = coverage_identity(folder, run, manifest, design)
    inputs = out / 'single-inputs.txt'; inputs.write_text(str(design) + '\n' + str(run / 'code.vdb') + '\n')
    single = bitmap.collect(inputs); combined = bitmap.combine(before, single)
    proof = exact_raw_union(before, single, combined); delta = bitmap.delta(before, combined)
    cache, input_pins = checked_cache()
    scopes = list(cache['instances'])
    old = {s: {k: r[k] for k in ('width', 'checksum', 'bits')} for s, r in cache['instances'].items()}
    prior = next(Path(path) for path in cache['input_pins'] if path.endswith('/inputs.txt'))
    require(life.digest(prior) == cache['input_pins'][str(prior)] and ledger[:742] == prior.read_text().splitlines(), 'Exact cached741 prefix')
    input_pins = life.merge_pins(input_pins, metadata_pins)
    for db in ledger[742:]:
        paths = list((Path(db) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(paths) == 1, 'One sealed suffix Toggle sample')
        sample, sha = toggle.rows(paths[0], scopes)
        require(base['input_pins'][str(paths[0])] == sha, 'Admitted suffix SHA ownership')
        input_pins[str(paths[0])] = sha; old = toggle.union(old, sample)
    sample, sha = toggle.rows(folder / 'tgl.verilog.data.xml', scopes)
    input_pins[str(folder / 'tgl.verilog.data.xml')] = sha
    new = toggle.union(old, sample); additions = toggle.gains(old, new)
    # Only non-array typed offsets; never project a handwritten LFN bit mask.
    shape_path = design / 'snps/coverage/db/shape/tgl.verilog.shape.xml'
    require(life.digest(shape_path) == base['input_pins'][str(shape_path)], 'Compiled Toggle shape SHA')
    shape = toggle.xml(shape_path); typed = []
    for definition in shape.findall('tgldef'):
        if definition.get('name', '').split(' (')[0] != 'ct_vfdsu_pack': continue
        offset = 0; fields = []
        for node in definition.find('tglshape'):
            if node.tag == 'arrays': continue
            require(node.tag in ('node', 'vectornode'), 'Known compiled Toggle object')
            width = 1 if node.tag == 'node' else abs(int(node.get('left')) - int(node.get('right'))) + 1
            fields.append((dict(node.attrib), offset, width)); offset += 2 * width
        for instance in definition:
            if instance.tag == 'tglshape': continue
            scope = instance.get('name')
            require(scope in old and old[scope]['checksum'] == definition.get('chksum') and old[scope]['width'] == offset, 'Exact scope/checksum/full typed width')
            for attrs, start, width in fields:
                hits = [position for position in additions[scope] if start <= position < start + 2 * width]
                if hits: typed.append(dict(scope=scope, field=attrs['name'], compiled_attributes=attrs,
                    checksum=definition.get('chksum'), serialized_offset=start, new_raw_slots=hits,
                    source_hypothesis=attrs['name'] in runner.SIGNALS, physical_bit_direction=None))
    for name, value in [('single-bits.json', single), ('proposed-combined-bits.json', combined),
        ('raw-delta.json', delta), ('full-toggle-gain.json', additions), ('pack-typed-gain.json', typed)]: life.save(out / name, value)
    return dict(baseline=777, four_metrics=delta['metrics'], full_union=proof,
        full_toggle_new_raw_slots=sum(map(len, additions.values())), typed_pack_fields=typed,
        raw_slots_not_official_denominator=True, official_percentage=None), input_pins


def collect(run, seal, out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh offline output')
    manifest = life.read_bound(run.with_name(run.name + '.prepared.json'), seal)
    require(manifest == runner.prepare(run, existing=True), 'Original run pins/contract exact')
    require(life.digest(Path(frozen.__file__).resolve()) == 'ffb6404656a6174f43d619281a88870d4b4d7039249ef501219c9360ce772eb3', 'Frozen original collector identity')
    terminal(run, manifest); pre = runner.preflight(); reference = reference_prefix(pre)
    pins = inherited.evidence_pins(run, seal, manifest)
    for module in (runner, p, inherited, common, control, memory, vc, frozen, store_adapter):
        path = Path(module.__file__).resolve(); pins[str(path)] = life.digest(path)
    for name in ('collect_c910_float_edge_initialized777.py', 'test_collect_c910_float_edge_initialized777.py'):
        path = Path(__file__).with_name(name); pins[str(path)] = life.digest(path)
    life.check(pins); out.mkdir()
    try:
        rows = common.read_csv((run / 'commit_trace.csv').read_bytes(), common.COMMIT_FIELDS)
        vectors = common.read_csv((run / 'vector_trace.csv').read_bytes(), common.VECTOR_FIELDS)
        lifecycle = control.lifecycle(rows, vectors); signature = footprint(rows, pre['symbols'], reference)
        inherited.logs(run, lifecycle)
        scalar = common.spike_trace.compare_commit_prefix(Path(pre['reference']), run / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'], rtl_exception_log=run / 'trace_hart_0.log', rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar, common.reference_counts(reference, pre['symbols']))
        scalar_memory = memory.scalar_memory_exact(rows, reference)
        vector = native(run, reference, pre['symbols']); raw, gain_pins = gain(run, out, manifest)
        pins = life.merge_pins(pins, gain_pins)
        pins = life.merge_pins(pins, {str(f): life.digest(f) for f in out.iterdir() if f.is_file()}); life.check(pins)
        result = dict(status='C910_INITIALIZED_FLOAT_EDGE_FULL_SCALAR_NATIVE_CSR_RAW777_PASS_NOT_ADMITTED', run=str(run),
            prepared_seal=seal, terminal=terminal(run, manifest), scalar=scalar, scalar_memory=scalar_memory,
            native=vector, signature=signature, lifecycle=lifecycle, raw_gain=raw, input_pins=pins,
            coverage_admitted=False, EDA_launched=False, RTL_modified=False)
        life.save(out / 'qualification.json', result); print('QUALIFIED_NOT_ADMITTED', life.digest(out / 'qualification.json'), flush=True)
    except Exception as error:
        life.save(out / 'failure.json', dict(status='FAIL_OR_HOLD_NOT_ADMITTED', reason=str(error), no_retry=True)); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--seal', required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); collect(args.run.resolve(), args.seal, args.output.resolve())
