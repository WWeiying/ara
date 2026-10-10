"""Sealed737 clip rejection matrix: independent encoding, host/Spike, no VCS."""
import argparse
import ast
from collections import Counter
import inspect
import json
from pathlib import Path
import re
import subprocess

import build_narrow_reject_r1_preflight as frozen
from inventory_operand_debug import Design
from closure_point_inventory import definition,read_xml,points

life,require=frozen.life,frozen.require
ROOT,OUT,LLVM,SPIKE=frozen.ROOT,frozen.OUT,frozen.LLVM,frozen.SPIKE
APP=ROOT/'apps/riscv-tests/isa/rv64uv/vnarrow_clip_reject_matrix.c'
HEADER=ROOT/'verification/tests/narrow_clip_reject_reference.h'
BASE=OUT/'narrow-source-group-offline-admitted-737-parent-20261006-01'
BASE_SEAL='bd0ee8b3f52627578b120eb97109d7efc40a6e44466867f3d816ca2ec35a12ad'
BUILD=OUT/'repaired-aligned-build-20260930-01'
DESIGN=BUILD/'sim/simv.vdb'
SCOPE='ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
FROZEN_SHA='3551fcca4a0285c58f187fec06bb43055448702ad4fd67989266e8a4e96abbcd'
CHECKS=2094
# opcode, form, SEW, LMUL, source base, exact source guard line.
CELLS=[('vnclipu','wv',8,1,9,1964),('vnclip','wv',8,1,9,1981),
       ('vnclip','wv',8,2,10,1982),('vnclip','wv',8,4,12,1983),
       ('vnclipu','wx',8,1,9,2253),('vnclipu','wx',8,4,12,2255),
       ('vnclipu','wx',8,8,8,2256),('vnclip','wx',8,1,9,2267),
       ('vnclip','wx',8,8,8,2270),('vnclipu','wi',64,1,8,2511),
       ('vnclipu','wi',8,2,10,2514),('vnclipu','wi',8,4,12,2515),
       ('vnclipu','wi',8,8,8,2516),('vnclip','wi',8,1,9,2527),
       ('vnclip','wi',8,2,10,2528),('vnclip','wi',8,4,12,2529),
       ('vnclip','wi',8,8,8,2530)]


def encode(op,form,source):
    return ({'vnclipu':46,'vnclip':47}[op]<<26)|(1<<25)|(source<<20)|\
           ({'wv':24,'wx':7,'wi':1}[form]<<15)|({'wv':0,'wx':4,'wi':3}[form]<<12)|(16<<7)|0x57


def illegality(word,sew,lmul):
    require(type(word) is int and 0<=word<1<<32 and type(sew) is int and sew in (8,16,32,64) and
            type(lmul) is int and lmul in (1,2,4,8),'Malformed integer instruction context')
    require(word&127==0x57 and word>>26 in (46,47) and (word>>12)&7 in (0,3,4) and
            (word>>25)&1==1,'Not supported unmasked clip instruction')
    source=(word>>20)&31;dest=(word>>7)&31;form=(word>>12)&7;rs1=(word>>15)&31
    require(dest%lmul==0 and dest+lmul<=32 and (form!=0 or rs1%lmul==0),
            'Another operand alignment guard would confound this cell')
    reasons=[]
    if sew*2>64:reasons.append('SOURCE_EEW128')
    if lmul*2>8:reasons.append('SOURCE_EMUL16')
    elif source%(lmul*2):reasons.append('WIDE_SOURCE_ALIGNMENT')
    return reasons


CASES=[dict(op=op,form=form,sew=sew,lmul='m%d'%lm,source=src,line=line,vl=4,vstart=1,
            word='0x%08x'%encode(op,form,src)) for op,form,sew,lm,src,line in CELLS]
SYMBOLS=frozen.SYMBOLS[:14]+tuple('gnr_bad_%02d'%i for i in range(17))
RECOVERY=frozen.RECOVERY


def vtype(case):
    return ({8:0,16:1,32:2,64:3}[case['sew']]<<3)|{'m1':0,'m2':1,'m4':2,'m8':3}[case['lmul']]


expected_register=frozen.expected_register


class Constants(ast.NodeTransformer):
    def __init__(self,expected):
        self.expected=expected
    def visit_Constant(self,node):
        if type(node.value) is int and node.value in (24,25,26,312):
            require((node.lineno,node.value) in self.expected,'Non-matrix numeric literal cannot be adapted')
            return ast.copy_location(ast.Constant({24:17,25:2,26:3,312:221}[node.value]),node)
        return node


