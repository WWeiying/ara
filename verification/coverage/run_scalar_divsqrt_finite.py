"""Scalar-only C910 finite DIV/SQRT preflight, one frozen VCS run and strict qualification."""
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import sys
import types
import xml.etree.ElementTree as ET
import run_scalar_fpu_finite as base
import scalar_divsqrt_oracle as oracle
import review_srt_radix16_child_residual as radix

life,require,build,old=base.life,base.require,base.build,base.old
APP=life.ROOT/'apps/riscv-tests/isa/rv64uv/scalar_divsqrt_finite.c'
PRE=life.OUT/'scalar-divsqrt-finite-preflight-agent-20261007-01'
RUN=life.OUT/'scalar-divsqrt-finite-old-image-agent-20261007-01'
QUAL=life.OUT/'scalar-divsqrt-finite-qualified-agent-20261007-01'
SYMBOLS=base.SYMBOLS
SCOPE=base.PREFIX+'.gen_operation_groups[1].i_opgroup_block.gen_merged_slice.i_multifmt_slice.gen_num_lanes[0].active_lane.lane_instance.gen_thmulti_c910_divsqrt.i_fpnew_divsqrt_th_64_c910'
CHILD=SCOPE+'.i_ct_vfdsu_top.x_ct_vfdsu_double.x_ct_vfdsu_srt.x_ct_vfdsu_srt_radix16_with_sqrt'


def instruction(row,word):
    require(word&0x7f==0x53 and (word>>25)&3==int(row['width']==64) and
        (word>>12)&7==(3 if row['rounding']=='rup' else 0),'Scalar DIV/SQRT format/rounding differs')
    require((word>>27)&31==(3 if row['operation']=='div' else 11) and (word>>7)&31==3 and
        (word>>15)&31==0 and (word>>20)&31==(1 if row['operation']=='div' else 0),
        'Exact scalar operation/FPR operands differ')


def validate_reference(commits,symbols,rows):
    writes={a:v for c in commits for a,v in c.memory_accesses if v is not None}
    require(not any(c.vector_writes or c.pc==symbols['trap_fail'] for c in commits),'Vector/trap not permitted')
    active=[c for c in commits if c.pc in {symbols['sf_op%d'%i] for i in range(20)}]
    require([c.pc for c in active]==[symbols['sf_op%d'%i] for i in range(20)],'Exact20 scalar arithmetic order differs')
    arithmetic=[c for c in commits if c.instruction&0x7f in (0x43,0x47,0x4b,0x4f) or
        (c.instruction&0x7f==0x53 and (c.instruction>>27)&31 in (0,1,2,3,4,5,11))]
    require(arithmetic==active,'Additional arithmetic not in independent oracle')
    for row,c in zip(rows,active):
        instruction(row,c.instruction)
        require(c.fpr_writes=={3:base.boxed(row)},'Rational/integer-root vs actual Spike FPR differs')
        addr=symbols['sf_observed']+24*row['index']
        require([writes.get(addr+8*j) for j in range(3)]==[base.boxed(row),row['flags'],64|row['flags']],
            'Independent Spike result/flags/NaNbox/frm readback differs')
    require([writes.get(symbols['g75_result']),writes.get(symbols['g75_result']+4),writes.get(symbols['num_failed']),
        writes.get(symbols['sf_guard_checks']),writes.get(symbols['tohost'])]==[40,0,0,35,1],
        '40checks/35guards terminal differs')
    csr=[writes.get(symbols['sf_csr']+8*i) for i in range(4)]
    require(csr[0] is not None and csr==[csr[0],72,64,csr[0]],'Independent CSR restoration differs')
    return old.architecture.reference_counts(commits,symbols)


