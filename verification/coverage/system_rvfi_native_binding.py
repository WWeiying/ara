"""Offline exact1206 compiled/native bijection from preserved RVFI02 before inventory."""
import argparse
import csv
import json
from pathlib import Path

import capture_system_rvfi788 as original

life,require=original.life,original.require
ORIGIN=life.OUT/'system-rvfi788-native-agent-20261007-02'
CONFIG_SHA='2f58f39ae08480b5a99b8dbeb11353676681121f4e59d3246ff53ad509b3dc2a'
ROWS_SHA='2fb82852b69428c68a928d7aff503ce6968f739b62b217c7acc6ef92b11b36dd'
TARGET_SCALARS={f'rvfi_instr[{port}].{field}' for port in (0,1) for field in ('halt','trap','valid')} | {
    'rvfi_probes.instr.'+field for field in ('decoded_instr_ack','decoded_instr_valid','fetch_entry_valid','is_compressed','issue_instr_ack')}
PROTECTED_SCALARS={f'{prefix}.{channel}.user' for prefix in
    ('axi_req_o','ariane_narrow_axi_req','ariane_axi_req','ara_axi_req_inval','ara_axi_req','ara_axi_req_delayed')
    for channel in ('ar','aw','w')} | {f'{prefix}.{channel}.user' for prefix in
    ('axi_resp_i','ariane_narrow_axi_resp','ariane_axi_resp','ara_axi_resp_inval','ara_axi_resp','ara_axi_resp_delayed')
    for channel in ('r','b')}
ARRAYS={
    'rvfi_probes.instr.wdata':(1,0,63,0), 'rvfi_probes.instr.wbdata':(4,0,63,0),
    'rvfi_probes.instr.commit_instr_result':(1,0,63,0),
    'rvfi_probes.instr.commit_instr_rd':(1,0,4,0), 'rvfi_probes.instr.commit_instr_rs2':(1,0,4,0),
    'rvfi_probes.instr.commit_instr_rs1':(1,0,4,0), 'rvfi_probes.instr.commit_instr_pc':(1,0,63,0),
    'rvfi_probes.instr.rs2':(0,0,63,0), 'rvfi_probes.instr.rs1':(0,0,63,0),
    'rvfi_probes.instr.instruction':(0,0,31,0), 'rvfi_probes.instr.commit_pointer':(1,0,2,0),
    'rvfi_probes.instr.issue_pointer':(0,0,2,0), 'rvfi_probes.csr.pmpaddr_q':(63,0,53,0),
    'rvfi_to_iti.pc':(1,0,63,0), 'verify_wb_valid':(3,0,4,0), 'verify_wb_id':(3,0,4,0,2,0),
    'verify_wb_addr':(3,0,4,0,9,0), 'verify_wb_wdata':(3,0,4,0,63,0), 'verify_wb_be':(3,0,4,0,7,0)}


def label(kind,a,role):
    name=a['name'];aliases=TARGET_SCALARS if role=='target' else PROTECTED_SCALARS
    if name in aliases:
        require(kind=='vectornode' and a.get('left')==a.get('right')=='0','Explicit scalar alias requires compiled[0:0]')
        return name
    if kind=='arrays':
        require(role=='protected' and name in ARRAYS and not a.get('unpackedrange','').strip(), 'Unreviewed array/role')
        dims=tuple(map(int,a['packedrange'].split()))
        require(dims==ARRAYS[name],'Array dimensions differ')
        return name+''.join('[%d]'%left if left==right else '[%d:%d]'%(left,right)
            for left,right in zip(dims[::2],dims[1::2]))
    require(kind in ('node','vectornode'),'Unknown compiled kind')
    return name+('[%s:%s]'%(a['left'],a['right']) if kind=='vectornode' else '')


