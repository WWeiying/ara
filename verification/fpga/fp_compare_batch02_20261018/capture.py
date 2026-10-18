#!/usr/bin/env python3
"""Bounded, explicit-signal capture of one unchanged comparison ELF."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('replay',HERE/'run.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
ARA='ara_tb.dut.i_ara_soc.i_system.i_ara'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',type=Path,default=base.IMAGE)
    p.add_argument('--prepared',type=Path,default=HERE/'scenarios_prepared03')
    p.add_argument('--case',default='unmasked_alias_v8_e32_m4_t0_ctx1')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve()
    assert out.is_relative_to(HERE) and not out.exists()
    out.mkdir()
    ledger=json.loads((a.image/'image.json').read_text())
    for path,digest in ledger['files'].items():assert base.sha(path)==digest
    assert base.sha(Path(ledger['snapshot'])/'snapshot.json')==ledger['snapshot_sha256']
    plan=json.loads((a.prepared/'prepared.json').read_text());entry=plan['programs'][a.case]
    elf=Path(entry['directory'])/'soc.elf';assert base.sha(elf)==entry['elf_sha256']
    signals=['ara_tb.clk']
    dispatcher=ARA+'.i_dispatcher'
    signals += [dispatcher+'.'+n for n in ('state_q','state_d','reshuffle_req_d','reshuffle_req_q',
        'ara_req_valid','ara_req_ready_i','backend_valid','eew_q[8]','eew_q[16]',
        'ara_req.op','ara_req.vd','ara_req.vs1','ara_req.vs2','ara_req.eew_vs1','ara_req.eew_vs2','ara_req.vtype.vsew',
        'backend_req.op','backend_req.vd','backend_req.vs1','backend_req.vs2',
        'backend_req.eew_vs1','backend_req.eew_vs2','backend_req.vtype.vsew')]
    for lane in range(4):
        path=ARA+f'.gen_lanes[{lane}].i_lane.i_vfus.i_vmfpu'
        signals += [path+'.'+n for n in ('vinsn_issue_q.op','vinsn_issue_q.id','vinsn_issue_q.vtype.vsew',
            'operand_a','operand_b','vfpu_in_valid','vfpu_in_ready','vfpu_out_valid','vfpu_out_ready',
            'vfpu_processed_result','vfpu_tag_out.operand_a')]
    signals += [ARA+'.i_masku.'+n for n in ('vinsn_issue.op','vinsn_issue_valid','vrf_pnt_q',
         'fp_compare_nv_seq','result_queue_active_mask_seq','masku_operand_alu_valid','masku_operand_alu_ready',
         'fflags_o','fflags_valid_o')]
    tcl=['onerror {quit}', 'set fid [dump -file comparison.vpd -type VPD]']
    tcl += ['dump -add {'+n+'} -aggregates -fid $fid' for n in signals]
    tcl += ['dump -disable -fid $fid','run -absolute 15700ns','dump -enable -fid $fid',
            'run -absolute 17000ns','dump -disable -fid $fid','dump -flush $fid','run','quit']
    (out/'capture.tcl').write_text('\n'.join(tcl)+'\n')
    base.save(out/'signals.json',signals)
    spec=importlib.util.spec_from_file_location('runtime',base.RUNTIME/'run.py')
    runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
    r=base.command([ledger['simv'],'-no_save','-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+str(elf),
        '+TESTCASE='+a.case,'+NO_FSDB','-ucli','-do',out/'capture.tcl'],out,'vcs',timeout=180,env=runtime.environment())
    text=(out/'vcs.log').read_text(errors='replace')
    r.update(image=str(a.image),elf_sha256=base.sha(elf),signals=len(signals),window_ns=[15700,17000],
             architectural_pass=all(m in text for m in entry['pass_markers']),
             terminal='Core Test ***' in text)
    base.save(out/'result.json',r);print(json.dumps(r),flush=True)
    if not r['terminal']:return 2
    converter=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vpd2vcd')
    converted=base.command([converter,out/'comparison.vpd',out/'comparison.vcd'],out,'convert',timeout=120,env=runtime.environment())
    assert converted['returncode']==0 and (out/'comparison.vcd').exists()
    return 0


if __name__=='__main__':raise SystemExit(main())