def source_review(pins,book):
    review=life.read_bound(radix.REVIEW,radix.REVIEW_SHA)
    pins=life.merge_pins(pins,{str(radix.REVIEW):radix.REVIEW_SHA})
    for item in review['compiled_pins']:
        pins=life.merge_pins(pins,{str(life.ROOT/item['path']):item['sha256']})
    mapping=life.OUT/'srt-radix16-child-residual-source-review762-agent-20261007-01.json'
    mapping_sha='c2f4064a1566fc8cb8889038a3feb1d95c32a37501379605ceb5afd574c35095'
    bound=life.read_bound(mapping,mapping_sha)
    sourceinfo=old.BUILD/'sim/simv.vdb/snps/coverage/db/auxiliary/verilog.sourceinfo.xml'
    pins=life.merge_pins(pins,{str(mapping):mapping_sha,str(sourceinfo):bound['pins'][str(sourceinfo)]})
    source=life.ROOT/review['source']['path']
    require(review['module']==radix.MODULE and book[str(source)]==review['source']['sha256'],
        'Frozen arithmetic source identity differs')
    upstream=subprocess.run(['git','-C',str(life.ROOT/'hardware/deps/fpnew'),'show',
        radix.UPSTREAM+':vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/'+radix.MODULE+'.v'],
        check=True,capture_output=True,timeout=30).stdout
    require(upstream==source.read_bytes(),'Arithmetic IP modified vs frozen upstream')
    db=old.BUILD/'sim/simv.vdb/snps/coverage/db'
    def xml(p):
        raw=p.read_bytes()
        return ET.fromstring(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
    life.check(pins)
    design=xml(db/'design/verilog.design.xml');info=xml(db/'shape/tgl.verilog.info.xml');shape=xml(db/'shape/tgl.verilog.shape.xml')
    nodes={n.get('id'):(n,m) for m in design.findall('srcdef') for n in m.findall('srcinst')}
    def path(key):
        n,_=nodes[key];return (path(n.get('pid'))+'.' if n.get('pid') in nodes else '')+n.get('name')
    hierarchy={path(k):m for k,(_,m) in nodes.items()}
    scalar=[s for s,m in hierarchy.items() if m.get('name')==radix.MODULE and '.i_ariane.' in s]
    require(scalar==[CHILD] and hierarchy[CHILD].get('chksum')=='406590228','Not exact one physical scalar radix instance')
    checks={n.get('name'):n.get('chksum') for n in info.iter('instance_data')}
    require(checks[CHILD]=='3969040510' and checks[SCOPE]=='2010657625','Scalar wrapper/child specialization differs')
    wrapper=[n for n in shape if n.get('chksum')==checks[SCOPE]]
    require(len(wrapper)==1 and 'FpFmtConfig=56,NumPipeRegs=2,PipeConfig=3,WIDTH=64,' in wrapper[0].get('name'),
        'Scalar multi-format configuration differs')
    definitions=[n for n in shape if n.get('name')==radix.MODULE and n.get('chksum')=='3969040510']
    require(len(definitions)==1,'Radix shape ambiguity')
    lines=source.read_text().splitlines();objects=[]
    for n in definitions[0].find('tglshape'):
        require(n.get('file')=='375' and n.tag in ('node','vectornode'),'Foreign/unknown radix object')
        objects.append(dict(n.attrib,kind=n.tag,width=abs(int(n.get('left'))-int(n.get('right')))+1 if n.tag=='vectornode' else 1,
            declaration=lines[int(n.get('line_num'))-1]))
    approved,protected=radix.partition(objects,{s[0] for s in review['signals']})
    for name,line,width,left,right,fileid in review['signals']:
        n=next(n for n in approved if n['name']==name)
        require((int(n['line_num']),n['width'],int(n['left']),int(n['right']),n['file'])==(line,width,left,right,fileid),
            'Existing158 whole arithmetic rule identity differs')
    sourceinfo=db/'auxiliary/verilog.sourceinfo.xml'
    require(str(sourceinfo) in pins,'Source mapping not pinned')
    require([n.get('name') for n in xml(sourceinfo).iter('fileinfo') if n.get('id')=='375']==[str(source)],
        'Compiled file375 identity differs')
    wrapperpath=life.ROOT/'hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv'
    text=wrapperpath.read_text()
    for token in ('fpnew_pkg::FP64:    divsqrt_fmt = 4\'b1000;',
        'fpnew_pkg::FP32:    divsqrt_fmt = 4\'b0100;',
        'assign div_valid   = in_valid_q & (op_q == fpnew_pkg::DIV)',
        'assign sqrt_valid  = in_valid_q & (op_q != fpnew_pkg::DIV)',
        '.dp_vfdsu_idu_fdiv_issue        ( op_starting',
        '.idu_vfpu_rf_pipex_func         ( {3\'b0, divsqrt_fmt_q, 11\'b0 ,sqrt_op, div_op} )'):
        require(token in text,'Scalar format/operation routing source differs')
    return pins,dict(status='SCALAR_SOURCE158_RULE_MATCH_PENDING_OWN_ARCHITECTURAL_QUALIFICATION',
        physical_scalar_instances=1,architectural_formats=['FP32','FP64'],scope=CHILD,
        design_module_checksum='406590228',toggle_checksum='3969040510',wrapper=wrapper[0].attrib,
        upstream_commit=radix.UPSTREAM,upstream_bytes_equal=True,source_sha256=book[str(source)],
        signals=approved,protected=protected,objects=158,protected_objects=52,
        all_descendants_protected=True,vector_architecture_borrowed=False,native_approval=False,
        official_denominator=False,population_application=False)


def command(elf):
    cmd=base.command(elf)
    result=[x.replace(str(base.RUN)+'/',str(RUN)+'/') if str(base.RUN)+'/' in x else
        '+TESTCASE=scalar_divsqrt_finite' if x=='+TESTCASE=scalar_fpu_finite' else
        'scalar_divsqrt_finite' if x=='scalar_fpu_finite' else x for x in cmd]
    require(not any(str(base.RUN) in x for x in result),'Sealed FMA output path leaked')
    return result


def prepare():
    require(not PRE.exists() and not RUN.exists(),'Fresh one-shot output required')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL);require(len(image['image'])==66,'Frozen66 image differs')
    book=life.read_bound(old.BUILD/'build-source-pins.json',old.SOURCE_SHA)
    pins=life.merge_pins(image['image'],{str(life.PLAN):life.PLAN_SEAL,str(old.BUILD/'build-source-pins.json'):old.SOURCE_SHA})
    sourcepaths=['hardware/deps/cva6/core/fpu_wrap.sv','hardware/deps/cva6/core/ex_stage.sv',
        'hardware/deps/cva6/core/decoder.sv','hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv',
        'hardware/deps/fpnew/src/fpnew_top.sv','hardware/deps/fpnew/src/fpnew_opgroup_multifmt_slice.sv']
    sourcepaths.extend(str(p.relative_to(life.ROOT)) for p in (life.ROOT/'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl').glob('*.v'))
    for rel in sourcepaths:pins=life.merge_pins(pins,{str(life.ROOT/rel):book[str(life.ROOT/rel)]})
    pins,review=source_review(pins,book)
    cmd=json.loads(old.TEMPLATE.read_bytes())
    cmd=[str(APP) if x.endswith('/vgap99_csr_satp_mprv.c') else str(PRE/'input.elf') if x.endswith('/input.elf') else x for x in cmd]
    cmd[1:1]=['-I'+str(PRE)]
    for p in (APP,old.TEMPLATE,Path(__file__).resolve(),Path(oracle.__file__).resolve(),
        Path(__file__).with_name('test_scalar_divsqrt_finite.py'),life.ROOT/'verification/tests/gap75_start.S',
        life.ROOT/'verification/tests/gap75.ld',Path(cmd[0]),build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump',build.SPIKE):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    # Freeze the local imported strict comparison/reference/source-rule helpers, not their vector evidence.
    for module in tuple(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and Path(file).resolve().parent==Path(__file__).resolve().parent:
            p=Path(file).resolve();pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins);PRE.mkdir()
    try:
        rows=oracle.cases();life.save(PRE/'oracle.json',rows);life.save(PRE/'source-review.json',review)
        with (PRE/'scalar_divsqrt_vectors.h').open('x') as f:f.write(oracle.header(rows))
        life.save(PRE/'compile-command.json',cmd)
        with (PRE/'build.log').open('x') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        elf=PRE/'input.elf';symbols={n:build._elf_symbol(elf,build.LLVM/'llvm-readelf',n) for n in SYMBOLS}
        with (PRE/'input.disasm').open('x') as f:subprocess.run([str(build.LLVM/'llvm-objdump'),'-d',str(elf)],stdout=f,check=True,timeout=30)
        spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(elf)]
        life.save(PRE/'spike-command.json',spike)
        with (PRE/'spike.trace').open('x') as f:subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        counts=validate_reference(build.parse_spike_commits(PRE/'spike.trace'),symbols,rows)
        life.check(pins)
        for f in PRE.iterdir():pins=life.merge_pins(pins,{str(f):life.digest(f)})
        pre=dict(status='SCALAR20_DIV_SQRT_RATIONAL_SPIKE_PASS_NOT_RTL',pins=pins,symbols=symbols,counts=counts,
            operations=20,result_flags_checks=40,guard_checks=35,instances=[review],
            scope='Own scalar F/D DIV/SQRT only, positive finite sqrt and nonzero finite divide, explicit RNE/RUP; no vector borrowing.',
            coverage_admitted=False,native_exclusion_approved=False)
        life.save(PRE/'preflight.json',pre);pins=life.merge_pins(pins,{str(PRE/'preflight.json'):life.digest(PRE/'preflight.json')})
        record=dict(case='scalar_divsqrt_finite',pins=pins,command=command(elf),timeout_s=600,
            preflight_seal=life.digest(PRE/'preflight.json'),automatic_retry=False,rtl_changed=False,coverage_admitted=False)
        p=RUN.with_name(RUN.name+'.prepared.json');life.save(p,record);print('PREPARED '+life.digest(p),flush=True)
    except Exception as e:life.save(PRE/'failure.json',dict(reason=str(e),coverage_admitted=False));raise


