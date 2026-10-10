"""Integer/Fraction gold, source predicates and one software-only Spike preflight."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import re
import subprocess

import build_scalar_fpu_fma_arbiter792 as reuse
import rank_cva6_scalar_data767 as typed
import targeted_toggle_evidence_v2 as toggle
import xml.etree.ElementTree as ET

life,build,old=reuse.life,reuse.build,reuse.old
require=reuse.prior.require
ROOT=life.ROOT
BASE=life.OUT/'itlb-ppn-aba-offline-admitted794-parent-20261008-01'
BASE_SHA='02ee7424a6b21d8073097d8a6389be4393d76fc7a3ab31ce410f1c24f70de8cf'
APP=ROOT/'apps/riscv-tests/isa/rv64uv/scalar_div_subnormal794.c'
RANK=life.OUT/'scalar-active-data-residual793-agent-20261008-01.json'
RANK_SHA='c4b57015f4406865fe8df468922937d31a6e55e8c9c2701ac4e0af13c50f1f90'
REL='hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/'
SRT=reuse.prior.SCOPE+'.fpu_gen.i_fpnew_bulk.gen_operation_groups[1].i_opgroup_block.'\
    'gen_merged_slice.i_multifmt_slice.gen_num_lanes[0].active_lane.lane_instance.'\
    'gen_thmulti_c910_divsqrt.i_fpnew_divsqrt_th_64_c910.i_ct_vfdsu_top.x_ct_vfdsu_double.x_ct_vfdsu_srt'
ROUND=SRT.rsplit('.',1)[0]+'.x_ct_vfdsu_round'


def cells():
    return [(k,0,s,0) for s in (0,1) for k in range(1,53)]+[
        (k,d,s,rm) for s in (0,1) for k,d in ((1,1),(1,3),(26,1),(52,1)) for rm in range(5)]


def gold(k,delta,negative,rm):
    require(type(k) is int and 1<=k<=52 and delta in (0,1,3) and
        negative in (0,1) and type(rm) is int and 0<=rm<=4,'Finite supported gold domain')
    # Exact quotient measured in binary64 minimum-subnormal units, no host floating point.
    ratio=Fraction((1<<52)+delta,1<<k)
    q,r=divmod(ratio.numerator,ratio.denominator)
    if r:
        if rm==0:q+=int(2*r>ratio.denominator or (2*r==ratio.denominator and q%2))
        elif rm==2:q+=negative
        elif rm==3:q+=1-negative
        elif rm==4:q+=int(2*r>=ratio.denominator)
    flags=3 if r else 0
    return dict(a=((1<<52)+delta)|(negative<<63),b=(1023+k)<<52,
        result=q|(negative<<63),fflags=flags,fcsr=(rm<<5)|flags,rm=rm,k=k,delta=delta,
        exponent_predicate=(-1022-k)&8191,onehot=1<<k)


def source_evidence():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    book=life.read_bound(old.BUILD/'build-source-pins.json',old.SOURCE_SHA)
    pins={str(BASE/'admission-manifest.json'):BASE_SHA,str(old.BUILD/'build-source-pins.json'):old.SOURCE_SHA}
    texts={}
    for rel in (REL+'ct_vfdsu_prepare.v',REL+'ct_vfdsu_srt.v',REL+'ct_vfdsu_round.v',
                'hardware/deps/cva6/core/fpu_wrap.sv'):
        p=ROOT/rel;require(life.digest(p)==book[str(p)],'Frozen exponent producer')
        pins[str(p)]=book[str(p)];texts[rel]=p.read_text()
    table=re.findall(r"13'h([0-9a-f]+):ex2_result_double_denorm_round_add_num\[52:0\]\s*=\s*53'h([0-9a-f]+)",texts[REL+'ct_vfdsu_srt.v'])
    table={int(e,16):int(v,16) for e,v in table}
    require(table=={(-1022-k)&8191:1<<k for k in range(53)},'All53 exponent/onehot predicates exact')
    for needle in ('ex2_expnt_result[12:0]  = vfdsu_ex2_expnt_add0[12:0] - vfdsu_ex2_expnt_add1[12:0]',
        'ex2_result_double_denorm_round_add_num[52:0] :'):
        require(needle in texts[REL+'ct_vfdsu_srt.v'],'DIV exponent/format producer')
    require('ex1_oper0[62:52]' in texts[REL+'ct_vfdsu_prepare.v'] and
        'ex1_oper1[62:52]' in texts[REL+'ct_vfdsu_prepare.v'],'Unsigned normal exponent inputs')
    rank=life.read_bound(RANK,RANK_SHA);pins[str(RANK)]=RANK_SHA
    p=BASE/'combined-toggle-bits.json';rows=life.read_bound(p,base['output_pins'][str(p)])
    pins[str(p)]=base['output_pins'][str(p)]
    shape=Path(str(life.IMAGE)+'.vdb')/'snps/coverage/db/shape/tgl.verilog.shape.xml'
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    require(life.digest(shape)==authority[str(shape)],'Frozen native Toggle shape')
    pins[str(shape)]=authority[str(shape)]
    definitions={d.get('chksum'):d for d in toggle.xml(shape).findall('tgldef')}
    targets=[]
    for obj in rank['groups']['FP64_denorm_round_shift']:
        scope=obj['scope'];row=rows[scope]
        require(row['checksum']==obj['checksum'],'Exact native scope checksum')
        nodes,_=typed.typed_nodes(ET.tostring(definitions[row['checksum']],encoding='unicode'),row)
        matches=[n for n in nodes if n['name']==obj['field']];require(len(matches)==1,'Unique typed field')
        n=matches[0];missing=sorted(set(n['missing_coordinates'])&set(obj['missing_serialized_positions']))
        if missing:targets.append(dict(scope=scope,checksum=row['checksum'],name=n['name'],
            file_id=n['file'],decl_line=n['line_num'],left=n.get('left'),right=n.get('right'),serialized_offset=n['serialized_offset'],
            missing_serialized_positions=missing,capacity=len(missing)))
    require(sum(t['capacity'] for t in targets)==580,'Closed794 residual field intersection')
    return dict(pins=pins,targets=targets,table=table,
        predicate='Normal A exponent1 minus normal B exponent1023+k => -1022-k; table selects1<<k.',
        copied_fields='EX2 double select -> EX3 pipedown -> denorm round concat/complement; observed owners required.',
        direction_labels='Serialized positions only; no guessed native 0to1/1to0 or MDA offsets',
        source_target_capacity=580,measured_gain=False)


def validate(commits,symbols):
    commits=list(commits);retired=[c for c in commits if c.pc==symbols['div_matrix_insn']]
    expected=[gold(*cell) for cell in cells()]
    require(len(retired)==len(expected)==144,'All144 DIV owners')
    for c,e in zip(retired,expected):
        require(c.instruction==0x1a107153 and c.fpr_writes=={2:e['result']},'Exact FDIV.D dyn instruction/result')
    require(all(c.instruction&3==3 and not c.vector_writes and c.pc!=symbols['trap_fail'] for c in commits),'NoC/vector/trap')
    writes={a:v for c in commits for a,v in c.memory_accesses if v is not None}
    for i,e in enumerate(expected):
        require([writes.get(symbols['div_observed']+24*i+8*j) for j in range(3)]==
            [e['result'],e['fflags'],e['fcsr']],'Independent integer gold results/fflags/FCSR per cell')
    csr=[writes.get(symbols['div_csr']+8*i) for i in range(2)]
    require(csr[0] is not None and csr[0]==csr[1],'Full FCSR restore')
    require([writes.get(symbols['g75_result']),writes.get(symbols['g75_result']+4),
        writes.get(symbols['num_failed']),writes.get(symbols['tohost'])]==[436,0,0,1],'436checks/terminal')
    return old.architecture.reference_counts(commits,symbols)


def prepare(out):
    require(not out.exists(),'Fresh software preflight')
    evidence=source_evidence();pins=evidence['pins'].copy()
    cmd=json.loads(old.TEMPLATE.read_bytes())
    cmd=[str(APP) if x.endswith('/vgap99_csr_satp_mprv.c') else str(out/'input.elf')
        if x.endswith('/input.elf') else '-march=rv64gv_zfh_zvfh' if x.startswith('-march=') else x for x in cmd]
    for p in (APP,Path(__file__).resolve(),old.TEMPLATE,Path(cmd[0]),build.SPIKE,
        build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump',ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld'):
        pins[str(p)]=life.digest(p)
    life.check(pins);out.mkdir();life.save(out/'compile-command.json',cmd)
    with (out/'build.log').open('x') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    symbols={s:build._elf_symbol(out/'input.elf',build.LLVM/'llvm-readelf',s)
        for s in ('tohost','trap_fail','g75_result','num_failed','div_observed','div_csr','div_guards','div_matrix_insn')}
    with (out/'input.disasm').open('x') as f:
        subprocess.run([str(build.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],stdout=f,check=True,timeout=30)
    spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(out/'input.elf')]
    life.save(out/'spike-command.json',spike)
    with (out/'spike.trace').open('x') as f:subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    counts=validate(build.parse_spike_commits(out/'spike.trace'),symbols)
    life.save(out/'gold.json',[gold(*x) for x in cells()]);life.save(out/'source-targets.json',evidence)
    life.check(pins)
    for p in out.iterdir():pins[str(p)]=life.digest(p)
    life.save(out/'preflight.json',dict(status='SPIKE_SCALAR_DIV_SUBNORMAL144_PASS_NOT_NATIVE',
        baseline=794,baseline_seal=BASE_SHA,pins=pins,symbols=symbols,counts=counts,cells=144,checks=436,
        source_target_capacity=580,runtime_target_predicates_unproven=True,RTL_changed=False,EDA_started=False))
    print(out,life.digest(out/'preflight.json'),counts)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    prepare(p.parse_args().output.resolve())
