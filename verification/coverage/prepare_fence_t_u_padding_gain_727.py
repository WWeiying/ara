"""Formal727 + scoped qualified singleton candidate; no admission or EDA."""
import argparse
import copy
import json
from pathlib import Path

import collect_fence_t_u_padding_post_v3 as post_tool
import coverage_bitmap_delta as bitmap
import closure_point_inventory as inventory
from inventory_operand_debug import Design

old=post_tool.old
ROOT,OUT,require=old.ROOT,old.OUT,old.require
BASE=OUT/'gap106-offline-admitted-727-parent-20261006-01'
BASE_SHA='918a5cb4b471e1106a10b4e1c76eb996e9803a44c8d4566c0a038d3b697e29d2'
POST=OUT/'fence-t-u-padding-post-parent-727-20261006-01/result.json'
POST_SHA='ae86f14616195603c505c98671bc8d8e5c0a234faad2ab060245beade3dabb11'
DESIGN=OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'
RUN=OUT/'fence-t-u-padding-run-parent-727-20261006-01'
BITMAP_SHA='e251f049f619ca86e4a9578a468ddca8619ac532ead0ed0c5661a7ee3756e0e3'
PREFIX='ara_tb.dut.i_ara_soc.i_system.i_ariane.'
ALLOWED={PREFIX+'controller_i',PREFIX+'csr_regfile_i',PREFIX+'controller_i.i_pad_cnt.i_counter'}


def merge(pins,extra):
    for path,digest in extra.items():
        require(path not in pins or pins[path]==digest,'Conflicting input pin: '+path)
        pins[path]=digest


def check(pins):
    for path,digest in pins.items():require(old.sha(path)==digest,'Input drift: '+path)


def post_contract(record):
    require(record['status']=='SCOPED_SCALAR_FUNCTIONAL_RETIREMENT_PASS_WITH_TWO_UVM_POLICY_ERRORS_NOT_ADMITTED',
            'Wrong scoped qualification status')
    require(record['terminal_source']==post_tool.MODE and record['returncode_unknown'] is True and
            record['OS_returncode'] is None and record['wall_elapsed_seconds'] is None,
            'OS terminal evidence must remain unknown')
    for key in ('cyclequalified','exact_cycle_proof','native_counter_observer_verified',
                'full_ISA_reference_verified','UVM_clean','generic_UVM_override','admissibility_decided',
                'application_approval','relative727_gain_checked'):
        require(record[key] is False,'Unreviewed qualification promotion: '+key)
    require(record['case_specific_scalar_qualifier'] is True and record['frozen_pin_count']==151 and
            record['frozen_pins_pre_and_post_verified'] is True and len(record['frozen_input_pins'])==151,
            'Incomplete frozen inputs')
    require(record['linked_plan_sha256']==old.PLAN_SHA,'Wrong linked plan')
    require(record['uart']['legacy_checks']==458 and record['uart']['extra_checks']==241 and
            record['uart']['software_ceil']==1011,'Wrong complete software audit')
    retired=record['retirement']
    require(retired['status']=='PASS' and retired['retired_records']==retired['opcode_elf_matches']==18853 and
            retired['capture_stores_checked']==195 and len(retired['rounds'])==3 and
            len(retired['independent_trap_stores'])==5 and retired['native_CSR_ceil_parity'] is True,
            'Incomplete focused retirement audit')
    scalar=record['scalar_policy']
    require(scalar['all_retired_records_checked']==18853 and scalar['vector_retirements']==
            scalar['cvx_backend_events']==0 and scalar['UVM_errors_preserved'] is True,
            'Not scalar-only actual trace')
    for name in ('console','vcs_log'):
        p=scalar[name]
        require(p['actual_UVM_errors']==2 and p['actual_UVM_fatals']==0 and
                p['zero_counter_records']==post_tool.policy.COUNT_MESSAGES and
                p['contract']==post_tool.policy.CONTRACT and p['require_contract_promoted'] is False,
                'Unexpected protocol/error policy')


