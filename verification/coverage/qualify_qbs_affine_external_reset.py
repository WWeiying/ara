"""Exact two-epoch affine native qualification; no Spike/custom ISA or admission claim."""
import argparse
import json
import re
import struct
import subprocess
import sys
from pathlib import Path
from types import FunctionType, SimpleNamespace

import run_qbs_affine_external_reset as run
import qualify_gap113_payload_full8 as full8
import qualify_gap113_cached_reset as epochs
import audit_external_reset_window as reset_wave
import audit_gap115_axi_v2 as vcd_parser
import postprocess_gap115_events_v2 as events
import coverage_bitmap_delta as bitmap

sys.path.insert(0, str(run.life.ROOT / 'verification/tests'))
import build_qbs_affine_slot0_preflight as recipe

life, require = run.life, run.require
BASE = life.OUT / 'external-reset-fpu-half-offline-admitted-746-agent-20261007-01'
BASE_SHA = 'edcc5b1614dd65c51c8e9c69f1ce60bb9196101eea89330c59fde05238a96ddb'
WORD = 0x0eb5045b
inherited = full8.inherited


def native():
    items = []
    for phase in (0, 1):
        w, a, gold = recipe.fixture(phase)
        require(json.loads((run.PRE / ('gold%d.json' % phase)).read_bytes()) == dict(bits=gold, flags=0),
                'Sealed independent affine gold differs')
        items.append(dict(n=8, result_bits=gold, integer_dots=[256 * (phase + 2)] * 64,
                          fflags=0, weight_image=w, activation_image=a))
    require((run.PRE / 'host-dump.log').read_bytes() == b''.join(i['weight_image'] + i['activation_image']
                                                             for i in items), 'Native host template differs')
    return items


def descriptor(n):
    require(type(n) is int and n == 8, 'Exact N8 descriptor')
    header = adapter().abi_descriptor_header(7)
    header = (header & ~(31 << 20)) | (7 << 20)
    return (header & ~(15 << 4)) | (1 << 4)


def regions(phase, symbols, data, inputs):
    item = inputs[phase]
    seed = inherited.seed_image(phase)
    actual = bytearray(seed)
    for c in range(8):
        for r in range(8):
            struct.pack_into('<I', actual, 1024 + 128*c + 4*r, item['result_bits'][8*c+r])
    before = b''.join(struct.pack('<I', 0x13570000+i) for i in range(16))
    after = b''.join(struct.pack('<I', 0x24680000+i) for i in range(16))
    desc = bytes([0xc3])*64 + struct.pack('<QQ', descriptor(8), symbols['weights'][0]+64) + bytes([0xc3])*64
    csr = struct.pack('<20Q', *[0x1234567800000000+i for i in range(4)],
                      *([8,16,0,2,8,5]*2), *[0x8765432100000000+i for i in range(4)])
    values = dict(initial=before+seed+after, actual=before+actual+after, weights=item['weight_image'],
                  activation=item['activation_image'], descriptor_packet=desc, csr_packet=csr)
    require(all(symbols[name][1] == len(blob) for name, blob in values.items()), 'Complete ELF region size differs')
    return values


def software(log):
    text = log.read_text()
    wanted = ['GAP110 command=0 checks=17 errors=0', 'GAP110 command=1 checks=17 errors=0',
              'GAP110 inspected vrf_words=2048 initial_words=2048 source_bytes=7840 csr_words=24',
              'PASSED: qbs_gap110_q3_r4_tail checks=41 errors=0',
              'PASSED: qbs_affine_slot0_cancel checks=41 errors=0']
    require(all(text.splitlines().count(line) == 1 for line in wanted) and
            text.count('Core Test *** SUCCESS ***') == 1 and
            not re.search(r'(?m)^UVM_(?:ERROR|FATAL)\b(?!\s*:\s*0\s*$)|\[ARA_CONTRACT_ERROR\]|FAIL|Error:|Fatal:|trace.*truncat', text),
            'Actual software/contract/error boundary')
    summary = [inherited.support.parse_contract_summary(line) for line in text.splitlines() if '[ARA_CONTRACT]' in line]
    require(len(summary) == 1 and summary[0] and all(summary[0][key] == 0 for key in
            ('exceptions', 'protocol_errors', 'outstanding')), 'Exact terminal contract differs')
    return summary[0]