def oracle_functions():
    require(life.digest(Path(frozen.__file__))==FROZEN_SHA,'Immutable R1 oracle changed')
    namespace=dict(frozen.__dict__,CASES=CASES,CHECKS=CHECKS,SYMBOLS=SYMBOLS,vtype=vtype)
    # Adapt only dimensions, not the sealed ledger/VRF/handler/value predicates.
    positions={'signatures':[(15,24),(16,26),(18,25)],
               'validate':[(3,24),(5,24),(9,24),(26,24),(27,24),(41,24),(42,312),(43,26),(43,26)]}
    for name in ('signatures','validate'):
        tree=ast.parse(inspect.getsource(getattr(frozen,name)))
        actual=Counter((n.lineno,n.value) for n in ast.walk(tree) if isinstance(n,ast.Constant) and
                       type(n.value) is int and n.value in (24,25,26,312))
        require(actual==Counter(positions[name]),'Frozen matrix literal positions/counts differ')
        tree=Constants(set(positions[name])).visit(tree)
        ast.fix_missing_locations(tree)
        exec(compile(tree,str(Path(__file__).resolve())+':private-R1','exec'),namespace)
    return namespace


def validate(commits,symbols,trace):
    require(all(c.instruction&3==3 for c in commits),'No-C ELF contract: compressed retirement rejected')
    result=oracle_functions()['validate'](commits,symbols,trace)
    result.update(status='CLIP17_HOST_SPIKE_FULL_ORACLE_PASS_NOT_DUT',
        rejected_backend_native_zero_required_at_DUT=True,three_full_VRF_snapshots=True,
        per_cell_VRF_preservation_basis='initial/end full snapshots plus every rejected request zero backend/native and no intervening vector writers',
        legal_narrow_compute_executed=False)
    return result


def verify_elf(blob,symbols):
    # Original ELF-header constants must not be dimension-rewritten.
    fn=frozen.verify_elf
    source=inspect.getsource(fn)
    require(source.count('== 25')==1,'Original fault-PC dimension shape')
    namespace=dict(fn.__globals__,CASES=CASES)
    exec(compile(source.replace('== 25','== 18'),str(Path(__file__).resolve())+':ELF','exec'),namespace)
    namespace['verify_elf'](blob,symbols)


def header_audit():
    cells=re.findall(r'X\((\d{2}),"e(\d+), m(\d+)",(\d+),(0x[0-9a-f]+)\)',HEADER.read_text())
    require(len(cells)==17,'Exact compiled matrix size')
    for i,(index,sew,lm,vt,word) in enumerate(cells):
        c=CASES[i]
        require((index,int(sew),int(lm),int(vt),int(word,16))==
                ('%02d'%i,c['sew'],int(c['lmul'][1:]),vtype(c),int(c['word'],16)), 'Independent matrix encoding differs')
        require(len(illegality(int(word,16),int(sew),int(lm)))==1,'One exact independent rejection reason required')
    require(CHECKS==3*32*18+17*21+9,'Check arithmetic differs')


