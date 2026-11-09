#!/usr/bin/env python3
"""Read-only ABBA attribution; retirement intervals are not additive stalls."""
from collections import Counter
import argparse
import csv
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path('/home/wangwy/openproject/ara_dsa/verification/performance/resident_rvv/soc_eval')
sys.path.insert(0, str(HERE))
import experiment as e

require, sha = e.require, e.sha
HELPERS = {
    HERE/'run_abba.py': '8ee469af3cd682000ac609e4ae3c2aa9c1305e51dd359bfd3ddd8fabfd31ac0e',
    HERE.parent/'analyze.py': '6794029f0ee578d1dddb5d91a1f4dc2980c16281847b1b934b80bbccdbfa798a',
}
e.contract.verify({str(p): h for p, h in HELPERS.items()})
r = e.load(HERE/'run_abba.py', 'attribute_abba_contract')
reference = e.load(HERE.parent/'analyze.py', 'attribute_retirement_parts')
QK = 'akv_experimental_qk_f16_pair_panel4'
PV = ('__wrap_akv_experimental_pv_f16_pair', 'resident_pv_prepare', 'resident_pv_rotation_body')
FMA_OPCODES = ('b2805057', 'b280d157', 'b2a05057', 'b2a0d157')


def elf_ranges(raw):
    require(len(raw) >= 64 and raw[:7] == b'\x7fELF\x02\x01\x01', 'Expected ELF64 little endian')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(h[1:4] == (2, 243, 1) and h[8] == 64 and h[11] == 64 and h[12] > 0 and
        h[6]+h[11]*h[12] <= len(raw), 'ELF/section table bounds')
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, h[6]+i*h[11]) for i in range(h[12])]
    wanted, result = {QK, *PV}, {}
    for sec in sections:
        if sec[1] != 2:
            continue
        require(sec[9] == 24 and sec[5] % 24 == 0 and sec[4]+sec[5] <= len(raw) and sec[6] < len(sections),
                'ELF symtab bounds')
        strings = sections[sec[6]]
        require(strings[1] == 3 and strings[4]+strings[5] <= len(raw), 'ELF strtab bounds')
        names = raw[strings[4]:strings[4]+strings[5]]
        for off in range(sec[4], sec[4]+sec[5], 24):
            name, info, _, index, value, size = struct.unpack_from('<IBBHQQ', raw, off)
            end = names.find(b'\0', name)
            require(name < len(names) and end >= name, 'ELF symbol name bounds')
            text = names[name:end].decode('ascii')
            if text not in wanted:
                continue
            require(text not in result and info & 15 == 2 and info >> 4 in (1, 2) and
                0 < index < len(sections) and size > 0, 'Missing/duplicate/invalid helper function')
            target = sections[index]
            require(target[2] & 4 and target[4]+target[5] <= len(raw) and
                target[3] <= value and value+size <= target[3]+target[5],
                    'Helper outside executable section')
            result[text] = (value, value+size)
    require(set(result) == wanted, 'Missing helper symtab range')
    ordered = sorted(result.values())
    require(all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:])), 'Overlapping helper symbols')
    return result


def cpu_spans(rows, ranges, markers):
    def checked_rows():
        previous = -1
        for row in rows:
            require(None not in row and all(v is not None for v in row.values()), 'Malformed commit CSV')
            cycle = int(row['cycle'])
            require(cycle >= previous, 'Nonmonotonic retirement trace')
            previous = cycle
            yield row
    raw, matched = reference.retirement_spans(checked_rows(), ranges, markers)
    result = []
    for span in raw:
        span = dict(span, helper='qk' if span['helper'] == QK else 'pv', opcodes=Counter(span['opcodes']))
        if result and result[-1]['helper'] == span['helper'] and result[-1]['end'] == span['begin']:
            result[-1]['end'] = span['end']
            result[-1]['retired'] += span['retired']
            result[-1]['opcodes'].update(span['opcodes'])
        else:
            result.append(span)
    return result, matched


