"""Exact768 LZC interval provenance and standalone calibration plan; no simulator launch."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import audit_fma_lzc_library_candidate as source
import inspect_cva6_mda767 as intervals
import report_native_batch766 as original

life,require=original.life,original.require
FORMAL=life.OUT/'stride-metadata-full64-offline-admitted-768-agent-20261007-01'
SEAL='1add5889916fd9cfe2bb6e95368a2a86d43f1d0ac27ac4cf89786639cb6f4198'
BENCH=life.ROOT/'verification/tests/fma_lzc_width_calibration.sv'


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh standalone review directory')
    audit=source.review();scopes={i['scope']:i for i in audit['instances']}
    book=life.read_bound(FORMAL/'admission-manifest.json',SEAL)
    ledger=FORMAL/'combined-inputs.txt';require(life.digest(ledger)==book['output_pins'][str(ledger)],'Exact768 ledger pin')
    inputs=ledger.read_text().splitlines();require(len(inputs)==len(set(inputs))==769,'Exact768 population')
    cfg=life.read_bound(life.OUT/'native-batch-full766-agent-20261007-01/config.json',
        'ce709dbf1da6a16f16c8c10e7c2006c59429a3ff08c09237a3355a7267f53650')
    authority=original.merge(cfg['pins'],book['input_pins'],book['output_pins'])
    pins=dict(audit['pins']);pins.update({str(FORMAL/'admission-manifest.json'):SEAL,
        str(ledger):book['output_pins'][str(ledger)]})
    arrays={}
    for scope,item in scopes.items():
        nodes=[n for n in item['internal_candidates'] if n['shape_kind']=='arrays']
        require(len(nodes)==2 and len({n['logical_bits'] for n in nodes})==2,'Unique LZC array extents')
        arrays[scope]={n['logical_bits']:dict(name=n['name'],dimensions=n['dimensions'],extent=n['logical_bits'],
            any_nonzero_code_mask=0,member_code_histogram=Counter()) for n in nodes}
    for index,db in enumerate(inputs[1:],1):
        paths=list((Path(db)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(paths)==1,'One Toggle sample per member')
        path=paths[0];key=str(path);require(key in authority and life.digest(path)==authority[key],'Sealed768 Toggle source pin')
        found=set()
        with gzip.open(path,'rb') as f:
            for _,node in ET.iterparse(f,events=('end',)):
                scope=node.get('name')
                if node.tag=='instance_intervaldata' and scope in scopes:
                    require(scope not in found and node.get('chksum')==scopes[scope]['toggle_checksum'],'Exact array module/checksum')
                    found.add(scope);groups=intervals.intervals(node.get('value',''))
                    require(len(groups)==2 and {g['extent'] for g in groups}==set(arrays[scope]),'Exact array extent bijection')
                    for group in groups:
                        a=arrays[scope][group['extent']]
                        for run in group['raw_runs']:
                            code=run['raw_code'];a['member_code_histogram'][str(code)]+=run['count']
                            if code!=0:a['any_nonzero_code_mask']|=((1<<run['count'])-1)<<run['start']
                node.clear()
        require(found==set(scopes),'All32 FMA LZC array rows required')
        require(life.digest(path)==authority[key],'Array sample changed during read');pins[key]=authority[key]
        if index%200==0:print('LZC readonly interval members %d/768'%index,flush=True)
    result=[];total=0
    for scope,items in arrays.items():
        for a in items.values():
            mask=a.pop('any_nonzero_code_mask');a['member_code_histogram']=dict(a['member_code_histogram'])
            a['zero_code_in_all768_members_slots']=a['extent']-bin(mask).count('1')
            a['nonzero_seen_slots_mask']=hex(mask);total+=a['zero_code_in_all768_members_slots']
            result.append(dict(scope=scope,**a))
    cc=source.SOURCE.parent.parent
    pkg=cc/'src/cf_math_pkg.sv';asserts=cc/'include/common_cells/assertions.svh'
    build=json.loads((source.BUILD/'build-source-pins.json').read_bytes())
    require(build[str(pkg)]==life.digest(pkg) and build[str(asserts)]==life.digest(asserts),'Frozen calibration dependencies')
    for p in (BENCH,pkg,asserts,Path(__file__).resolve(),Path(intervals.__file__).resolve()):pins[str(p)]=life.digest(p)
    vcs=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')
    command=[str(vcs),'-full64','-sverilog','-timescale=1ns/1ps','+incdir+'+str(cc/'include'),
        str(pkg),str(source.SOURCE),str(BENCH),'-top','fma_lzc_width_calibration','-o','simv','-l','compile.log']
    life.check(pins);out.mkdir()
    plan=dict(status='LZC_WIDTH25_51_109_ARRAY_RAW_CODE_BOUND_CALIBRATION_PREPARED_NOT_RUN',
        population=768,manifest_seal=SEAL,pins=pins,array_groups=result,
        zero_code_all_members_slots=total,code_semantics='Raw codes preserved, never bitwise ORed. Code0 footprint is NOT a proved Toggle-direction missing count.',
        flattened_slot_to_physical_bit_bound=False,official_denominator=None,native_qualification_allowed=False,
        calibration_command=command,calibration_cwd=str(out),simulation_command=[str(out/'simv'),'-l','run.log'],
        settled_binary_expected_checks={str(w):w+w*(w-1)//2+5 for w in (25,51,109)},
        zero_policy='empty strictly checked; count logged, not asserted. FMA ignores leading_zero_count when lzc_zeroes is true (source518..535).',
        all_X_empty_preserved_test=True,EDA_launched=False,SoC_VDB_modified=False,
        open_source_policy='Only original RTL may be compiled. Do not rewrite unsigned casts or package semantics for tool compatibility.',
        next_gate='Real matched-width calibration PASS plus native array direction semantics and useful missing counts before native eligibility.')
    life.save(out/'plan.json',plan)
    print(json.dumps(dict(status=plan['status'],seal=life.digest(out/'plan.json'),zero_code_all_members_slots=total)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.output.resolve())
