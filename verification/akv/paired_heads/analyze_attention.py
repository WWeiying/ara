#!/usr/bin/env python3
"""Offline attribution of an accepted two-way ABBA; never launch or poll a job."""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import attention_run as gate
from run_refill_overlap_probe import csv_records, COMMIT_HEADER

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TYPES = {4:'FULL', 5:'REFILL', 6:'KCOL', 2:'PV', 3:'RELEASE'}
CUSTOM = {0x00b5605b:'FULL', 0x02a0605b:'REFILL', 0x0005745b:'KCOL',
          0x0205745b:'KCOL', 0x0205345b:'PV', 0x0000505b:'RELEASE'}
QK = {'akv_v2_compute_scores_f16_generic', 'akv_experimental_qk_f16_pair_panel4'}
PV = {'akv_v2_update_outputs_f16_generic', 'akv_experimental_pv_f16_pair'}


def busy_by_type(text, checked):
    groups, active = [], None
    for line in text.splitlines():
        if gate.BEGIN.fullmatch(line):
            active = {name:dict(commands=0, busy_cycles=0) for name in TYPES.values()}
        elif line.startswith('[AKV_PERF] '):
            row = gate.numeric_fields(line[len('[AKV_PERF] '):], gate.PERF_FIELDS)
            target = active[TYPES[row['command']]]
            target['commands'] += 1
            target['busy_cycles'] += row['busy_cycles']
        elif gate.END.fullmatch(line):
            trial = checked['trials'][len(groups)]
            busy = sum(x['busy_cycles'] for x in active.values())
            gate.require(busy == trial['derived_hardware_totals']['busy_cycles'], 'Grouped busy mismatch')
            groups.append(dict(trial=trial['trial'], paired=trial['paired'], measured_cycles=trial['cycles'],
                command_types=active, engine_busy_cycles=busy,
                measured_minus_engine_busy=trial['cycles']-busy))
            active = None
    gate.require(len(groups) == 4 and active is None, 'Incomplete grouped work')
    return groups