def targets():
    admission=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    require(admission['schema']=='NARROW_SOURCE_GROUP_HISTORICAL_ADMISSION_V1' and admission['output']==str(BASE),
            'Exact formal737 admission required')
    pins=dict(admission['output_pins']);life.check(pins)
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SEAL})
    before=life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    state=life.read_bound(BASE/'status.json',pins[str(BASE/'status.json')])
    require(state['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and state['aggregate_passed']==737 and
            state['coverage_admitted'] is True and len(before['tests'])==len(set(before['tests']))==737 and
            (BASE/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*before['tests']], 'Exact737 population required')
    d=Design(DESIGN)
    for rel,h in before['design'].items():pins=life.merge_pins(pins,{str(d.db/rel):h})
    book=BUILD/'build-source-pins.json';pins=life.merge_pins(pins,{str(book):life.digest(book)})
    sources=json.loads(book.read_bytes());src=OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    pins=life.merge_pins(pins,{str(src):sources[str(ROOT/'hardware/src/ara_dispatcher.sv')]})
    require(life.digest(src)=='9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43', 'Wrong frozen dispatcher')
    indices={'line':[401,416,419,422,561,567,569,576,584,673,680,683,685,692,695,698,700],
             'cond':[220,226,228,230,263,267,269,294,296,298,300,302],
             'branch':[825,827,829,835,837,841,913,919,923,1026,1028,1030,1040]}
    expected={'line':(1718,'1316526434'),'cond':(1140,'1370170966'),'branch':(1215,'1558979345')}
    result=[]
    for metric,wanted in indices.items():
        row=before['metrics'][metric][SCOPE];require((row['width'],row['checksum'])==expected[metric], 'Frozen shape drift')
        node=definition(read_xml(d.db/'shape/cond.verilog.shape.xml'),d.hierarchy[SCOPE],row['checksum']) if metric=='cond' else d.definition(SCOPE,metric)
        mapped={p['raw_index']:p for p in points(metric,node,row['width'])}
        for i in wanted:
            require(i in mapped and not int(row['bits'],16)&(1<<(row['width']-1-i)), 'Target already hit737/missing')
            result.append(dict(scope=SCOPE,metric=metric,width=row['width'],checksum=row['checksum'],
                point=mapped[i],hit_before=False,source_evidence=str(src),source_sha256=life.digest(src),native_ID_claimed=False))
    require({int(t['point']['line']) for t in result if t['metric']=='line'}=={c['line'] for c in CASES},'One zero source guard per cell')
    life.check(pins)
    return result,pins


def build(output):
    require(output.parent==OUT and output.resolve()==output and not output.exists(),'Fresh independent output required')
    header_audit();bound,pins=targets()
    template_dir=OUT/'narrow-reject-r1-cached-preflight-719-20261006-01'
    template_pre=life.read_bound(template_dir/'preflight-manifest.json','d84184ea823564af4af9475bc6d31c25f7cb7a2de9429b45751ef4633b080d28')
    template=template_dir/'compile-command.json'
    cmd=life.read_bound(template,template_pre['pins'][str(template)])
    oldapp=str(ROOT/'apps/riscv-tests/isa/rv64uv/vnarrow_reject_r1_matrix_cached.c')
    require(cmd.count(oldapp)==1 and cmd[-2]=='-o' and cmd[0]==str(LLVM/'clang'),'Sealed compile template differs')
    cmd=[str(APP) if x==oldapp else '-march=rv64gv_zfh_zvfh' if x=='-march=rv64gcv_zfh_zvfh' else x for x in cmd]
    cmd[-1]=str(output/'input.elf')
    require('-march=rv64gv_zfh_zvfh' in cmd and not any('ZCC' in x or 'Terapines' in x for x in cmd),'No-C/LLVM contract')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['image'][str(life.IMAGE)]=='2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3','Frozen66 identity differs')
    pins=life.merge_pins(pins,image['image'])
    paths=[APP,HEADER,Path(__file__).resolve(),Path(__file__).with_name('test_build_narrow_clip_reject_preflight.py'),
        Path(frozen.__file__).resolve(),ROOT/'verification/tests/narrow_reject_r1_reference.h',
        ROOT/'verification/tests/narrow_clip_reject_host.c',ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld',
        template,template_dir/'preflight-manifest.json',life.PLAN,Path('/usr/bin/cc'),Path('/usr/bin/cc').resolve(),
        LLVM/'clang',LLVM/'ld.lld',LLVM/'llvm-readelf',SPIKE,Path(frozen.shared.__file__),Path(frozen.strict.__file__),Path(life.__file__)]
    paths+=sorted((ROOT/'verification/ara_verify').rglob('*.py'))
    for tool in (LLVM/'clang',LLVM/'ld.lld',LLVM/'llvm-readelf',SPIKE):paths.append(tool.resolve())
    pins=life.merge_pins(pins,{str(x.absolute()):life.digest(x) for x in paths});life.check(pins)
    output.mkdir()
    try:
        host=['/usr/bin/cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(ROOT/'verification/tests'),
              str(ROOT/'verification/tests/narrow_clip_reject_host.c'),'-o',str(output/'host-reference')]
        life.save(output/'host-command.json',host)
        with (output/'host.log').open('x') as log:
            subprocess.run(host,check=True,timeout=60,stdout=log,stderr=subprocess.STDOUT)
            subprocess.run([str(output/'host-reference')],check=True,timeout=10,stdout=log,stderr=subprocess.STDOUT)
        require((output/'host.log').read_text()=='CLIP_HOST_PASS cases=17 checks=2094\n','Independent host check failed')
        life.save(output/'compile-command.json',cmd)
        with (output/'compile.log').open('x') as log:subprocess.run(cmd,check=True,timeout=120,stdout=log,stderr=subprocess.STDOUT)
        symbols={n:frozen.shared._elf_symbol(output/'input.elf',LLVM/'llvm-readelf',n) for n in SYMBOLS}
        verify_elf((output/'input.elf').read_bytes(),symbols)
        oldpins=life.read_bound(BASE/'evidence-pins.json',pins[str(BASE/'evidence-pins.json')])
        elfsha=life.digest(output/'input.elf')
        require(not any(x.endswith('.elf') and h==elfsha for x,h in oldpins.items()),'Duplicate formal737 ELF')
        spike=[str(SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(output/'input.elf')]
        life.save(output/'spike-command.json',spike)
        with (output/'spike.stdout').open('x') as stdout,(output/'spike.trace').open('x') as trace:
            subprocess.run(spike,check=True,timeout=180,stdout=stdout,stderr=trace)
        commits=frozen.shared.parse_spike_commits(output/'spike.trace')
        result=validate(commits,symbols,(output/'spike.trace').read_text())
        counts=frozen.strict.reference_counts(commits,symbols)
        life.save(output/'spike-validation.json',result);life.save(output/'target-before.json',bound)
        life.save(output/'matrix.json',[dict(c,rejection_reason=illegality(int(c['word'],16),c['sew'],int(c['lmul'][1:]))[0]) for c in CASES])
        life.check(pins)
        output_pins={str(x):life.digest(x) for x in output.iterdir() if x.is_file()}
        pre=dict(status='CLIP17_REJECT_MATRIX_PREFLIGHT_PASS_NOT_VCS',case=APP.stem,baseline=737,baseline_seal=BASE_SEAL,
            input_elf=str(output/'input.elf'),elf_sha256=elfsha,pins=life.merge_pins(pins,output_pins),symbols=symbols,
            validation=result,reference_counts=counts,targets=bound,checks=CHECKS,trap_cells=17,full_VRF_snapshots=3,
            old_image_files_checked=66,vcs_started=False,coverage_admitted=False,rtl_changed=False,
            software_compile_noC=True,DUT_differential_executed=False,legal_narrow_compute_executed=False,
            DUT_gate='full scalar/memory+vector diff; exact17 illegal request/response, zero backend/native per rejected owner; no interstitial vector writers',
            budget_estimate_seconds=[120,300],budget_is_not_measured=True,
            scope='Historical fixed image only; no waiver or new RTL signoff')
        life.save(output/'preflight-manifest.json',pre)
        print(json.dumps(dict(output=str(output),seal=life.digest(output/'preflight-manifest.json'),validation=result,reference_counts=counts,elf_sha256=elfsha)))
    except Exception as error:
        life.save(output/'failure.json',dict(status='PREFLIGHT_REJECTED_NO_VCS',reason=str(error)));raise


def verify(output,seal):
    pre=life.read_bound(output/'preflight-manifest.json',seal)
    require(pre['status']=='CLIP17_REJECT_MATRIX_PREFLIGHT_PASS_NOT_VCS' and pre['baseline']==737 and
            pre['baseline_seal']==BASE_SEAL and pre['vcs_started'] is False and pre['coverage_admitted'] is False,
            'Exact preflight required')
    life.check(pre['pins']);header_audit()
    bound,_=targets();require(bound==pre['targets'],'Compiled target rebinding differs')
    symbols={n:frozen.shared._elf_symbol(output/'input.elf',LLVM/'llvm-readelf',n) for n in SYMBOLS}
    require(symbols==pre['symbols'],'ELF symbols drift');verify_elf((output/'input.elf').read_bytes(),symbols)
    commits=frozen.shared.parse_spike_commits(output/'spike.trace')
    require(validate(commits,symbols,(output/'spike.trace').read_text())==pre['validation'] and
            frozen.strict.reference_counts(commits,symbols)==pre['reference_counts'],'Independent software replay differs')
    return pre


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('build','verify'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal');a=parser.parse_args()
    if a.mode=='build':require(not a.seal,'Build cannot claim seal');build(a.output.absolute())
    else:require(a.seal,'Seal required');verify(a.output.absolute(),a.seal);print('VERIFY_PASS NO_VCS')


if __name__=='__main__':main()
