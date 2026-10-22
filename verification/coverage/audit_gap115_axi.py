"""Offline four-object VCD AR/R audit, explicit missing-UVM-report boundary."""
from collections import defaultdict, deque
import json
from pathlib import Path
import re
import run_gap115_axi_capture as capture
import postprocess_gap115_events_v2 as architecture

life, require = capture.life, architecture.require
OUT = life.OUT/'gap115-axi-only-audit-20261007-01'
ROOT = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
WIDTHS = {'clk_i': 1, 'rst_ni': 1, 'axi_req_o.ar_valid': 1, 'axi_resp_i.ar_ready': 1,
          'axi_req_o.ar.id': 4, 'axi_req_o.ar.addr': 64, 'axi_req_o.ar.len': 8,
          'axi_req_o.ar.size': 3, 'axi_req_o.ar.burst': 2, 'axi_req_o.r_ready': 1,
          'axi_resp_i.r_valid': 1, 'axi_resp_i.r.id': 4, 'axi_resp_i.r.last': 1,
          'axi_resp_i.r.resp': 2, 'axi_resp_i.r.data': 128}


def markers(text):
    lines = text.splitlines()
    expected = ['GAP115_AXI_OBJECT '+ROOT+'.'+name for name in ('clk_i', 'rst_ni', 'axi_req_o', 'axi_resp_i')]
    actual = [line for line in lines if line.startswith('GAP115_AXI_OBJECT ')]
    require(actual == expected and lines.count('GAP115_AXI_FOUR_OBJECTS_READY') == 1 and
            not any(line.startswith('GAP115_AXI_CAPTURE_ERROR') or re.match(r'^(?:Error-|UCLI_ERROR)', line)
                    for line in lines), 'Actual UCLI four-object setup differs')
    return dict(objects=actual, ready_markers=1, echoed_script_not_treated_as_executed=True)


def vcd(path):
    """Strict subset emitted by pinned vpd2vcd: scopes, scalars, vectors and timestamps."""
    scopes, declarations, ids = [], {}, {}
    state, changes = {}, {}; time = 0; last = -1; body = False; block = None; scale = []
    with path.open() as stream:
        for raw in stream:
            line = raw.strip()
            if not line: continue
            if not body:
                if block:
                    if block == 'timescale': scale.extend(line.replace('$end', '').split())
                    if '$end' in line: block = None
                    continue
                if line.startswith('$scope '): scopes.append(line.split()[2])
                elif line.startswith('$upscope'):
                    require(bool(scopes), 'VCD scope underflow'); scopes.pop()
                elif line.startswith('$var '):
                    parts = line.split(); width, code, name = int(parts[2]), parts[3], parts[4]
                    full = '.'.join(scopes+[name.lstrip('\\')])
                    require(full not in declarations and width > 0, 'Duplicate/invalid VCD declaration')
                    declarations[full] = dict(width=width, code=code, type=parts[1]); ids[code] = width
                elif line.startswith('$enddefinitions'):
                    require(not scopes and ''.join(scale) == '100fs', 'VCD hierarchy/time precision differs')
                    for name, width in WIDTHS.items():
                        require(declarations.get(ROOT+'.'+name, {}).get('width') == width,
                                'Missing/incorrect named waveform field: '+name)
                    body = True
                    yield 'declarations', declarations
                elif line.startswith('$timescale'):
                    scale.extend(line[len('$timescale'):].replace('$end', '').split())
                    if '$end' not in line: block = 'timescale'
                elif line.startswith(('$comment', '$date', '$version')):
                    if '$end' not in line: block = 'metadata'
                else: require(line == '$end', 'Unknown VCD header directive')
                continue
            if line.startswith('#'):
                new = int(line[1:]); require(new > last and new >= time, 'Nonmonotonic VCD time')
                if changes:
                    before = dict(state); state.update(changes)
                    yield time, before, dict(state)
                    changes = {}
                last, time = new, new
            elif line in ('$dumpvars', '$end'): continue
            elif line.startswith(('b', 'B')):
                fields = line[1:].split(); require(len(fields) == 2, 'Malformed VCD vector')
                bits, code = fields
                require(code in ids and set(bits.lower()) <= set('01xz') and len(bits) <= ids[code], 'Unknown VCD vector')
                changes[code] = bits.lower().rjust(ids[code], bits[0].lower() if bits[0].lower() in 'xz' else '0')
            elif line[0] in '01xXzZ':
                code = line[1:]; require(code in ids and ids[code] == 1, 'Unknown VCD scalar')
                changes[code] = line[0].lower()
            elif line.startswith(('r', 'R')):
                require(line.split()[-1] in ids, 'Unknown real VCD metadata')
            else: raise ValueError('Unsupported VCD directive/value: '+line[:80])
    require(body and last >= 0, 'Truncated VCD')
    if changes:
        before = dict(state); state.update(changes)
        yield time, before, dict(state)