def adapter():
    ns = dict(vars(inherited), WORD=WORD, regions=regions, software=software,
              custom_expected=full8.custom_expected, activity_bytes=full8.activity_bytes,
              runner=SimpleNamespace(PRE=run.PRE, PRE_SEAL=run.PRE_SHA,
                                     ELF=run.PRE / 'qbs_affine_slot0_cancel.elf'),
              ABI_DEP=recipe.APP / '../qbs_gap110_q3_r4_tail/../common/qbs_abi.h')
    for name in ('elf_view', 'abi_pins', 'abi_descriptor_header', 'runtime'):
        ns[name] = FunctionType(getattr(inherited, name).__code__, ns, name)
    return SimpleNamespace(**ns)


def slot_reuse(vcd, selection, release):
    relative = {name[len('ara_tb.'):] for name in (selection['ext_target'], selection['ext_guard'])}
    widths = dict(clk=1, rst_n=1, **{name: 3 if name.endswith('entry_state_q[0]') else 1 for name in relative})
    fn = FunctionType(vcd_parser.vcd.__code__, dict(vcd_parser.vcd.__globals__, ROOT='ara_tb', WIDTHS=widths))
    iterator = iter(fn(vcd)); _, declarations = next(iterator)
    state_id = declarations[selection['ext_target']]['code']
    guard_id = declarations[selection['ext_guard']]['code']
    for time, before, after in iterator:
        if time <= release:
            continue
        if before.get(guard_id) == '0' and after.get(guard_id) == '1':
            require(int(after[state_id], 2) == 0 and int(before[state_id], 2) == selection['ext_value'],
                    'First slot reuse did not change retained target state to DOT')
            return dict(time=time, retained_state=selection['ext_value'], allocated_state=0, slot=0)
    raise ValueError('No post-reset slot0 allocation')


def selected_wave(source, output, selection):
    require(selection == run.configuration(next(name for name in run.STAGES
            if run.STAGES[name][0] == selection['ext_value'])), 'Exact slot0 observation required')
    guard = selection['ext_guard'][:-3]
    widths = {'clk': 1, 'rst_n': 1, selection['ext_target'][7:]: 3, guard[7:]: 16}
    parse = FunctionType(vcd_parser.vcd.__code__, dict(vcd_parser.vcd.__globals__, ROOT='ara_tb', WIDTHS=widths))
    iterator = iter(parse(source)); _, declarations = next(iterator)
    names = ['ara_tb.clk', 'ara_tb.rst_n', selection['ext_target'], guard]
    codes = [declarations[name]['code'] for name in names]
    with output.open('x') as stream:
        stream.write('$timescale 100fs $end\n$scope module ara_tb $end\n')
        for index, (name, width) in enumerate(zip(names, (1, 1, 3, 1))):
            label = selection['ext_guard'] if index == 3 else name
            stream.write('$var reg %d %s \\%s $end\n' % (width, 'abcd'[index], label[7:]))
        stream.write('$upscope $end\n$enddefinitions $end\n')
        for time, _, after in iterator:
            stream.write('#%d\n' % time)
            for index, code in enumerate(codes):
                bits = after.get(code, 'x')
                if index == 3:
                    bits = bits[-1]  # Proven [15:0] packed vector, exact requested bit0.
                stream.write(('b%s %s\n' if index == 2 else '%s%s\n') % (bits, 'abcd'[index]))
    return dict(source_target=names[2], target_width=3, source_guard=guard, guard_width=16,
                selected_guard_bit=0, converter_memory_objects_required=True,
                source_sha256=life.digest(source), selected_sha256=life.digest(output))