def validate_population(before,single):
    require(before['tests'] and len(before['tests'])==len(set(before['tests']))==727,
            'Formal727 population differs')
    require(single['tests']==[str(RUN/'code.vdb')] and single['tests'][0] not in before['tests'],
            'Not a unique original singleton')
    for value in (before,single):
        require(set(value['metrics'])==set(bitmap.METRICS) and
                sum(len(rows) for rows in value['metrics'].values())==6162,'Incomplete6162 population')
        for rows in value['metrics'].values():
            for row in rows.values():
                require(type(row['width']) is int and row['width']>=0 and
                        0<=int(row['bits'],16)<(1<<row['width']), 'Overflow/malformed raw bitmap')
    pins=copy.deepcopy(before['input_hashes']);merge(pins,single['input_hashes'])
    combined=bitmap.combine(before,single)
    require(combined['tests']==before['tests']+single['tests'] and len(set(combined['tests']))==728,
            'Not exact727 prefix plus singleton')
    changes=[]
    for metric,rows in before['metrics'].items():
        for scope,row in rows.items():
            added=single['metrics'][metric][scope];after=combined['metrics'][metric][scope]
            require(after['bits']==hex(int(row['bits'],16)|int(added['bits'],16)), 'Incomplete raw OR')
            mask=int(after['bits'],16)&~int(row['bits'],16)
            for raw in range(row['width']):
                if mask&(1<<(row['width']-1-raw)):
                    changes.append(dict(scope=scope,metric=metric,raw_index=raw,width=row['width'],
                                        checksum=row['checksum']))
    delta=bitmap.delta(before,combined)
    require(sum(delta['metrics'].values())>0,'No positive fresh727 product gain')
    require(all(p['scope'] in ALLOWED for p in changes),'Gain outside reviewed source path')
    require(sum(delta['metrics'].values())==len(changes),'Gain outside product scope')
    return combined,delta,changes


def verify(output,seal):
    require(output.parent==OUT and output.resolve()==output,'Direct candidate output required')
    require(old.sha(output/'candidate.json')==seal,'Candidate seal differs')
    record=json.loads((output/'candidate.json').read_bytes())
    require(record['status']=='EXACT727_PLUS_SCOPED_FENCE_PADDING_CANDIDATE_NOT_ADMITTED' and
            record['baseline']==str(BASE) and record['baseline_seal']==BASE_SHA and
            record['qualification']==str(POST) and record['qualification_seal']==POST_SHA and
            record['coverage_admitted'] is False and record['application_approval'] is False,
            'Candidate identity/approval differs')
    require(set(record['output_pins'])=={str(output/n) for n in
            ('single-inputs.txt','single-bits.json','combined-bits.json','raw-delta.json',
             'gained-compiled-points.json','target-hits.json','evidence-pins.json','combined-inputs.txt')},
            'Incomplete/foreign candidate product pins')
    check(record['output_pins'])
    pins=json.loads((output/'evidence-pins.json').read_bytes());check(pins)
    require(old.sha(POST)==POST_SHA and old.sha(BASE/'admission-manifest.json')==BASE_SHA,
            'Authoritative post/base differs')
    post_contract(json.loads(POST.read_bytes()))
    require((output/'single-inputs.txt').read_text().splitlines()==[str(DESIGN),str(RUN/'code.vdb')],
            'Singleton design/run differs')
    single=bitmap.collect(output/'single-inputs.txt')
    require(single==json.loads((output/'single-bits.json').read_bytes()),'Actual raw singleton differs')
    before=json.loads((BASE/'combined-bits.json').read_bytes())
    combined,delta,changes=validate_population(before,single)
    require(combined==json.loads((output/'combined-bits.json').read_bytes()) and
            delta==json.loads((output/'raw-delta.json').read_bytes()) and record['raw_delta']==delta['metrics'],
            'Complete OR/delta replay differs')
    require((output/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*combined['tests']],
            'Not exact727 prefix')
    gained=json.loads((output/'gained-compiled-points.json').read_bytes())
    require([{k:p[k] for k in ('scope','metric','raw_index','width','checksum')} for p in gained]==changes and
            record['gained_positions']==len(gained) and record['full_OR_instances']==6162,
            'Incomplete gained coordinates')
    check(pins);check(record['output_pins'])
    print('FENCE_PADDING_EXACT727_CANDIDATE_REVERIFIED_NOT_ADMITTED '+seal)