def accepted_evidence(directory):
    directory = r.output_path(directory)
    resultfile = directory/'result.json'
    require(resultfile.is_file(), 'ABBA terminal PASS not available; no analysis output')
    m = json.loads(resultfile.read_text())
    require(m.get('state') == 'PASS' and m.get('kind') == 'abba' and all(m.get(k) is True for k in
        ('numerical_checked', 'independent_protocol_checked', 'post_pins_match', 'post_image_match')),
        'Independently accepted ABBA required')
    selected, pins, soc, software = r.verify_prepared(directory)
    require(m['soc_build'] == selected['soc_build'] and m['build'] == selected['build'] and
        m['smoke_admission'] == selected['smoke_admission'] and m['configuration'] == soc['configuration'] and
        m['software_sha256'] == software['elf_sha256'] == r.ABBA_ELF_SHA and
        m['image_sha256'] == sha(soc['simv']) and m['source_pins_sha256'] == sha(directory/'source-pins.json'),
        'ABBA source/software/image/admission identity mismatch')
    artifacts = {str(p): sha(p) for p in directory.rglob('*') if p.is_file() and p != resultfile and
        p.name not in ('status.json', 'service.stdout.log', 'service.stderr.log')}
    require(artifacts == m['artifacts'], 'ABBA evidence inventory drift')
    e.contract.verify(artifacts)
    for name, command, seconds in (('console', 'simulation', r.s.SIM_SECONDS), ('checker', 'protocol', r.s.PROTOCOL_SECONDS)):
        require(json.loads((directory/'work'/(name+'.command.json')).read_text()) ==
            dict(argv=selected['commands'][command], cwd=str(directory/'work'), timeout_seconds=seconds),
            'ABBA command provenance mismatch')
    log, vector = directory/'work/run.vcs.log', directory/'work/vector_trace.csv'
    text = log.read_text()
    require(m['numerical'] == r.check_numerical(text, software) and m['akv_work'] == r.check_akv(text) and
        m['vector_work'] == r.check_vectors(vector) and m['resident_work'] == e.check_resident_work(vector, text, 'abba'),
        'ABBA reconstructed correctness/work mismatch')
    proof = json.loads((directory/'work/uvm_result.json').read_text())
    r.s.check_protocol(proof, soc, software, log, vector)
    checked = r.recheck_protocol(log, vector)
    require(checked.get('status') == 'PASS' and checked.get('issues') == [] and
        all(proof.get(k) == v for k, v in checked.items()), 'ABBA protocol evidence mismatch')
    e.merge(pins, artifacts)
    e.merge(pins, {str(resultfile): sha(resultfile), **{str(p): h for p, h in HELPERS.items()},
        **{str(HERE/n): sha(HERE/n) for n in ('attribute.py', 'test_attribute.py')}})
    e.contract.verify(pins)
    return m, software, text, pins


