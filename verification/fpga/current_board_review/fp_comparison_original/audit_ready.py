#!/usr/bin/env python3
"""Bind original failed contexts and independently check prepared references."""
import collections
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from recover import HERE, CAMP, read, save, sha


def main():
    out=HERE/'ready_audit01'
    out.mkdir(exist_ok=False)
    pins={}
    reports={}
    contexts=[]
    parents=read(HERE/'provenance01/parents.json')
    for row in parents:
        p=Path(row['evidence']['failed'][0])
        if p not in reports:
            raw=read(p); reports[p]=raw.get('report',raw); pins[str(p)]=sha(p)
        report=reports[p]
        inputs=[x for x in report['inputs']['cases'] if x['name']==row['name']]
        assert len(inputs)==1 and inputs[0]['sha256']==row['sha256']
        results=[x for x in report['results'] if x['name']==row['name'] and x['status']=='failed']
        assert len(results)==1
        result=results[0]
        details=[x for x in result['output'].splitlines() if x.startswith('RVV_FP_COMPARE_DETAIL ')]
        tuples=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',s)} for s in details]
        contexts.append(dict(name=row['name'],elf_sha256=row['sha256'],report=str(p),status=result['status'],
            retained_details=details,retained_tuples=tuples,
            summary=[s for s in result['output'].splitlines() if s.startswith('RVV_FP_COMPARE_FAIL')],
            caveat='At most20 retained error details; neither complete failing tuple set nor shared cause proof'))
    save(out/'original_contexts.json',contexts)
    prefix_path=CAMP/'rvv_compare_prefix_board232_01.json'
    prefix=read(prefix_path); prefix=prefix.get('report',prefix)
    name='rvv_prefix_fp_compare_unmasked_alias_v8_e16_m8'
    result=next(x for x in prefix['results'] if x['name']==name)
    assert result['status']=='passed' and 'RVV_FP_COMPARE_PASS sew=16 cases=50 errors=0' in result['output']
    assert len(re.findall(r'RVV_FP_COMPARE_BYTE index=\d+ actual=1\b',result['output']))==64
    pins[str(prefix_path)]=sha(prefix_path)
    save(out/'existing_prefix50.json',dict(result=result,new_execution=False,report=str(prefix_path),report_sha256=sha(prefix_path)))
    prep=HERE/'prepared02'
    input_pins=read(prep/'pins.json')
    assert all(sha(Path(p))==h for p,h in input_pins.items())
    provenance=read(prep/'prepared/provenance.json')
    assert all(sha(prep/'prepared'/p)==h for p,h in provenance['files'].items())
    references=read(prep/'reference.json')
    assert {x['id'] for x in references['results']}=={x['id'] for x in provenance['records']}
    reviewed=[]
    for backend in ('spike','soc'):
        programs=read(prep/backend/'programs.json')
        assert programs['provenance_sha256']==sha(prep/'prepared/provenance.json')
        for name,entry in programs['programs'].items():
            assert sha(Path(entry['path']))==entry['sha256']
            pins[entry['path']]=entry['sha256']
            if backend=='spike':
                log=prep/backend/(name+'.spike.log'); text=log.read_text()
                assert all(m in text for m in entry['pass_markers'])
                assert not re.search(r'RVV_FP_COMPARE_(?:FAIL|DETAIL|CAPACITY_FAIL)|BOARD_\w*FAIL|BOARD_REPLAY_TRAP',text)
                vals=re.findall(r'^0x([0-9a-f]+)$',text,re.M)
                assert len(vals)==4 and int(vals[-1],16)==0
                pins[str(log)]=sha(log)
                reviewed.append(dict(id=name,status='RAW_REFERENCE_PASS',elf_sha256=entry['sha256']))
    for p in (Path(__file__),prep/'reference.json',prep/'host.json',prep/'soc/programs.json',
              prep/'spike/programs.json',prep/'address_map.json',prep/'prepared/provenance.json',prep/'pins.json'):
        pins[str(p)]=sha(p)
    save(out/'pins.json',pins)
    save(out/'finding.json',dict(status='READY_3_PREFIXES_HOST_SPIKE_NOT_DUT',original_parent_identities=len(contexts),
        retained_detail_count=sum(len(x['retained_details']) for x in contexts),
        originals_with_retained_equal_flags_data_symptom=sum(any(t['errors']>0 and t['actual_flags']==t['expected_flags'] for t in x['retained_tuples']) for x in contexts),
        source_status=read(HERE/'provenance01/inventory.json')['source_status'],
        host=read(prep/'host.json')['status'],references=reviewed,original_input_pins=len(input_pins),
        prepared_file_pins=len(provenance['files']),all_pins_unchanged=True,dut_launched=False,
        existing_prefix50_reexecuted=False,scope='942 calls across three authentic-source prefixes; no original parent acceptance'))
    print(json.dumps(read(out/'finding.json')))


if __name__=='__main__':
    main()
