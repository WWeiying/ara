#!/usr/bin/env python3
"""Completed focused record + bounded offline wave check, not another simulation."""
import csv
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BEFORE = HERE.parent
RUN = HERE/'vcs_candidate05_01'
OUT = HERE/'focused01'
sys.path.insert(0,str(BEFORE.parent.parent/'comparison_alias_original'))
from analyze_selected import normalize, vcd
sys.path.insert(0,str(BEFORE.parent.parent/'integration'))
import run as integration
ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
MASK = ARA+'.i_masku'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path,data):
    with path.open('x') as stream:
        json.dump(data,stream,indent=2)
        stream.write('\n')


def compare_control(name):
    old = BEFORE/'vcs_candidate04_01/replay/tests'/name/'commit_trace.csv'
    new = RUN/'replay/tests'/name/'commit_trace.csv'
    changed, nonretire_changed, examples, rows = 0,0,[],0
    with old.open() as a,new.open() as b:
        for index,(x,y) in enumerate(itertools.zip_longest(csv.DictReader(a),csv.DictReader(b)),1):
            rows += 1
            if x != y:
                changed += 1
                if (x and x['event'] != 'retire') or (y and y['event'] != 'retire'):
                    nonretire_changed += 1
                if len(examples) < 8:
                    examples.append(dict(row=index,m4=x,m5=y))
    return dict(all_rows_compared=rows,changed_rows=changed,changed_nonretire_rows=nonretire_changed,
                examples=examples,m4_sha256=sha(old),m5_sha256=sha(new),
                byte_identical=sha(old)==sha(new))


def wave(case, checked):
    name = case['name']
    folder = OUT/name
    folder.mkdir()
    fsdb = RUN/'replay/tests'/name/'work/focused.fsdb'
    target_cycle = int(checked['target']['cycle'])
    start,end = max(0,target_cycle-12000),min(90000,target_cycle+4000)
    raw = folder/'capture.vcd'
    command = [str(integration.VERDI/'platform/linux64/bin/fsdb2vcd'),str(fsdb),'-o',str(raw),
               '-bt',str(start)+'ns','-et',str(end)+'ns','-compacttree']
    env = dict(integration.environment(),LD_LIBRARY_PATH=str(integration.VERDI/'etc/lib/libstdc++/linux64'))
    with (folder/'conversion.log').open('x') as stream:
        subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=90)
    save(folder/'conversion.json',dict(command=command,fsdb=str(fsdb),fsdb_sha256=sha(fsdb)))
    iterator = iter(vcd(normalize(raw)))
    _,decl = next(iterator)
    def value(state,path):
        bits = state.get(decl.get(path,{}).get('code'),'x')
        return int(bits,2) if set(bits)<=set('01') else None
    clk = decl['ara_tb.clk']['code']
    cycle_path = 'ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q'
    requests, first_grants, scans, consumptions, active_writes = [],{},[],[],[]
    vids = {}
    for timestamp,before,after in iterator:
        if before.get(clk) != '0' or after.get(clk) != '1':
            continue
        cycle = value(before,cycle_path)
        if value(before,MASK+'.vinsn_issue_valid') == 1 and value(before,MASK+'.vinsn_issue.vl') == 256:
            scan = value(before,MASK+'.vrgat_cnt_q')
            if value(before,MASK+'.vrgat_idx_fifo_push') == 1 and scan in (0,128):
                scans.append(dict(cycle=cycle,scan=scan,index=value(before,MASK+'.vrgat_req_idx_d'),
                                  oor=value(before,MASK+'.vrgat_idx_oor_d')))
            if value(before,MASK+'.vrgat_idx_fifo_pop') == 1 and value(before,MASK+'.issue_cnt_q') == 128:
                consumptions.append(dict(cycle=cycle,destination=128,index=value(before,MASK+'.vrgat_req_idx_q'),
                                         oor=value(before,MASK+'.vrgat_idx_oor_q')))
        for lane in range(4):
            scope = ARA+'.gen_lanes[%d].i_lane' % lane
            requester = scope+'.i_operand_requester'
            valid,ready = value(before,scope+'.operand_request_valid'),value(before,scope+'.operand_request_ready')
            if value(before,scope+'.operand_request[0].vs') == 16 and valid is not None and ready is not None and valid&ready&1:
                vids[lane] = value(before,scope+'.operand_request[0].id')
                requests.append(dict(cycle=cycle,lane=lane,vstart=value(before,scope+'.operand_request[0].vstart'),
                    eew=value(before,scope+'.operand_request[0].eew'),length=value(before,scope+'.operand_request[0].vl')))
            if lane in vids and lane not in first_grants and value(before,requester+'.requester_metadata_q[0].id') == vids[lane] and value(before,requester+'.operand_requester_gnt[0]'):
                first_grants[lane] = dict(cycle=cycle,lane=lane,address=value(before,requester+'.requester_metadata_q[0].addr'),
                    bank_address=value(before,requester+'.operand_payload[0].addr'),remaining=value(before,requester+'.requester_metadata_q[0].len'))
            valid,ready = value(before,MASK+'.masku_result_req_o'),value(before,MASK+'.masku_result_gnt_i')
            if lane == 0 and valid is not None and ready is not None and valid&ready&1 and value(before,MASK+'.masku_result_addr_o[0]') == 100:
                active_writes.append(dict(cycle=cycle,lane=0,address=100,be=value(before,MASK+'.masku_result_be_o[0]'),
                    low_byte=value(before,MASK+'.masku_result_wdata_o[0]')&255))
    passed = len(requests)==len(first_grants)==4 and all(r['vstart']==0 and r['eew']==1 and r['length']==64 for r in requests)
    passed &= all(r['address']==64 and r['bank_address']==8 and r['remaining']==64 for r in first_grants.values())
    passed &= len(scans)==2 and [(r['scan'],r['index'],r['oor']) for r in scans]==[(0,0,0),(128,511,0)]
    passed &= len(consumptions)==1 and consumptions[0]['index']==511 and consumptions[0]['oor']==0
    passed &= len(active_writes)==1 and active_writes[0]['be']==255 and active_writes[0]['low_byte']==79
    result = dict(status='ORIGIN0_SCAN128_IDX511_ACTIVE_BE79_PASS' if passed else 'NOT_CONFIRMED',
        requests=requests,first_grants=list(first_grants.values()),scans=scans,consumptions=consumptions,
        active_writes=active_writes,sampling='Actual pre-rising-edge valid AND ready; no force',
        fsdb_sha256=sha(fsdb),normalized_vcd_sha256=sha(folder/'normalized.vcd'))
    save(folder/'wave_gate.json',result)
    print(name,result['status'],scans,flush=True)
    return result


