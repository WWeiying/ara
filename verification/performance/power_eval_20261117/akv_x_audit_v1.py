#!/usr/bin/env python3
"""Offline settled first-X diagnosis; no simulator, environment or RTL changes."""
import argparse
import importlib.util
from pathlib import Path
import re
import shutil

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
PARENT = OUT/'power_gls_20261117_long_akv_diag_02'
FROZEN = OUT/'power_dc_20261117_q8_matmul_subwindow_03/native/inputs'
BASE = 'ara_tb.dut.i_ara_soc'
LANE = BASE+'.i_system.i_ara.gen_lanes_0__i_lane'


def wanted(path):
    owner,_,leaf = path.rpartition('.')
    if owner==BASE:
        return leaf in ('clk_i','rst_ni')
    if owner==BASE+'.i_system.i_ariane':
        return leaf in ('pc_commit','commit_ack_commit_id','wdata_commit_id')
    if owner==LANE:
        return (leaf.startswith(('alu_','mfpu_','pv_fpu_','vrf_')) and
                not leaf.startswith(('vrf_tgt','vrf_operand')))
    if owner.startswith(LANE) and owner.endswith('i_simd_alu'):
        return leaf in ('operand_a_i','operand_b_i','result_o','valid_i','mask_i','vm_i','op_i','vew_i')
    if owner==LANE+'.i_vfus.i_vmfpu':
        return leaf.endswith(('_i','_o')) or leaf.startswith(('operand','result','state'))
    if owner==LANE+'.gen_resident_pv_i_resident_pv':
        return leaf.startswith(('fpu_','state','stream_'))
    if owner==BASE+'.i_system.i_ara.i_dispatcher':
        return leaf in ('state_q','state_d')
    if owner.endswith('i_wt_dcache'):
        return leaf.endswith(('_i','_o'))
    return False


def load(inputs):
    spec = importlib.util.spec_from_file_location('akv_frozen_scanner',inputs/'q8_matmul_post_v1.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def analyze(out):
    if out.parent!=OUT or out.exists():
        raise ValueError('Fresh owned offline output required')
    (out/'inputs').mkdir(parents=True)
    for name in ('q8_matmul_post_v1.py','dc_power.py','convert.py','reference-pair.json'):
        shutil.copyfile(FROZEN/name,out/'inputs'/name)
    shutil.copyfile(__file__,out/'inputs/akv_x_audit_v1.py')
    m = load(out/'inputs')
    plan = m.read(PARENT/'plan.json')
    m.require(plan['environment_diagnostic'] and plan['case_id']=='power_attention_akv', 'Wrong diagnostic')
    m.d.verify(m.read(PARENT/'source-pins.json'))
    vcd = PARENT/'run/window.vcd'
    scopes,paths = [],{}
    with vcd.open() as stream:
        for line in stream:
            f=line.split()
            if not f:continue
            if f[0]=='$scope':scopes.append(f[2])
            elif f[0]=='$upscope':scopes.pop()
            elif f[0]=='$var':
                path='.'.join(scopes+[f[4]])
                if wanted(path):paths[path]=path
            elif f[0]=='$enddefinitions':break
    m.require(30<len(paths)<700,'Unexpected selected profile size')
    m.PATHS=paths
    frames,command=m.read_frames(vcd,dict(first_tick=280150000,last_tick=355150000))
    values,seen_known,first_new,active_bad,snapshots={},{},{},{},[]
    points=(283805000,354825000,354835000,354845000,354855000)
    point_index=0
    for tick,changes in frames:
        values.update(changes)
        for name,value in changes.items():
            if m.known(value):seen_known[name]=True
            elif name in seen_known and name not in first_new:
                first_new[name]=dict(tick=tick,ns=tick/10000,value=value)
        for stem in ('alu','mfpu','pv_fpu'):
            valid = values.get(LANE+'.'+stem+('_result_valid' if stem=='pv_fpu' else '_result_req'))
            data = values.get(LANE+'.'+stem+('_result' if stem=='pv_fpu' else '_result_wdata'))
            if valid=='1' and data is not None and not m.known(data) and stem not in active_bad:
                active_bad[stem]=dict(tick=tick,ns=tick/10000,values=dict(values))
        while point_index<len(points) and tick>=points[point_index]:
            snapshots.append(dict(tick=tick,values=dict(values)))
            point_index+=1
    warnings=[]
    for num,line in enumerate((PARENT/'run/run.vcs.log').read_text().splitlines(),1):
        hit=re.search(r'Warning (\S+) : input (.+?) unknown/high-Z.*simulation time ([\d.]+)',line)
        if hit and (not warnings or hit[2] not in {x['input'] for x in warnings}):
            warnings.append(dict(line=num,path=hit[1],input=hit[2],ns=hit[3]))
    pins={str(p):m.sha(p) for p in [*list((out/'inputs').iterdir()),PARENT/'source-pins.json',
        PARENT/'plan.json',PARENT/'result.json',PARENT/'run/run.vcs.log',vcd]}
    m.save(out/'source-pins.json',pins)
    m.save(out/'result.json',dict(state='AKV_SELECTED_FIRST_X_EVIDENCE_NOT_POWER',
        original_failure_unchanged=True,diagnostic_cycles=7500,selected_signals=len(paths),
        first_new_X=first_new,first_active_unknown_result=active_bad,snapshots=snapshots,
        warning_first_categories=warnings,scan_command=command,new_GLS_launched=False,
        safe_environment_repair_proven=False,formal_power_window_eligible=False))
    print(out/'result.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True)
    analyze(p.parse_args().output.resolve())