def bindings(review):
    result=[]
    for role,points in (('target',review['targets']),('protected',review['protected'])):
        for p in points:
            kind=p['compiled_kind'] if role=='target' else p['kind'];a=p['attributes']
            result.append(dict(role=role,compiled_kind=kind,compiled_attributes=a,
                compiled_name=a['name'],compiled_label=a['name']+('[%s:%s]'%(a['left'],a['right']) if kind=='vectornode' else ''),
                observed_label=label(kind,a,role),width=p.get('width') if role=='target' else None))
    require(len(result)==len({p['compiled_name'] for p in result})==len({p['observed_label'] for p in result})==1206,
        'Not exact1206 compiled/native bijection')
    require({p['compiled_name'] for p in result if p['role']=='target' and p['compiled_name'] in TARGET_SCALARS}==TARGET_SCALARS
        and {p['compiled_name'] for p in result if p['role']=='protected' and p['compiled_name'] in PROTECTED_SCALARS}==PROTECTED_SCALARS,
        'Missing explicit alias inventory')
    require(sum(p['role']=='target' for p in result)==788 and sum(p['width'] for p in result if p['role']=='target')==22126
        and sum(p['role']=='protected' for p in result)==418,'Typed target/protection counts differ')
    return result


def parse(path,rows,stage='before'):
    require(stage in ('before','selected','reset','reloaded','final'),'Unknown stage')
    expected={p['observed_label']:p for p in rows};active=stage in ('selected','reloaded')
    with Path(path).open(newline='') as f:
        reader=csv.DictReader(f,delimiter='\t')
        require(reader.fieldnames==['handle','path','meta','name','excluded'],'Wrong native inventory schema')
        native=list(reader)
    require(len(native)==1206 and all(set(p)==set(reader.fieldnames) and all(p.values()) for p in native),'Incomplete native inventory')
    require(len({p['handle'] for p in native})==len({p['path'] for p in native})==len({p['name'] for p in native})==1206,
        'Duplicate native handle/path/name')
    require(all(p['path']==p['meta']==p['name'] and p['excluded'] in ('0','1') for p in native),
        'Observed exact path/meta/name contract differs')
    require({p['name'] for p in native}==set(expected),'Missing/foreign full compiled complement')
    for p in native:
        want=str(int(active and expected[p['name']]['role']=='target'))
        require(p['excluded']==want,'Target/protected exclusion differs: '+p['name'])
    return sorted((p['path'],p['meta'],p['name']) for p in native)


def audit(output):
    config=life.read_bound(ORIGIN/'config.json',CONFIG_SHA)
    r=life.read_bound(original.REVIEW,original.REVIEW_SHA)
    life.check(config['pins']);life.check(r['pins'])
    require(config['targets']==r['targets'] and config['source_review_sha256']==original.REVIEW_SHA
        and config['context_population']==763,'Frozen source/capture candidate mismatch')
    protected=[]
    for p in r['protected']:
        a=p['attributes'];protected.append(dict(p,label=a['name']+('[%s:%s]'%(a['left'],a['right']) if p['kind']=='vectornode' else '')))
    require(config['protected']==protected,'Protected typed complement drift')
    path=ORIGIN/'native_before.tsv';require(life.digest(path)==ROWS_SHA,'Preserved native02 rows drift')
    bound=bindings(r);actual=parse(path,bound)
    pins=life.merge_pins(config['pins'],{str(ORIGIN/'config.json'):CONFIG_SHA,str(path):ROWS_SHA,
        str(original.REVIEW):original.REVIEW_SHA,str(Path(__file__).resolve()):life.digest(Path(__file__).resolve()),
        str(Path(__file__).with_name('test_system_rvfi_native_binding.py')):life.digest(Path(__file__).with_name('test_system_rvfi_native_binding.py'))})
    life.check(pins)
    result=dict(status='RVFI02_FULL1206_OFFLINE_TYPED_NATIVE_BINDING_VERIFIED_NOT_EXCLUSION_QUALIFICATION',
        scope=original.review.SCOPE,toggle_checksum='3385959260',module_checksum=config['module_checksum'],
        source_review_sha256=original.REVIEW_SHA,origin_config_sha256=CONFIG_SHA,origin_rows_sha256=ROWS_SHA,
        targets=788,target_bits=22126,protected=418,target_scalar_aliases=11,protected_scalar_aliases=30,
        protected_arrays=19,bindings=bound,native_identity_rows=actual,all_before_exclusions_zero=True,
        explicit_aliases_only=True,no_source_or_complement_change=True,EL_serialization_not_yet_observed=True,
        native_save_reload_qualified=False,EDA_launched=False,pins=pins)
    life.save(output,result)
    print(json.dumps(dict(path=str(output),seal=life.digest(output),targets=788,protected=418,aliases=41,arrays=19)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(a.output.absolute().parent==life.OUT and not a.output.exists(),'Fresh offline output required')
    audit(a.output.absolute())