def inherited(fn):
    return types.FunctionType(fn.__code__,dict(fn.__globals__,PRE=PRE,RUN=RUN,QUAL=QUAL,
        command=command,instruction=instruction),fn.__name__)


def collect(seal):
    inherited(base.collect)(seal)
    qpath=QUAL/'qualification.json';q=life.read_bound(qpath,life.digest(qpath))
    require(q['status']=='EXACT20_SCALAR_FP_RATIONAL_SPIKE_DUT_QUALIFIED' and
        (q['operations'],q['result_flags_checks'],q['guard_checks'])==(20,40,35),'Own exact scalar qualification required')
    life.check(q['input_pins']);life.check(q['output_pins'])
    review=life.read_bound(PRE/'source-review.json',q['input_pins'][str(PRE/'source-review.json')])
    review.update(status='SCALAR_RADIX158_SOURCE_AND_OWN_FINITE_ARCHITECTURE_READY_NATIVE_REQUIRED',
        own_scalar_qualification=str(qpath),own_scalar_qualification_sha256=life.digest(qpath),
        own_scalar_operations=20,exact_result_flags_checks=40,exact_boxing_csr_guards=35,
        evidence_limit='Finite scalar F/D DIV and positive SQRT RNE/RUP only; not exhaustive IEEE or other formats.',
        pins=life.merge_pins(life.merge_pins(q['input_pins'],q['output_pins']),{str(qpath):life.digest(qpath)}))
    life.save(QUAL/'arithmetic-source-review.json',review)
    print('SOURCE_READY '+life.digest(QUAL/'arithmetic-source-review.json'),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true');p.add_argument('--run-seal');p.add_argument('--collect-seal')
    a=p.parse_args();require(sum(map(bool,(a.prepare,a.run_seal,a.collect_seal)))==1,'One mode required')
    if a.prepare:prepare()
    elif a.run_seal:
        inherited(base.execute)(a.run_seal)
        collect(a.run_seal)
    else:collect(a.collect_seal)
