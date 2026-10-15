#!/usr/bin/env python3
"""Offline conversion of this completed one-round capture; no DUT invocation."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RUN = HERE / 'vcs_candidate04_01'
OUT = HERE / 'focused01'
sys.path.insert(0, str(HERE.parent.parent / 'comparison_alias_original'))
from analyze_selected import normalize, vcd
sys.path.insert(0, str(HERE.parent))
from prepare_batch import sha
sys.path.insert(0, str(HERE.parent.parent / 'integration'))
import run as integration

ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
MASK = ARA + '.i_masku'


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def scalar(spec):
    folder = RUN / 'replay/tests' / spec['name']
    model = json.loads((HERE / (spec['name'] + '.expected.json')).read_text())['rows'][0]
    target = spec['soc_routine'][8]['pc']
    csr = spec['soc_routine'][9]['pc']
    reads, mismatches, retired, target_row, returned = [], [], 0, None, None
    with (folder / 'commit_trace.csv').open() as stream:
        for row in csv.DictReader(stream):
            if row['event'] != 'retire':
                continue
            retired += 1
            pc = int(row['pc'],16)
            if pc == target:
                target_row = row
            if pc == csr:
                returned = int(row['rd_wdata'],16)
            addr = int(row['mem_addr'],16)
            if target_row and int(row['mem_rmask'],16) and spec['output_address'] <= addr < spec['output_address']+514:
                index = addr-spec['output_address']
                actual = int(row['rd_wdata'],16) & 255
                want = 91 if index in (0,513) else model['output'][index-1]
                reads.append(index)
                if want != actual:
                    mismatches.append(dict(element=index-1, expected=want, actual=actual, row=row))
    return dict(target=target_row, returned_vstart=returned, retired=retired,
                fullcap_elements_read=len(set(reads)-{0,513}), guards_read=0 in reads and 513 in reads,
                scalar_output_loads=len(reads), numeric_mismatches=len(mismatches), first_mismatch=mismatches[:1])


def convert(spec, measured):
    name = spec['name']
    folder = OUT / name
    folder.mkdir(exist_ok=False)
    fsdb = RUN / 'replay/tests' / name / 'work/focused.fsdb'
    target_cycle = int(measured['target']['cycle'])
    start, end = max(0,target_cycle-12000), min(90000,target_cycle+1000)
    command = [str(integration.VERDI / 'platform/linux64/bin/fsdb2vcd'), str(fsdb),
        '-o', str(folder / 'capture.vcd'), '-bt', str(start)+'ns', '-et', str(end)+'ns', '-compacttree']
    env = dict(integration.environment(), LD_LIBRARY_PATH=str(integration.VERDI / 'etc/lib/libstdc++/linux64'))
    with (folder / 'convert.log').open('x') as stream:
        subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=90)
    save(folder / 'conversion.json', dict(command=command, original_fsdb=str(fsdb), fsdb_sha256=sha(fsdb)))
    iterator = iter(vcd(normalize(folder / 'capture.vcd')))
    _, declarations = next(iterator)
    save(folder / 'declarations.json', declarations)
    fields = {path: declaration['code'] for path,declaration in declarations.items()}
    clk = fields['ara_tb.clk']
    cycle_code = fields['ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q']
    scan, result, requests = [], [], []
    def integer(state, path):
        bits = state.get(fields.get(path),'x')
        return int(bits,2) if set(bits) <= set('01') else None
    for timestamp, before, after in iterator:
        if before.get(clk) != '0' or after.get(clk) != '1':
            continue
        cycle = int(before.get(cycle_code,'0'),2)
        valid = integer(before, MASK+'.vinsn_issue_valid')
        vl = integer(before, MASK+'.vinsn_issue.vl')
        if valid == 1 and vl == 256:
            item = dict(cycle=cycle, time_ns=timestamp/10000)
            item.update({key: integer(before,MASK+'.'+key) for key in (
                'vrgat_cnt_q','vrgat_req_idx_d','vrgat_idx_oor_d','vrgat_idx_fifo_push',
                'vrgat_req_idx_q','vrgat_idx_oor_q','vrgat_idx_fifo_pop',
                'vrgat_req_fifo_push','vrgat_req_no_data_d','issue_cnt_q',
                'masku_operand_alu_seq','be_vrgat_seq_d','out_valid_cnt_q','out_vrf_word_valid')})
            if item['vrgat_idx_fifo_push'] == 1 and item['vrgat_cnt_q'] in (0,128):
                scan.append(item)
            if item['vrgat_idx_fifo_pop'] == 1 and item['issue_cnt_q'] in (256,129,128,127):
                result.append(item)
        for lane in range(4):
            prefix = ARA+'.gen_lanes[%d].i_lane' % lane
            vs = integer(before,prefix+'.operand_request[0].vs')
            valid_bits = integer(before,prefix+'.operand_request_valid')
            ready_bits = integer(before,prefix+'.operand_request_ready')
            if vs == 16 and valid_bits is not None and ready_bits is not None and valid_bits & ready_bits & 1:
                item = dict(cycle=cycle,lane=lane)
                item.update({key:integer(before,prefix+'.operand_request[0].'+key)
                             for key in ('vs','vstart','eew','vl','scale_vl')})
                item.update({key:integer(before,prefix+'.i_operand_requester.'+key)
                             for key in ('operand_payload[0].addr','requester_metadata_q[0].addr',
                                         'requester_metadata_q[0].len','vrf_addr_o')})
                requests.append(item)
    finding = dict(name=name, scalar=measured, alu_a_commands=requests,
        scan_0_and_128=scan, result_samples=result, capture_profile_gap='Block-local vrgat_res unavailable; alu_result and result queues captured',
        scope='One baseline single plus start0 control, no RTL change, no prefix acceptance')
    save(folder / 'finding.json', finding)
    print(name, 'scan', [(s['cycle'],s['vrgat_cnt_q'],s['vrgat_req_idx_d'],s['vrgat_idx_oor_d']) for s in scan], flush=True)
    return finding


def main():
    complete = json.loads((RUN / 'complete.json').read_text())
    plan = json.loads((HERE / 'plan.json').read_text())
    OUT.mkdir(exist_ok=False)
    findings = [convert(spec, scalar(spec)) for spec in plan['cases']]
    save(OUT / 'measurement.json', dict(original_run=str(RUN), complete=complete, findings=findings,
         new_dut_launch=False, retries=0, rtl_modified=False, prefix_closed=False))


if __name__ == '__main__':
    main()