def disassembly_map(text):
    instructions, symbol = {}, None
    for line in text.splitlines():
        label = re.fullmatch(r'([0-9a-f]+) <([^>]+)>:',line)
        if label:
            symbol = label[2]
        m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{4}|[0-9a-f]{8})\s+(\S+)',line)
        if m:
            pc, bits = int(m[1],16), int(m[2],16)
            gate.require(pc not in instructions, 'Duplicate disassembly PC')
            instructions[pc] = dict(bits=bits, bytes=len(m[2])//2, mnemonic=m[3], symbol=symbol)
    pcs = sorted(pc for pc,item in instructions.items() if item['bits'] & ~0xf80 == 0xc0002073)
    gate.require(len(pcs) == 2 and all(instructions[pc]['symbol'] == 'main' for pc in pcs),
                 'Exactly two measurement CSR-read PCs in main required')
    return instructions, pcs


def retire_windows(stream, instructions, pcs, trials, groups):
    windows, reads, current = [], [], None
    last_order = -1
    for row in csv_records(stream, COMMIT_HEADER,
                           {'retire','arch_start','uop_alloc','uop_done','cvx_req','cvx_resp'}):
        if row['event'] != 'retire':
            continue
        gate.require(row['order'] == last_order+1, 'Missing/duplicate architectural retire order')
        last_order = row['order']
        pc = row['pc']
        if pc not in pcs and current is None:
            continue
        gate.require(not row['trap'], 'Trap within measurement boundary')
        item = instructions.get(pc)
        gate.require(item is not None, 'Retired PC absent from linked disassembly')
        mask = (1 << (item['bytes']*8))-1
        gate.require(row['insn'] & mask == item['bits'], 'Retire instruction differs from ELF disassembly')
        if pc in pcs:
            gate.require(len(reads) < 8 and pc == pcs[len(reads)%2] and
                         row['rd'] == ((item['bits'] >> 7) & 31) and row['rd'] != 0 and
                         row['rd_wdata'] < 1 << 64, 'Wrong measurement CSR retirement')
            reads.append(dict(pc=f'0x{pc:x}', order=row['order'], monitor_cycle=row['cycle'], value=row['rd_wdata']))
            if current is None:
                current = dict(mnemonics=Counter(), classes=Counter(), commands=Counter(), qk=0, pv=0)
            else:
                i = len(windows)
                delta = (reads[-1]['value']-reads[-2]['value']) & ((1 << 64)-1)
                gate.require(delta == trials[i]['cycles'], 'CSR rd_wdata difference does not match app cycles')
                count = sum(current['classes'].values())
                gate.require(count == row['order']-reads[-2]['order']-1, 'Missing in-window retired instructions')
                gate.require(current['qk'] == 1024 and current['pv'] == 512, 'Unexpected QK/PV arithmetic instruction work')
                wanted = {name:work['commands'] for name,work in groups[i]['command_types'].items()}
                gate.require(dict(current['commands']) == wanted, 'Retired custom command work differs from actual engine records')
                windows.append(dict(trial=i, paired=trials[i]['paired'], start=reads[-2], end=reads[-1],
                    csr_cycle_delta=delta, retired_instructions=count, classes=dict(current['classes']),
                    qk_vfwmacc_vf=current['qk'], pv_vfmacc_vf=current['pv'],
                    other_vfmacc_vf=current['mnemonics']['vfmacc.vf']-current['pv'],
                    custom_commands=dict(current['commands']), mnemonics=dict(sorted(current['mnemonics'].items()))))
                current = None
            continue
        mnemonic, bits = item['mnemonic'], item['bits']
        if bits & 127 == 0x5b:
            category = 'akv_custom'
            if bits in CUSTOM:
                current['commands'][CUSTOM[bits]] += 1
        elif mnemonic.startswith('v'):
            category = 'rvv_including_configuration'
        else:
            gate.require(mnemonic != '.word', 'Unclassified architectural opcode')
            category = 'scalar_including_scalar_fp'
        current['classes'][category] += 1
        current['mnemonics'][mnemonic] += 1
        current['qk'] += item['symbol'] in QK and mnemonic == 'vfwmacc.vf'
        current['pv'] += item['symbol'] in PV and mnemonic == 'vfmacc.vf'
    gate.require(len(reads) == 8 and len(windows) == 4 and current is None, 'Incomplete eight-CSR measurement proof')
    return dict(state='PROVEN_FROM_RETIRE', measurement_pcs=[f'0x{x:x}' for x in pcs], csr_reads=8,
        boundary='Strictly after start CSR retirement and before end CSR retirement; both CSR instructions excluded',
        instructions='Architectural retire events only; no arch_start/reshuffle/uop events counted', windows=windows,
        limitations='Retired instruction counts, not scalar/FP execution cycles, element FLOPs, issue occupancy, or FPU utilization')


def self_test():
    from attention_run_test import fixture
    text = fixture()
    checked = gate.check_log(text)
    groups = busy_by_type(text,checked)
    gate.require([g['engine_busy_cycles'] for g in groups] == [15420,3900,3900,15420], 'Busy grouping test')
    disasm = '0000000080000100 <main>:\n80000100: c0002573 rdcycle a0\n80000104: c00025f3 rdcycle a1\n'
    _,pcs = disassembly_map(disasm)
    gate.require(pcs == [0x80000100,0x80000104], 'CSR PC parser test')
    instructions = {pcs[0]:dict(bits=0xc0002573,bytes=4,mnemonic='rdcycle',symbol='main'),
                    pcs[1]:dict(bits=0xc00025f3,bytes=4,mnemonic='rdcycle',symbol='main'),
                    0x200:dict(bits=0xf2805057,bytes=4,mnemonic='vfwmacc.vf',symbol=next(iter(QK))),
                    0x204:dict(bits=0xb2805057,bytes=4,mnemonic='vfmacc.vf',symbol=next(iter(PV))),
                    0x208:dict(bits=0x0001,bytes=2,mnemonic='nop',symbol='main')}
    for i,bits in enumerate(CUSTOM):
        instructions[0x300+4*i] = dict(bits=bits,bytes=4,mnemonic='.word',symbol='native')
    code_pc = {v['bits']:k for k,v in instructions.items()}
    rows, order = [], 0
    def emit(pc,value=0):
        nonlocal order
        insn = instructions[pc]['bits']
        row = dict.fromkeys(COMMIT_HEADER,0)
        row.update(cycle=order,event='retire',order=order,trans_id=-1,pc=f'{pc:x}',insn=f'{insn:x}',
                   rd=((insn>>7)&31) if pc in pcs else 0,rd_wdata=f'{value:x}')
        rows.append(','.join(str(row[k]) for k in COMMIT_HEADER))
        order += 1
    for i,trial in enumerate(checked['trials']):
        emit(pcs[0],1000000*i)
        for pc,count in ((0x200,1024),(0x204,512),(0x208,3)):
            for _ in range(count):
                emit(pc)
        for command in gate.commands(trial['paired']):
            bits = {4:0x00b5605b,5:0x02a0605b,6:0x0205745b if trial['paired'] else 0x0005745b,
                    2:0x0205345b,3:0x0000505b}[command]
            emit(code_pc[bits])
        emit(pcs[1],1000000*i+trial['cycles'])
    trace = ','.join(COMMIT_HEADER)+'\n'+'\n'.join(rows)+'\n'
    result = retire_windows(io.StringIO(trace),instructions,pcs,checked['trials'],groups)
    gate.require(len(result['windows']) == 4, 'Complete synthetic windows')
    rejected = 0
    mutations = [trace.replace('186a0','186a1',1), '\n'.join(trace.splitlines()[:-1])+'\n',
                 trace.replace('f2805057','f2805056',1)]
    for bad in mutations:
        try:
            retire_windows(io.StringIO(bad),instructions,pcs,checked['trials'],groups)
        except ValueError:
            rejected += 1
    gate.require(rejected == 3,'Bad trace/cycle/insn accepted')
    return dict(state='HOST_SELF_TEST_PASS',busy_trials=4,csr_windows=4,rejected_mutations=3)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path)
    p.add_argument('--build',type=Path,default=ROOT/'verification/out/akv-paired-heads-attention-build-20261023-03')
    p.add_argument('--result-sha256')
    p.add_argument('--output',type=Path)
    p.add_argument('--self-test',action='store_true')
    a = p.parse_args()
    if a.self_test:
        print(json.dumps(self_test()))
        return
    gate.require(a.run is not None and a.output is not None and a.result_sha256 is not None,
                 'Require --run, --output and independently supplied --result-sha256')
    run,build,out = a.run.resolve(strict=True),a.build.resolve(strict=True),a.output.resolve()
    gate.require(not out.exists() and not out.is_relative_to(run) and not out.is_relative_to(build), 'Use fresh separate evidence output')
    status,result = gate.read_json(run/'status.json'),gate.read_json(run/'result.json')
    gate.require(status.get('state') == result.get('state') == 'PASS' and status.get('child_pid') is None,
                 'Run not terminal PASS; no polling or partial-trial analysis')
    gate.require(gate.digest(run/'result.json') == a.result_sha256,'Accepted result hash mismatch')
    report,pins = gate.checked_build(build)
    simv = Path(report['simv']).resolve(strict=True)
    image,accepted = gate.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',simv)
    gate.require(image == report['accepted_image_pins'] and status['simv'] == str(simv) and
                 status['elf'] == report['elf'],'Wrong accepted run ELF/image')
    gate.merge_pins(pins,accepted)
    gate.merge_pins(pins,gate.read_json(run/'source-pins.json'))
    evidence = result['evidence_sha256']
    log,trace,commit,uvm = (run/'work'/n for n in ('run.vcs.log','vector_trace.csv','commit_trace.csv','uvm_result.json'))
    gate.require(all(str(f) in evidence for f in (log,trace,commit,uvm,run/'source-pins.json')), 'Missing sealed run evidence')
    gate.merge_pins(pins,evidence)
    gate.merge_pins(pins,gate.hashes([run/'result.json',run/'status.json',Path(__file__),HERE/'analysis_README.md',
                                    HERE/'attention_run.py',HERE.parent/'run_refill_overlap_probe.py',Path(sys.executable).resolve()]))
    gate.verify_pins(pins)
    gate.check_result(uvm,report['elf_sha256'],image)
    checked_uvm = gate.read_json(uvm)
    gate.require(checked_uvm['log_sha256'] == gate.digest(log) and checked_uvm['vector_trace_sha256'] == gate.digest(trace), 'UVM evidence mismatch')
    text = log.read_text()
    checked = gate.check_log(text)
    gate.require(all(result.get(k) == v for k,v in checked.items()),'Stored result differs from sealed checker replay')
    groups = busy_by_type(text,checked)
    disasm = build/'disassembly.log'
    gate.require(str(disasm) in report['artifact_sha256'],'Disassembly not pinned in build')
    try:
        instructions,pcs = disassembly_map(disasm.read_text())
        with commit.open(newline='') as stream:
            retired = retire_windows(stream,instructions,pcs,checked['trials'],groups)
    except (ValueError,OSError) as error:
        retired = dict(state='NOT_AVAILABLE',reason=str(error),counts=None,
                       limitations='No arithmetic, scalar/vector work or FPU attribution claimed without complete retire proof')
    sums = {str(mode):dict(measured_cycles=sum(t['measured_cycles'] for t in groups if t['paired'] == mode),
        engine_busy_cycles=sum(t['engine_busy_cycles'] for t in groups if t['paired'] == mode),
        measured_minus_engine_busy=sum(t['measured_minus_engine_busy'] for t in groups if t['paired'] == mode)) for mode in (0,1)}
    result_analysis = dict(state='ANALYZED_ACCEPTED_RUN',run=str(run),build=str(build),
        accepted_result_sha256=a.result_sha256,elf_sha256=report['elf_sha256'],trials=groups,sums=sums,
        retired=retired,attention_speedup=checked['attention_speedup'],cycle_reduction_percent=checked['cycle_reduction_percent'],
        scope='Derived Qwen2.5 KV128 heads0,1,6,7 only; paired versus generic AKV, NOT ordinary RVV or Qwen3',
        residual='Measured cycles minus summed command busy; NOT an exclusive stall breakdown. Includes unassigned scalar/vector work, command gaps and synchronization; work can overlap engine busy.',
        busy_semantics='Actual per-command AKV_PERF busy_cycles; VLSU reports command_cycles+1. No disjoint attribution of FPU/memory/issue stalls.',
        work=[dict(trial=t['trial'],paired=t['paired'],**{k:t['derived_hardware_totals'][k] for k in
            ('records','v2_column_load','v2_column_panel','v2_logical_column','v2_row_load','replay_bytes',
             'q_external_bytes','kv_external_bytes','read_payload_bytes','read_ranges','ar','r_beats')}) for t in checked['trials']],
        raw_hardware_summary=checked['raw_hardware_summary'],post_pins_match=True)
    gate.verify_pins(pins)
    gate.require(gate.hashes(gate.image_files(simv)) == image,'Post-analysis image inventory drift')
    out.mkdir(parents=True,exist_ok=False)
    (out/'pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
    result_analysis['pins_sha256'] = gate.digest(out/'pins.json')
    (out/'analysis.json').write_text(json.dumps(result_analysis,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(state=result_analysis['state'],output=str(out/'analysis.json'),sums=sums,retire_state=retired['state'])))


if __name__ == '__main__':
    main()