def main():
    terminal = read(RUN/'complete.json')
    if terminal['status'] != 'FOCUS_FULL514_PASS2_PENDING_WAVE':
        print('NOT_ACCEPTED_NO_FURTHER_DUT',terminal['status'])
        return 1
    plan = read(HERE/'focus_plan.json')
    OUT.mkdir(exist_ok=False)
    control = next(case for case in plan['cases'] if case['control_override'])
    comparison = compare_control(control['name'])
    save(OUT/'start0_full_csv_comparison.json',comparison)
    waves = {case['name']:wave(case,terminal['checked'][case['name']]) for case in plan['cases']}
    old,new = terminal['before_endpoints'][control['name']],terminal['checked'][control['name']]
    end_cycles = dict(m4_exit=old['ctrl_exit_stores'],m5_exit=new['ctrl_exit_stores'],
        m4_last_cycle=old['last_cycle'],m5_last_cycle=new['last_cycle'],
        m4_last_retire=old['last_retire'],m5_last_retire=new['last_retire'],
        m4_events=old['event_counts'],m5_events=new['event_counts'])
    accepted = all(item['status']=='ORIGIN0_SCAN128_IDX511_ACTIVE_BE79_PASS' for item in waves.values()) and comparison['changed_rows']==0
    save(OUT/'acceptance.json',dict(status='PASS_M5_FOCUS2_FULL514_ORIGIN0_CONTROL_IDENTICAL' if accepted else 'NOT_ACCEPTED_CHECK_REQUIRED',
        complete_sha256=sha(RUN/'complete.json'),image=terminal['image'],
        same_elf_hashes={case['name']:case['soc_elf_sha256'] for case in plan['cases']},
        wave_results=waves,start0_comparison=comparison,start0_end_cycles=end_cycles,
        retries=0,software_changed=False,prefix_closed=False))
    print('ACCEPTANCE',accepted,sha(OUT/'acceptance.json'),flush=True)
    return 0 if accepted else 1


if __name__ == '__main__':
    sys.exit(main())
