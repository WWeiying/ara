#!/usr/bin/env python3
"""Decode selected VPD->VCD fields immediately before each rising edge."""
import argparse
import csv
import importlib.util
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('comparison_vcd', HERE.parent/'current_board_review/comparison/decode_cycle.py')
parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
ARA='ara_tb.dut.i_ara_soc.i_system.i_ara'
D=ARA+'.i_dispatcher'


def decode_request(bits):
    # ara.sv ara_req_t, FOR_VERIFY, TRANS_ID_BITS=3, VLEN=1024.
    fields=[('op',8),('scale_vl',1),('vm',1),('eew_vmask',3),
        ('vs1',5),('use_vs1',1),('conversion_vs1',4),('eew_vs1',3),('old_eew_vs1',3),
        ('vs2',5),('use_vs2',1),('conversion_vs2',4),('eew_vs2',3),('old_eew_vs2',3),
        ('use_vd_op',1),('eew_vd_op',3),('scalar_op',64),('use_scalar_op',1),
        ('stride',64),('is_stride_np2',1),('vd',5),('use_vd',1),('swap',1),('emul',3),
        ('nf',3),('fof',1),('akv_refill',1),('akv_v2',1),('akv_column',1),
        ('fp_rm',3),('wide_fp_imm',1),('cvt_resize',2),('overlap_capture',1),
        ('overlap_use_snapshot',1),('overlap_snapshot_word',11),('snapshot_capture',1),
        ('snapshot_vs1',1),('snapshot_vs2',1),('vl',11),('vstart',11),('vtype',9),
        ('arch_seq',64),('arch_insn',32),('trans_id',3),('token',1)]
    assert sum(w for _,w in fields)==349 and len(bits)==349
    pos=0;out={}
    for name,width in fields:
        word=bits[pos:pos+width];pos+=width
        out[name]=int(word,2) if set(word)<=set('01') else None
    out['vsew']=None if out['vtype'] is None else (out['vtype']>>3)&7
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path)
    a=p.parse_args();out=a.capture.resolve();assert out.is_relative_to(HERE)
    path=out/'comparison.vcd'
    assert '100fs' in path.read_text()[:256]
    raw=path.read_text();removed=[];kept=[]
    for line in raw.splitlines(True):
        if line.startswith(('r','R')):
            parts=line.split();assert len(parts)==2
            removed.append(parts[1])
        else:kept.append(line)
    normalized=out/'logic_only.vcd'
    normalized.write_text(''.join(kept))
    stream=iter(parser.vcd(normalized));tag,decl=next(stream);assert tag=='declarations'
    fields={'clk':'ara_tb.clk'}
    for n in ('state_q','state_d','ara_req_ready_i','backend_valid','ara_req_valid',
              'eew_q','reshuffle_req_d','reshuffle_req_q','ara_req','backend_req'):
        fields['d_'+n]=D+'.'+n
    for lane in range(4):
        prefix=ARA+f'.gen_lanes[{lane}].i_lane.i_vfus.i_vmfpu'
        for n in ('operand_a','operand_b','vfpu_in_valid','vfpu_in_ready','vfpu_processed_result','vfpu_out_valid','vfpu_out_ready'):
            fields[f'l{lane}_{n}']=prefix+'.'+n
    for n in ('vrf_pnt_q','fp_compare_nv_seq','result_queue_active_mask_seq',
              'masku_operand_alu_valid','masku_operand_alu_ready','fflags_o','fflags_valid_o'):
        fields['m_'+n]=ARA+'.i_masku.'+n
    assert not (set(fields.values())-set(decl)),set(fields.values())-set(decl)
    codes={k:decl[v]['code'] for k,v in fields.items()}
    assert not set(removed).intersection(codes.values()), 'A measured field is real-valued'
    (out/'normalization.json').write_text(json.dumps(dict(
        raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        logic_sha256=hashlib.sha256(normalized.read_bytes()).hexdigest(),
        unused_real_updates_removed=len(removed)),indent=2)+'\n')
    rows=[];events=[]
    for time,before,after in stream:
        if before.get(codes['clk'])!='0' or after.get(codes['clk'])!='1':continue
        row={}
        for name,code in codes.items():
            word=before.get(code,'x')
            row[name]=int(word,2) if set(word)<=set('01') else None
        row['time_ns']=time/10000
        for key in ('ara_req','backend_req'):
            decoded=decode_request(before.get(codes['d_'+key],'x'*349))
            for name in ('op','vm','vs1','use_vs1','vs2','vd','eew_vs1','eew_vs2','vsew','vl','vstart','arch_insn'):
                row[key+'_'+name]=decoded[name]
            row.pop('d_'+key)
        eew=row.pop('d_eew_q')
        for reg in (8,16):row[f'eew_v{reg}']=None if eew is None else (eew>>(3*reg))&7
        rows.append(row)
        if row['d_backend_valid']==row['d_ara_req_ready_i']==1 or any(
            row[f'l{i}_vfpu_in_valid']==row[f'l{i}_vfpu_in_ready']==1 or
            row[f'l{i}_vfpu_out_valid']==row[f'l{i}_vfpu_out_ready']==1 for i in range(4)) or row['m_fflags_valid_o']==1:
            events.append(row)
    assert rows and events
    with (out/'cycles.csv').open('x') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (out/'events.json').write_text(json.dumps(events,indent=2)+'\n')
    print(json.dumps(dict(rows=len(rows),events=len(events),first=events[0],last=events[-1]),indent=2))


if __name__=='__main__':main()