def read_bursts(path, address, expected_data):
    iterator = iter(vcd(path)); _, declarations = next(iterator)
    codes = {name: declarations[ROOT+'.'+name]['code'] for name in WIDTHS}
    def value(state, name):
        bits = state.get(codes[name], 'x')
        require(set(bits) <= set('01'), 'Unknown active waveform field: '+name)
        return int(bits, 2)
    pending = defaultdict(deque); phases = [dict(ar=0, r_beats=0, completed=0, aborted=0)]
    records = []; covered = set(); reset_times = []; phase = 0; previous_rise = None; periods = set()
    held_ar = held_r = None; sampled = 0; end_time = 0
    for time, before, after in iterator:
        end_time = time
        old_reset, new_reset = before.get(codes['rst_ni']), after.get(codes['rst_ni'])
        if old_reset == '1' and new_reset == '0':
            require(phase == 0 and phases[0]['ar'] == 1 and bool(pending), 'Reset not following first accepted AR')
            for queue in pending.values():
                for burst in queue:
                    burst['aborted_at'] = time; phases[0]['aborted'] += 1
            pending.clear(); reset_times.append(time); held_ar = held_r = None
        elif reset_times and old_reset == '0' and new_reset == '1':
            require(phase == 0 and len(reset_times) == 1, 'Multiple reset release')
            reset_times.append(time); phase = 1
            phases.append(dict(ar=0, r_beats=0, completed=0, aborted=0))
        if before.get(codes['clk_i']) != '0' or after.get(codes['clk_i']) != '1': continue
        if previous_rise is not None: periods.add(time-previous_rise)
        previous_rise = time
        if before.get(codes['rst_ni']) != '1': continue
        sampled += 1
        av, ready, rv, rready = [value(before, name) for name in
            ('axi_req_o.ar_valid', 'axi_resp_i.ar_ready', 'axi_resp_i.r_valid', 'axi_req_o.r_ready')]
        ar = tuple(value(before, 'axi_req_o.ar.'+name) for name in ('id', 'addr', 'len', 'size', 'burst')) if av else None
        response = tuple(value(before, 'axi_resp_i.r.'+name) for name in ('id', 'last', 'resp', 'data')) if rv else None
        require(held_ar is None or ar == held_ar, 'AR payload/valid changed under backpressure')
        require(held_r is None or response == held_r, 'R payload/valid changed under backpressure')
        held_ar = ar if av and not ready else None; held_r = response if rv and not rready else None
        if av and ready:
            ident, start, length, size, mode = ar
            require(size == 4 and mode == 1 and start % 16 == 0 and address <= start and
                    start+16*(length+1) <= address+1024 and (start & 4095)+16*(length+1) <= 4096,
                    'Unexpected read burst address/size/mode/range')
            burst = dict(phase=phase, id=ident, address=start, beats=length+1, received=0, accepted_at=time)
            records.append(burst); pending[ident].append(burst); phases[phase]['ar'] += 1
        if rv and rready:
            ident, last_bit, resp, data = response
            require(ident in pending and bool(pending[ident]), 'Orphan/wrong-ID R response')
            burst = pending[ident][0]
            require(resp == 0 and data == expected_data and last_bit == int(burst['received'] == burst['beats']-1),
                    'R response/data/RLAST differs')
            if phase == 1:
                offset = burst['address']+16*burst['received']-address
                require(offset not in covered, 'Duplicate restored read beat'); covered.add(offset)
            burst['received'] += 1; phases[phase]['r_beats'] += 1
            if last_bit:
                burst['completed_at'] = time; pending[ident].popleft(); phases[phase]['completed'] += 1
                if not pending[ident]: del pending[ident]
    require(len(reset_times) == 2 and len(periods) == 1 and reset_times[1]-reset_times[0] == 4*next(iter(periods)),
            'One exact four-cycle reset required')
    require(phase == 1 and not pending and phases[0]['ar'] == phases[0]['completed']+phases[0]['aborted'] and
            phases[0]['aborted'] == 1 and phases[1]['ar'] == phases[1]['completed'] > 0 and
            phases[1]['aborted'] == 0 and covered == set(range(0, 1024, 16)) and end_time > reset_times[1],
            'Reset abort/restored1024-byte read/final drain incomplete')
    return dict(status='EXACT_AR_R_RESET_ABORT_NORMAL_DRAIN_PASS', phases=phases, bursts=records,
                reset_times_100fs=reset_times, clock_period_100fs=next(iter(periods)),
                restored_bytes=1024, sampled_active_edges=sampled, end_time_100fs=end_time,
                field_mapping={name: declarations[ROOT+'.'+name] for name in WIDTHS},
                preedge_sampling=True, uvm_check_report_pass=False)