def prepare(output):
    require(output.parent==OUT and not output.exists() and output.resolve()==output,'Fresh candidate output required')
    pins={}
    def pin(path,digest=None):
        path=Path(path).absolute();actual=old.sha(path)
        require(digest is None or actual==digest,'Seal differs: '+str(path))
        merge(pins,{str(path):actual});return path
    def load(path,digest=None):return json.loads(pin(path,digest).read_bytes())
    record=load(POST,POST_SHA);post_contract(record)
    merge(pins,record['frozen_input_pins']);merge(pins,record['output_pins']);merge(pins,record['collector_pins'])
    linked=load(old.PLAN,old.PLAN_SHA)
    require(record['frozen_input_pins']==linked['pins'],'Dropped/changed151 frozen pins')
    manifest=load(BASE/'admission-manifest.json',BASE_SHA)
    require(manifest['schema']=='GAP106_HISTORICAL727_SOFTWARE_NATIVE_ADMISSION_V1' and
            manifest['output']==str(BASE) and all(Path(p).parent==BASE for p in manifest['output_pins']),
            'Wrong authoritative727')
    merge(pins,manifest['output_pins'])
    before=load(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    status=load(BASE/'status.json',pins[str(BASE/'status.json')])
    require(status['coverage_admitted'] is True and status['aggregate_passed']==727 and
            status['status']=='PASS_RAW_UNION_HISTORICAL_ONLY','727 is not formally admitted')
    require((BASE/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*before['tests']],
            'Formal727 input/design order differs')
    merge(pins,before['input_hashes'])
    db=DESIGN/'snps/coverage/db'
    for relative,digest in before['design'].items():pin(db/relative,digest)
    pin(Path(bitmap.__file__).resolve(),BITMAP_SHA)
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_prepare_fence_t_u_padding_gain_727.py'),
                 Path(inventory.__file__).resolve(),ROOT/'verification/coverage/inventory_operand_debug.py',
                 ROOT/'verification/coverage/reviewed_20261004/audit_readonly.py',
                 ROOT/'verification/coverage/closure_scorecard.py'):pin(path)
    for metric in ('line','cond','branch','tgl'):
        pin(db/('shape/'+metric+'.verilog.info.xml'))
    pin(db/'shape/tgl.verilog.shape.xml');pin(db/'auxiliary/verilog.sourceinfo.xml')
    sourcepins_path=OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    sourcepins=load(sourcepins_path,pins[str(sourcepins_path)])
    static=load(OUT/'fence-t-u-padding-static-agent-727-v2-20261006-01/review.json',
                'b7db0d745971f16654d3ed007811c627f2825fa6af574607e8137622f1fcf30f')
    check(pins)
    output.mkdir()
    try:
        inputs=output/'single-inputs.txt';inputs.write_text(str(DESIGN)+'\n'+str(RUN/'code.vdb')+'\n')
        single=bitmap.collect(inputs)
        require(all(record['output_pins'].get(p)==h for p,h in single['input_hashes'].items()),
                'Singleton raw inputs not qualified post outputs')
        combined,delta,gained=validate_population(before,single)
        design=Design(DESIGN);cond=inventory.read_xml(db/'shape/cond.verilog.shape.xml')
        infos={m:{n.get('name'):n.get('chksum') for n in inventory.read_xml(
            db/('shape/'+m+'.verilog.info.xml')).iter('instance_data')} for m in ('line','cond','branch')}
        for item in gained:
            scope,metric=item['scope'],item['metric'];module=design.hierarchy[scope]
            require(metric in ('line','cond','branch'),'Unreviewed FSM gain')
            if metric=='cond':node=inventory.definition(cond,module,item['checksum'])
            else:node=design.definition(scope,metric)
            effective=inventory.metric_checksum(item['checksum'],infos[metric].get(scope))
            if effective is None:
                require(scope==PREFIX+'controller_i.i_pad_cnt.i_counter' and metric=='branch' and
                        module.get('id')=='-14' and module.get('chksum')=='2931326076' and
                        node.get('chksum')=='2355591505' and item['width']==7,
                        'Unreviewed absent raw/info checksum')
                binding='unique_compiled_delta_counter_module_id_checksum_width; raw/info checksum remains None'
            else:
                require(node.get('chksum')==effective,'Compiled definition differs')
                binding='exact_metric_info_and_optional_raw_checksum'
            points={p['raw_index']:p for p in inventory.points(metric,node,item['width'])}
            point=points[item['raw_index']];source=Path(design.sources[point['file_id']]['name']).absolute()
            pin(source,sourcepins[str(source)])
            item.update(point=point,compiled_definition=dict(node.attrib),module=dict(module.attrib),
                        source=str(source),source_sha256=pins[str(source)],binding=binding,
                        DVE_native_qualified=False)
        targets=[]
        for group,rows in (('primary',static['targets']),('witness',static['padding_predicate_branch_witnesses'])):
            for target in rows:
                row=single['metrics'][target['metric']][target['scope']];raw=target['raw_index']
                require(row['width']==target['width'] and row['checksum']==target['definition_checksum'],
                        'Static target shape differs')
                hit=bool(int(row['bits'],16)&(1<<(row['width']-1-raw)))
                targets.append(dict(scope=target['scope'],metric=target['metric'],raw_index=raw,
                                    role=group,before_hit=target['hit727'],single_hit=hit,
                                    after_hit=hit or target['hit727'],compiled_point=target['compiled_point']))
        merge(pins,single['input_hashes']);check(pins)
        products={'single-bits.json':single,'combined-bits.json':combined,'raw-delta.json':delta,
                  'gained-compiled-points.json':gained,'target-hits.json':targets,'evidence-pins.json':pins}
        for name,value in products.items():(output/name).write_text(json.dumps(value,indent=2)+'\n')
        (output/'combined-inputs.txt').write_text(str(DESIGN)+'\n'+'\n'.join(combined['tests'])+'\n')
        product_pins={str(p):old.sha(p) for p in output.iterdir() if p.is_file()}
        candidate=dict(status='EXACT727_PLUS_SCOPED_FENCE_PADDING_CANDIDATE_NOT_ADMITTED',
                       baseline=str(BASE),baseline_seal=BASE_SHA,qualification=str(POST),qualification_seal=POST_SHA,
                       exact727_prefix=True,full_OR_instances=6162,proposed_population=728,
                       raw_delta=delta['metrics'],gained_positions=len(gained),
                       coverage_admitted=False,application_approval=False,full_ISA_reference_verified=False,
                       cyclequalified=False,UVM_clean=False,expected_UVM_policy_errors=2,
                       OS_returncode_unknown=True,historical_fixed_image_only=True,
                       simulation_started=False,rtl_changed=False,output_pins=product_pins)
        (output/'candidate.json').write_text(json.dumps(candidate,indent=2)+'\n')
        seal=old.sha(output/'candidate.json')
        (output/'seal.json').write_text(json.dumps(dict(candidate_sha256=seal))+'\n')
        print(json.dumps(dict(output=str(output),seal=seal,delta=delta['metrics'],gained=len(gained),pins=len(pins))))
    except Exception as error:
        (output/'failure.json').write_text(json.dumps(dict(status='REJECTED_NOT_ADMITTED',reason=str(error)))+'\n')
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--verify-seal')
    args=parser.parse_args()
    if args.verify_seal:verify(args.output.absolute(),args.verify_seal)
    else:prepare(args.output.absolute())