def summarize(trials, spans, matched, resident):
    require(len(resident['pv_terminals']) == len(resident['actual_vector_writes']) == 6, 'Expected six PV services')
    output, service_index = [], 0
    for trial in trials:
        begin, returned, end = (matched[trial[k]] for k in ('begin', 'returned', 'end'))
        selected = [x for x in spans if x['begin'] < end and x['end'] > begin]
        require([x['helper'] for x in selected] == ['qk', 'pv']*3 and
            all(begin <= x['begin'] < x['end'] <= end for x in selected), 'Expected three QK/PV spans per call')
        cpu = {phase: sum(x['end']-x['begin'] for x in selected if x['helper'] == phase) for phase in ('qk', 'pv')}
        cpu['other'] = end-begin-cpu['qk']-cpu['pv']
        require(cpu['other'] >= 0 and all(a['end'] <= b['begin'] for a, b in zip(selected, selected[1:])),
                'Overlapping CPU retirement intervals')
        tiles, useful = [], 0
        for tokens, span in zip((64, 64, 9), selected[1::2]):
            if trial['arm'] == 0:
                row_loads = sum(span['opcodes'][v] for v in ('0205345b', '0205355b'))
                fmas = sum(span['opcodes'][v] for v in FMA_OPCODES)
                require(row_loads == tokens and fmas == 2*tokens, 'Baseline retired PV work mismatch')
                useful += fmas*128
                tiles.append(dict(tokens=tokens, retired_fma_instructions=fmas,
                    fma_handshake_utilization=None, reason='No baseline per-cycle FPU handshake samples'))
                continue
            perf = resident['pv_terminals'][service_index]
            vector = resident['actual_vector_writes'][service_index]
            service_index += 1
            require(perf['tokens'] == tokens and span['begin'] <= vector['allocation_cycle'] < span['end'] and
                vector['completion_cycle'] <= end, 'PV service not owned by this call/helper')
            cycles, lanes = perf['cycles'], perf['lanes']
            require(cycles > 0 and len(lanes) == 4, 'Missing PV service/lane evidence')
            issued = [x['issued'] for x in lanes]
            require(all(x['issued'] == x['returned'] and x['issued'] <= cycles for x in lanes), 'PV handshake accounting')
            useful += 4*sum(issued)
            tiles.append(dict(tokens=tokens, controller_service_cycles_inclusive=cycles,
                backend_allocation_to_done_cycles=vector['completion_cycle']-vector['allocation_cycle'],
                completion_after_cpu_helper_exit_cycles=max(0, vector['completion_cycle']-span['end']),
                fma_input_handshakes_by_lane=issued, fma_return_handshakes_by_lane=[x['returned'] for x in lanes],
                fma_input_acceptance_per_service_lane_cycle=sum(issued)/(4*cycles),
                fma_input_acceptance_ratio_by_lane=[n/cycles for n in issued], flags=perf['flags']))
        require(useful == 35072 and trial['fcsr'] == 3, 'Unequal PV arithmetic work/CSR')
        output.append(dict(trial=trial['trial'], arm=trial['arm'], trace_begin=begin, trace_end=end,
            issue_return_cycles=returned-begin, final_drain_cycles=end-returned, full_call_cycles=end-begin,
            cpu_retirement_interval_cycles=cpu, helpers=selected, pv_tiles=tiles, pv_scalar_fmas=useful, fcsr=3))
    require(service_index == 6, 'Unowned PV service')
    means = {}
    for arm, label in ((0, 'strong_rotation'), (1, 'resident_pv')):
        group = [x for x in output if x['arm'] == arm]
        require(len(group) == 2, 'Expected two trials per arm')
        means[label] = {phase: sum(x['cpu_retirement_interval_cycles'][phase] for x in group)/2
            for phase in ('qk', 'pv', 'other')}
        means[label]['full_call'] = sum(x['full_call_cycles'] for x in group)/2
    delta = {k: means['strong_rotation'][k]-means['resident_pv'][k] for k in means['strong_rotation']}
    require(delta['full_call'] == sum(delta[k] for k in ('qk', 'pv', 'other')), 'Difference bookkeeping not closed')
    return dict(trials=output, mean_cycles=means, baseline_minus_candidate_retirement_interval_delta=delta,
        complete_call_speedup=means['strong_rotation']['full_call']/means['resident_pv']['full_call'],
        same_work=dict(pv_scalar_fmas_per_call=35072, qk_panel4_commands_per_call=96, fcsr=3),
        noncausal_difference_bookkeeping=True, pipeline_occupancy_measured=False,
        handshake_definition='Accepted SIMD F16x4 FPU inputs / controller-service lane-cycles; not occupied pipeline stages',
        warning='CPU first-inside to first-outside retirement intervals include exit gaps; partition deltas are not additive real stalls. PV service windows overlap CPU intervals and must not be added to them.')


def analyze(directory):
    directory = Path(directory).resolve()
    result, software, text, pins = accepted_evidence(directory)
    elf, commit = Path(software['elf']), directory/'work/commit.csv'
    require(pins.get(str(elf)) == sha(elf) and pins.get(str(commit)) == sha(commit), 'Unpinned ELF/commit trace')
    ranges = elf_ranges(elf.read_bytes())
    trials = reference.trials_from_log(text)
    markers = {x[k] for x in trials for k in ('begin', 'returned', 'end')}
    require(len(markers) == 12, 'Nonunique full-call rdcycle values')
    with commit.open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)) and
            {'cycle', 'event', 'pc', 'insn', 'rd_wdata'} <= set(reader.fieldnames), 'Malformed commit trace header')
        spans, matched = cpu_spans(reader, ranges, markers)
    report = summarize(trials, spans, matched, result['resident_work'])
    require([t['full_call_cycles'] for t in report['trials']] == result['numerical']['complete_call_cycles'],
            'Trace/rdcycle full-call mismatch')
    report.update(schema='resident-pv-abba-attribution-v1', state='ACCEPTED_ABBA_ATTRIBUTED',
        no_new_rtl_execution=True, source_run=str(directory), source_result_sha256=sha(directory/'result.json'),
        elf_helper_ranges=ranges, pv_phase_pc_union=list(PV), qk_phase_pc=QK,
        trace_minus_rdcycle=next(matched[v]-v for v in matched), post_analysis_pins_match=True)
    e.contract.verify(pins)
    return report, pins


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New independent signoff directory')
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.parent == r.OUT and re.fullmatch(r'resident_pv_soc_attribute_[A-Za-z0-9_-]+', out.name) and
        not out.exists() and not out.is_relative_to(args.run.resolve()), 'Fresh independent attribution output required')
    report, pins = analyze(args.run)
    out.mkdir()
    e.save(out/'source-pins.json', pins)
    report['source_pins_sha256'] = sha(out/'source-pins.json')
    e.save(out/'report.json', report)
    print(json.dumps(dict(state=report['state'], output=str(out), mean_cycles=report['mean_cycles'])))


if __name__ == '__main__':
    main()