def collect():
    require(not (OUT/'qualification.json').exists() and not (OUT/'failure.json').exists(), 'Fresh audit only')
    prepared = capture.OUT.with_name(capture.OUT.name+'.prepared.json')
    record = life.read_bound(prepared, 'fa075771da77998d712daa5fb59743228c4c6a31ced2af747ff2d705a7d75e86')
    pins = life.merge_pins(record['pins'], {str(prepared): life.digest(prepared)})
    status = json.loads((capture.OUT/'simulation-status.json').read_bytes())
    require(status['returncode'] == 0, 'Simulator not successful terminal')
    observed = json.loads((capture.OUT/'manifest.json').read_bytes())
    require(observed['command'] == record['command'] and observed['old_manifest_seal'] == capture.OLD_SHA,
            'Actual command/old immutable origin differs')
    old_q = architecture.OUT
    old_pins = life.read_bound(old_q/'input-pins.json', 'bc9f36398145c0fe465a3dd40b2b9b929aea5db946d5c52a06c2c53887ed2354')
    pins = life.merge_pins(pins, old_pins)
    pins = life.merge_pins(pins, {str(old_q/'qualification.json'):
        '39ff705a889940f8c10c48f165ff8f4f0dd66ee6072607a3167b4fcf93d04bb7'})
    sourcebook = life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    sources = life.read_bound(sourcebook, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    for rel in ('hardware/src/ara_soc.sv', 'hardware/src/ara_system.sv', 'hardware/src/ara.sv',
                'hardware/tb/ara_tb.sv', 'hardware/deps/axi/include/axi/typedef.svh', 'hardware/deps/axi/src/axi_pkg.sv'):
        path = life.ROOT/rel; pins = life.merge_pins(pins, {str(path): sources[str(path)]})
    artifacts = [capture.OUT/name for name in ('manifest.json', 'simulation-status.json', 'capture-failure.json',
        'console.log', 'run.vcs.log', 'commit_trace.csv', 'vector_trace.csv', 'axi-only.vpd')]
    artifacts += [OUT/'axi-only.vcd', Path(__file__).resolve(), Path(__file__).with_name('test_audit_gap115_axi.py')]
    reader = architecture.run.shared.template.s.LLVM/'llvm-readelf'
    artifacts.append(reader)
    for path in artifacts: pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    try:
        setup = markers((capture.OUT/'console.log').read_text()); life.save(OUT/'setup-audit.json', setup)
        # Exact native traces give the same full architecture oracle, not a new simulated-ISA claim.
        for name in ('commit_trace.csv', 'vector_trace.csv'):
            require(life.digest(capture.OUT/name) == old_pins[str(capture.OLD/name)], 'Architectural trace equivalence differs')
        pre = life.read_bound(architecture.run.PRE/'preflight.json', pins[str(architecture.run.PRE/'preflight.json')])
        cf, cr = architecture.run.reset.read_csv(capture.OUT/'commit_trace.csv')
        vf, vr = architecture.run.reset.read_csv(capture.OUT/'vector_trace.csv')
        epochs, _ = architecture.run.reset.split_epochs(cr, vr)
        original_audit = architecture.run.reset.check_real_uvm_log(capture.OUT/'run.vcs.log', require_events=True,
            require_backend=True, require_axi=True, vector_trace=capture.OUT/'vector_trace.csv', reset_kind='read')
        life.save(OUT/'uvm-original-contract-audit.json', original_audit)
        event_audit = architecture.events_audit((capture.OUT/'run.vcs.log').read_text(), epochs, original_audit, pre['symbols'])
        life.save(OUT/'event-audit.json', event_audit)
        address = architecture.run.shared.template.s._elf_symbol(architecture.run.PRE/'input.elf', reader, 'source')+128
        axi = read_bursts(OUT/'axi-only.vcd', address, 0x123456789abcdef0*(1+(1 << 64)))
        life.save(OUT/'axi-audit.json', axi); life.check(pins); life.save(OUT/'evidence-pins.json', pins)
        life.save(OUT/'qualification.json', dict(status='GAP115_FOCUSED_AXI_AND_TRACE_EQUIVALENT_ARCHITECTURE_PASS_NOT_ADMITTED',
            architecture_reference=str(old_q/'qualification.json'), exact_commit_and_vector_bytes_equal=True,
            software_checks=679, restored_vrf_bytes=4096, recovery_vector_compared_bytes=7168,
            axi_burst_conservation_verified=True, uvm_check_report_pass=False, original_failures_preserved=True,
            coverage_admitted=False, output_pins={str(p): life.digest(p) for p in OUT.iterdir() if p.is_file()}))
    except Exception as exc:
        life.save(OUT/'failure.json', dict(reason=str(exc), coverage_admitted=False)); raise


if __name__ == '__main__': collect()
