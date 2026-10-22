"""Frozen PMP0 direct constant aliases, minus qualified791 EL; no EL or EDA."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import audit_soc_constants792_static as base
import review_csr_pmp0_toggle765 as prior

ROOT,OUT=base.ROOT,base.OUT
BASE=OUT/'itlb-ppn-aba-offline-admitted794-parent-20261008-01'
SEAL='02ee7424a6b21d8073097d8a6389be4393d76fc7a3ab31ce410f1c24f70de8cf'
CORE=base.CORE
CSR=CORE+'.csr_regfile_i'
FILES=('hardware/src/ara_soc.sv','hardware/deps/cva6/core/include/build_config_pkg.sv',
       'hardware/deps/cva6/core/csr_regfile.sv','hardware/deps/cva6/core/cva6.sv',
       'hardware/deps/cva6/core/cva6_rvfi_probes.sv','hardware/deps/cva6/core/cva6_rvfi.sv',
       'hardware/deps/cva6/core/include/rvfi_types.svh','hardware/deps/cva6/core/ex_stage.sv',
       'hardware/deps/cva6/core/load_store_unit.sv','hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv',
       'hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv','hardware/deps/cva6/core/acc_dispatcher.sv',
       'hardware/deps/cva6/core/pmp/src/pmp_data_if.sv')


def proof(texts):
    value=prior.source_proof(texts['ara_soc.sv'],texts['build_config_pkg.sv'],texts['csr_regfile.sv'])
    def expect(file,pattern):base.t.require(re.search(pattern,texts[file],re.S),'Direct PMP reflection/route differs: '+file)
    expect('csr_regfile.sv',r'assign rvfi_csr_o.pmpcfg_q\s*=\s*pmpcfg_q;')
    expect('csr_regfile.sv',r'assign rvfi_csr_o.pmpaddr_q\s*=\s*pmpaddr_q;')
    expect('cva6.sv',r'\.rvfi_csr_o\s*\(rvfi_csr\)')
    expect('cva6.sv',r'\.csr_i\s*\(rvfi_csr\)')
    expect('cva6_rvfi_probes.sv',r'csr\s*=\s*csr_i;')
    probe=re.sub(r'/\*.*?\*/|//[^\n]*','',texts['cva6_rvfi_probes.sv'],flags=re.S)
    csr_writes=[re.sub(r'\s+','',s) for s in re.findall(r'(?<![\w.])csr(?:\.[\w.]+)?\s*=(?!=)',probe)]
    base.t.require(csr_writes==['csr=','csr=','csr.mip_q='],'All probe CSR writers; PMP must remain direct')
    expect('cva6_rvfi_probes.sv',r'if \(\$bits\(rvfi_probes_o.csr\) == \$bits\(csr\)\) begin\s*rvfi_probes_o.csr = csr;')
    for field in ('pmpcfg','pmpaddr'):
        expect('cva6.sv',r'\.'+field+r'_o\s*\('+field+r'\)')
        expect('cva6.sv',r'\.'+field+r'_i\s*\('+field+r'\)')
        for file in ('ex_stage.sv','load_store_unit.sv'):
            expect(file,r'\.'+field+r'_i\s*[,\)]')
        expect('cva6_mmu.sv',r'\.'+field+r'_i\s*\('+field+r'_i\)')
    value.update(actual_NrPMPEntries=0,compiled_dummy_port_indices=[0],
                 dummy_port_reason='avoid_neg(NrPMPEntries-1) and explicit q[0:0] output for zero entries',
                 dynamic_d_counterexample='CSR writes may change d despite zero entries; i<0 next mux discards it. '
                   'reserved-clearing loop has zero iterations: d.reserved is NOT constant.',
                 rvfi_disabled_rdata='CONNECT_RVFI_FULL has no else/reset for disabled rdata; do not infer zero.',
                 csr_name_correction='64 internal pmpcfg entries, 64 pmpaddr entries; RVFI exposes pmpcfg0..3 and 16 pmpaddr slots.')
    return value


def stems():
    result={CSR:('pmpcfg_q','pmpcfg_next','pmpcfg_o','pmpaddr_q','pmpaddr_next','pmpaddr_o',
                 'rvfi_csr_o.pmpcfg_q','rvfi_csr_o.pmpaddr_q'),
            CORE:('pmpcfg','pmpaddr','rvfi_csr.pmpcfg_q','rvfi_csr.pmpaddr_q',
                  'rvfi_probes_o.csr.pmpcfg_q','rvfi_probes_o.csr.pmpaddr_q')}
    for scope in (CORE+'.ex_stage_i',CORE+'.ex_stage_i.lsu_i',
                  CORE+'.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu',
                  CORE+'.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_ptw',
                  CORE+'.ex_stage_i.lsu_i.i_pmp_data_if',CORE+'.gen_accelerator.i_acc_dispatcher'):
        result[scope]=('pmpcfg_i','pmpaddr_i')
    return result


def in_family(name,stem):return name==stem or name.startswith(stem+'[') or name.startswith(stem+'.')


def build():
    pins={}
    def read(path,sha,text=True):
        base.t.require(base.t.digest(path)==sha,'Bound static input drift: '+str(path))
        pins[str(path)]=sha;return path.read_text() if text else path.read_bytes()
    book=json.loads(read(base.BOOK,base.BOOK_SHA));texts={}
    for rel in FILES:
        p=ROOT/rel;texts[p.name]=read(p,book[str(p)])
    source=proof(texts)
    manifest=json.loads(read(BASE/'admission-manifest.json',SEAL))
    base.t.require(manifest['coverage_admitted'] is True,'Formal794 required')
    authority=dict(manifest['input_pins'],**manifest['output_pins'])
    ledger=read(BASE/'combined-inputs.txt',authority[str(BASE/'combined-inputs.txt')]).splitlines()
    base.t.require(len(ledger)==len(set(ledger))==795,'Exact794 ledger')
    union=json.loads(read(BASE/'combined-toggle-bits.json',authority[str(BASE/'combined-toggle-bits.json')]))
    q=json.loads(read(base.REPORT/'qualification.json',base.QUAL_SHA))
    base.t.require(q['population']==791 and q['complete_approved_EL_bitmask_union'] is True,'Qualified old EL authority')
    other,masks=base.native.semantic(read(base.REPORT/'applied.el',q['output_pins'][str(base.REPORT/'applied.el')]))
    whole={s for s,ch,m,line in other if line=='WHOLE_SCOPE'}
    owners=defaultdict(dict)
    for (scope,checksum,name,kind,decl,prefix,direction),mask in masks.items():
        if not prefix:owners[scope][(checksum,name,direction)]=owners[scope].get((checksum,name,direction),0)|mask
    db=Path(ledger[0])/'snps/coverage/db';trees=[]
    for rel in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml'):
        p=db/rel;read(p,authority[str(p)],False);trees.append(base.t.xml(p))
    fresh=[];already=[];holds=[];protected=[];shape_counts={}
    for scope,ss in stems().items():
        base.t.require(scope in union,'Exact product source scope exists')
        checks,defs=base.t.definitions(*trees,[scope]);d=defs[scope]
        base.t.require(checks[scope]==union[scope]['checksum'],'Source-bound Toggle checksum')
        nodes,arrays=base.typed.typed_nodes(d['shape'],union[scope])
        raw=list(ET.fromstring(d['shape']).find('tglshape'))
        shape_counts[scope]=dict(Counter(n.tag for n in raw if any(in_family(n.get('name',''),s) for s in ss)))
        for n in raw:
            if not any(in_family(n.get('name',''),s) for s in ss):
                if 'pmp' in n.get('name','').lower():protected.append(dict(scope=scope,kind=n.tag,**n.attrib))
        for n in nodes:
            if not any(in_family(n['name'],s) for s in ss):continue
            low=min(int(n.get('left',0)),int(n.get('right',0)))
            mask=((1<<n['logical_width'])-1)<<low
            ch=d['module']['chksum']+' '+checks[scope]
            coverage=[owners[scope].get((ch,n['name'],direction),0)&mask for direction in ('0to1','1to0')]
            item=dict(scope=scope,module=d['module'],checksum=checks[scope],compiled=n,constant='0',
                      initial_X_qualified=False,native_qualified=False)
            if any(scope==s or scope.startswith(s+'.') for s in whole) or coverage==[mask,mask]:already.append(item)
            elif any(coverage):holds.append(dict(item,reason='PARTIAL_OR_SINGLE_DIRECTION_EXISTING_EL'))
            elif n['missing_slots']:fresh.append(item)
        for n in arrays:
            if any(in_family(n['name'],s) for s in ss):holds.append(dict(scope=scope,compiled=n,reason='MDA_NO_BINARY_CAPACITY_OR_NATIVE_FLATTENING'))
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_audit_pmp_constants794_static.py'),Path(prior.__file__).resolve()):
        pins[str(path)]=base.t.digest(path)
    return dict(status='PMP0_DIRECT_CONSTANT_ALIASES794_STATIC_NOT_NATIVE_APPROVED',population=794,
                admission_seal=SEAL,existing_EL_population=791,proof=source,input_pins=pins,
                fresh_candidates=fresh,already_owned=already,HOLD=holds,dynamic_protected=protected,
                shape_counts=shape_counts,fresh_fields=len(fresh),fresh_logical_bits=sum(n['compiled']['logical_width'] for n in fresh),
                fresh_raw_missing=sum(n['compiled']['missing_slots'] for n in fresh),
                target_MDA=0,official_denominator=None,predicted_percentage=None,
                EDA_started=False,EL_generated=False,
                limitations=['Source reset-settled induction only; no initial X or delta exclusion',
                  'New61 and QBS3232 do not own PMP objects; 791 PMP owners are retained, not re-approved',
                  'RVFI rmask/wmask/rdata macros not generalized; observer and existing system aliases not new targets',
                  'All dynamic d, CSR address/index/wdata/locks/exceptions/control and noncandidate objects protected'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=build()
    for path,sha in value['input_pins'].items():base.t.require(base.t.digest(path)==sha,'Read-end input drift')
    with a.output.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(dict(output=str(a.output),seal=base.t.digest(a.output),fields=value['fresh_fields'],bits=value['fresh_logical_bits'],missing=value['fresh_raw_missing'])))