def event_audit(log, split, original):
    from ara_verify import uvm_dut as uvm
    resets = list(uvm._RESET_OBSERVED.finditer(log))
    require([int(m['epoch']) for m in resets] == [1, 2], 'Exactly two independent reset epochs required')
    cut = int(resets[1]['cycle'])
    uv, ui = uvm._events(log, '[CVXIF/EVENT]', uvm._UVM_EVENT, 10)
    cv, ci = uvm._events(log, '[ARA_CONTRACT_TRACE]', uvm._CONTRACT_EVENT, 16)
    require(not ui and not ci and uvm._event_digest(uv) == uvm._event_digest(cv) and len(cv) < 100000,
            'Independent CVXIF/contract trace missing/truncated/different')
    counts = []
    for i, (rows, _) in enumerate(split):
        selected = [e for e in cv if (e[0] < cut if i == 0 else e[0] > cut)]
        count = events.traffic(selected)
        require(count['aborted'] == 0, 'Accepted CVXIF owner remained pending at reset/terminal')
        commits = [(int(r['cycle']), r['event'], int(r['trans_id']),
                    int(r['insn'], 16) if r['event'] == 'cvx_req' else 0, int(r['trap']))
                   for r in rows if r['event'] in ('cvx_req', 'cvx_resp')]
        flatten = [(e[0], name, key, insn, exc) for e in selected for name, key, insn, exc in
                   ([('cvx_req', e[2], e[3], 0)] if e[1] else []) +
                   ([('cvx_resp', e[5], 0, e[6])] if e[4] else [])]
        require(events.relative_events(commits) == events.relative_events(flatten), 'Commit/CVXIF owners differ')
        counts.append(count)
    require(original['uvm_backend_event_sha256'] and original['uvm_backend_event_sha256'] ==
            original['vector_backend_event_sha256'], 'Independent UVM/vector backend trace differs')
    summary = original['contract_counts']
    require(summary and summary['requests'] == summary['responses'] == counts[1]['requests'] == counts[1]['responses'] and
            all(summary[k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding')), 'Final contract conservation')
    # Preserve the original checker FAIL. Only these unavailable UVM summaries and
    # shared external-pin trigger are replaced by independent concrete evidence.
    permitted = {'expected one UVM CVXIF summary, found 0',
                 'dedicated reset test lacks one matching trigger and observed reset',
                 'UVM error/fatal report summary is missing or nonzero',
                 'UVM did not complete its check/report phases',
                 'expected one backend VID summary, found 0',
                 'expected one Ara AXI read summary, found 0'}
    require(set(original['issues']) <= permitted, 'Unexpected original UVM checker diagnostic')
    return dict(cvx_epochs=counts, independent_backend_digest=original['uvm_backend_event_sha256'],
                original_checker_status_preserved=original['status'], UVM_report_claimed=False)


def collect(stage, source, seal, out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh qualification output required')
    prepared = source.with_name(source.name + '.prepared.json')
    plan = life.read_bound(prepared, seal)
    require(plan['command'] == run.command(stage, source) and plan['selection'] == run.configuration(stage),
            'Actual prepared command/stage mismatch')
    pins = life.merge_pins(plan['pins'], {str(prepared): seal})
    paths = [p for p in source.rglob('*') if p.is_file()]
    paths += [Path(__file__).resolve(), Path(__file__).with_name('test_qualify_qbs_affine_external_reset.py')]
    for module in (run, full8, inherited, epochs, reset_wave, vcd_parser, events, recipe, bitmap):
        paths.append(Path(module.__file__).resolve())
    paths += list((life.ROOT / 'verification/ara_verify').glob('*.py'))
    paths += [Path(__file__).with_name(name) for name in ('test_qualify_gap113_payload_full8.py',
              'test_qualify_gap113_cached_reset.py', 'test_audit_external_reset_window.py')]
    paths.append(life.OUT / 'qbs-affine-wave-mda-diagnostic-746-agent-20261007-01/external-reset.vcd')
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in paths})
    life.check(pins)
    require(json.loads((source / 'simulation-status.json').read_bytes())['returncode'] == 0 and
            json.loads((source / 'manifest.json').read_bytes()) == dict(plan, pins=life.merge_pins(plan['pins'], {str(prepared): seal})),
            'Executed manifest/terminal differs')
    run.markers((source / 'console.log').read_text(), stage)
    out.mkdir()
    try:
        vcd = out / 'external-reset.vcd'
        with (out / 'converter.log').open('x') as log:
            subprocess.run([str(run.focused.CONVERTER), '+includemda', '+splitpacked', str(source / 'external-reset.vpd'), str(vcd)],
                           stdout=log, stderr=subprocess.STDOUT, timeout=60, check=True)
        selected = out / 'selected-reset.vcd'
        projection = selected_wave(vcd, selected, plan['selection'])
        window = reset_wave.audit(selected, plan['selection'])
        reuse = slot_reuse(selected, plan['selection'], window['release_timestamp'])
        cf, cr = epochs.read_csv(source / 'commit_trace.csv')
        vf, vr = epochs.read_csv(source / 'vector_trace.csv')
        split, reset_cycle = epochs.split_epochs(cr, vr)
        view = adapter(); symbols, data, sites = view.elf_view(); inputs = native()
        audits = []
        for i, (commits, vectors) in enumerate(split):
            path = out / ('epoch%d' % i); path.mkdir()
            epochs.write_csv(path / 'commit_trace.csv', cf, commits)
            epochs.write_csv(path / 'vector_trace.csv', vf, vectors)
            (path / 'run.vcs.log').write_bytes((source / 'run.vcs.log').read_bytes())
            if i == 0:
                q = SimpleNamespace(WORD=WORD, inherited=inherited, activity_bytes=full8.activity_bytes)
                audit = epochs.cancelled_epoch(path, commits, vectors, q, symbols, sites)
                events.backend(commits, vectors, {audit['cancelled_arch_seq']})
            else:
                audit = view.runtime(path, symbols, data, sites, inputs)
                events.backend(commits, vectors, set())
                audit.update(status='AFFINE_M8_FULL_VRF_CSR_NATIVE_PASS_NOT_FULL_SCALAR_ISA',
                             custom_write_bytes=512, source_guard_bytes=7840, custom_preserved_vrf_bytes=7680)
            audits.append(audit)
        from ara_verify.uvm_dut import check_real_uvm_log
        original = check_real_uvm_log(source / 'run.vcs.log', require_events=True, require_backend=True,
            require_axi=True, vector_trace=source / 'vector_trace.csv', reset_kind='state')
        independent_events = event_audit((source / 'run.vcs.log').read_text(), split, original)
        book = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
        before_path = BASE / 'combined-bits.json'
        before = life.read_bound(before_path, book['output_pins'][str(before_path)])
        require(len(before['tests']) == len(set(before['tests'])) == 746, 'Not formal746')
        pins = life.merge_pins(pins, {str(BASE / 'admission-manifest.json'): BASE_SHA,
                                    str(before_path): book['output_pins'][str(before_path)]})
        (out / 'single-inputs.txt').write_text(str(life.IMAGE) + '.vdb\n' + str(source / 'code.vdb') + '\n')
        single = bitmap.collect(out / 'single-inputs.txt')
        after = bitmap.combine(before, single); delta = bitmap.delta(before, after)
        row = single['metrics']['fsm'][run.SCOPE]; old = before['metrics']['fsm'][run.SCOPE]
        require((row['checksum'], row['width']) == (old['checksum'], old['width']) == ('3794445597', 288),
                'Exact accumulator raw shape differs')
        targets = [dict(stage=name, index=index, before=bool(int(old['bits'], 16) & (1 << (287-index))),
                        single=bool(int(row['bits'], 16) & (1 << (287-index)))) for name, (_, index) in run.STAGES.items()]
        for name, value in [('wave-binding.json', projection), ('reset-window.json', window), ('slot-reuse.json', reuse), ('epoch-audits.json', audits),
                            ('original-protocol-audit.json', original), ('single-bits.json', single),
                            ('independent-event-audit.json', independent_events),
                            ('raw-delta.json', delta), ('fsm-targets.json', targets), ('evidence-pins.json', pins)]:
            life.save(out / name, value)
        life.check(pins)
        result = dict(status='QBS_AFFINE_EXACT_RESET_REUSE_TWO_EPOCH_NATIVE_PASS_NOT_ADMITTED', baseline=746,
            stage=stage, raw_delta=delta['metrics'], targets=targets, full_scalar_ISA_verified=False,
            spike_custom_ISA_PASS=False, recovery_full_vrf_bytes=8192, initial_seed_bytes=8192,
            CSR_values=24, source_guard_bytes=7840, native_active_bytes=512, checks=41,
            reset_stage_and_slot_reuse_wave_verified=True, uvm_check_report_pass=False, coverage_admitted=False,
            output_pins={str(p): life.digest(p) for p in out.rglob('*') if p.is_file()})
        life.save(out / 'qualification.json', result)
        print(json.dumps(dict(status=result['status'], seal=life.digest(out / 'qualification.json'), raw_delta=delta['metrics'])), flush=True)
    except Exception as exc:
        life.save(out / 'failure.json', dict(reason=str(exc), coverage_admitted=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=run.STAGES, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.stage, args.run.resolve(), args.seal, args.output.resolve())
