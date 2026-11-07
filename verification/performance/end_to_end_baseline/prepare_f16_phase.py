#!/usr/bin/env python3
"""Prepare exact-anchor, observation-only F16 D128/GQA2 clones; never compile/run target code."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
SOURCE = RUNS/'e2e_output_graph_20261106_01/sdk/software/akv/src/akv_v2_native_riscv.c'
SOURCE_SHA = 'aff613518b3495df363209beacf0940ef6d8b6c734f4851f63a7aa820d4f692c'
PREFIX = 'akv_attention_execute_v2'
FUNCTIONS = ('with_features_native', 'native', 'prefill_native')
NAMES = {PREFIX+'_'+suffix: 'f16_phase_execute_v2_'+suffix for suffix in FUNCTIONS}
CONTROL = {old:new.replace('f16_phase_', 'f16_phase_control_', 1) for old,new in NAMES.items()}
SIGNATURES = {suffix:'akv_status_t '+PREFIX+'_'+suffix+'(\n' for suffix in FUNCTIONS}


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(data): return hashlib.sha256(data).hexdigest()


def rename(text, mapping):
    for old,new in mapping.items():
        pattern=r'\b'+old+r'(?=\s*\()'
        require(len(re.findall(pattern,text))==(2 if old.endswith('with_features_native') else 1), 'Exact export/call rename: '+old)
        text=re.sub(pattern,new,text)
    return text


def transform(source):
    require(sha(source.encode())==SOURCE_SHA,'Exact frozen native source SHA required')
    for marker in SIGNATURES.values():require(source.count(marker)==1,'Unique public function anchors required')
    a=source.index(SIGNATURES['with_features_native']);b=source.index(SIGNATURES['native']);c=source.index(SIGNATURES['prefill_native'])
    require(a<b<c,'Frozen public function order')
    pieces={'decode':source[a:b], 'prefill':source[c:]}
    records=[]

    def edit(part, label, before, after, count=1):
        text=pieces[part]
        require(text.count(before)==count,f'Exact anchor count {part}/{label}: expected {count}')
        pieces[part]=text.replace(before,after)
        records.append(dict(function=part,label=label,before=before,after=after,occurrences=count))

    def before(part,label,anchor,phase):
        indent=anchor[:len(anchor)-len(anchor.lstrip())]
        edit(part,label,anchor,indent+'F16_PHASE_SWITCH(f16_scope, '+phase+');\n'+anchor)

    entry='    const akv_attention_features_t *features) {\n'
    edit('decode','scope',entry,entry+'  F16_PHASE_SCOPE(f16_scope, plan != NULL && workspace != NULL && features == NULL && plan->descriptor.element_format == AKV_ELEMENT_FORMAT_F16 && plan->descriptor.q_rows == 2u && plan->descriptor.head_dim == 128u && plan->logical_head_dim == 128u && plan->d_segment_count == 1u);\n')
    entry='    akv_attention_v2_prefill_workspace_t *workspace) {\n'
    edit('prefill','scope',entry,entry+'  F16_PHASE_SCOPE(f16_scope, device != NULL && problem != NULL && workspace != NULL && problem->head_dim == 128u && problem->query_tokens == 64u && problem->kv_heads > 0u && problem->kv_heads <= UINT32_MAX/2u && problem->query_heads == 2u*problem->kv_heads);\n')

    anchor='  initialize_workspace(workspace, q_rows, head_dim);'
    before('decode','init',anchor,'F16_PHASE_INIT')
    edit('decode','after_init',anchor,anchor+'\n  F16_PHASE_SWITCH(f16_scope, F16_PHASE_SCHEDULE);')
    anchor='    if (tile_start == 0u)\n      issue_full(&plan->descriptor, 0u);'
    before('decode','kv',anchor,'tile_start == 0u ? F16_PHASE_KV_FULL : F16_PHASE_KV_REFILL')
    anchor='    if (q_rows == AKV_ATTENTION_KERNEL_Q_ROWS &&\n        head_dim == AKV_HEAD_DIM_128) {\n      compute_scores_d128_gqa6('
    before('decode','qk',anchor,'F16_PHASE_QK')
    before('decode','softmax','    apply_scale_mask_and_softmax(mask_bits, scale, workspace, tile_start,','F16_PHASE_SOFTMAX')
    anchor='                                 tile_tokens, q_rows, features);'
    edit('decode','pv',anchor,anchor+'\n    F16_PHASE_SWITCH(f16_scope, F16_PHASE_PV);')
    anchor='          workspace->old_scale, tile_tokens, q_rows, head_dim);\n    }\n  }'
    edit('decode','after_pv',anchor,anchor[:-4]+'\n    F16_PHASE_SWITCH(f16_scope, F16_PHASE_SCHEDULE);\n  }')
    before('decode','release','  issue_release();','F16_PHASE_RELEASE')
    before('decode','normalize','  store_outputs(output, output_row_stride_bytes, workspace, q_rows, head_dim);','F16_PHASE_NORMALIZE')

    before('prefill','query','        convert_prefill_query_block(problem, &layout, workspace, first_qhead,','F16_PHASE_QUERY')
    before('prefill','init','        initialize_prefill_block(problem, &layout, workspace, first_qhead,','F16_PHASE_INIT')
    anchor='                                 token_start, token_count, q_rows);\n      }\n\n      const akv_attention_problem_t context_problem'
    edit('prefill','after_init',anchor,'                                 token_start, token_count, q_rows);\n      }\n      F16_PHASE_SWITCH(f16_scope, F16_PHASE_PREFLIGHT);\n\n      const akv_attention_problem_t context_problem')
    anchor='      if (plan_status != AKV_STATUS_OK) return AKV_STATUS_EXECUTION;'
    edit('prefill','after_plan',anchor,anchor+'\n      F16_PHASE_SWITCH(f16_scope, F16_PHASE_SCHEDULE);')
    before('prefill','kv','        if (tile_start == 0u)\n          issue_full(&workspace->plan.descriptor, 0u);','tile_start == 0u ? F16_PHASE_KV_FULL : F16_PHASE_KV_REFILL')
    before('prefill','after_kv','        const uint32_t resident_tokens =','F16_PHASE_SCHEDULE')
    before('prefill','qk','            if (!use_q2) {','F16_PHASE_QK')
    before('prefill','softmax','            apply_prefill_scale_mask_softmax(','F16_PHASE_SOFTMAX')
    anchor='                q_rows);\n\n            float *const output ='
    edit('prefill','after_softmax',anchor,'                q_rows);\n            F16_PHASE_SWITCH(f16_scope, F16_PHASE_SCHEDULE);\n\n            float *const output =')
    before('prefill','pv','            if (d128_gqa6) {\n              akv_v2_update_outputs_f32_d128_gqa6(','F16_PHASE_PV')
    anchor='                  problem->head_dim);\n            }\n          }\n          local_token += compute_tokens;'
    edit('prefill','after_pv',anchor,'                  problem->head_dim);\n            }\n            F16_PHASE_SWITCH(f16_scope, F16_PHASE_SCHEDULE);\n          }\n          local_token += compute_tokens;')
    before('prefill','release','      issue_release();','F16_PHASE_RELEASE')
    before('prefill','normalize','      normalize_prefill_block(problem, &layout, workspace, first_qhead,','F16_PHASE_NORMALIZE')
    anchor='                              token_start, token_count, q_rows);\n    }\n  }'
    edit('prefill','after_normalize',anchor,'                              token_start, token_count, q_rows);\n      F16_PHASE_SWITCH(f16_scope, F16_PHASE_SCHEDULE);\n    }\n  }')

    for part, expressions in {
        'decode': [('AKV_STATUS_BAD_ARGUMENT',2),('execute_segmented_d256(plan, workspace, features)',1),('AKV_STATUS_OK',1),('AKV_STATUS_RUNTIME_UNAVAILABLE',1)],
        'prefill': [('validation',1),('plan_status',1),('AKV_STATUS_EXECUTION',1),('AKV_STATUS_OK',1),('AKV_STATUS_RUNTIME_UNAVAILABLE',1)],
    }.items():
        for expression,count in expressions:
            edit(part,'return_'+expression,'return '+expression+';', 'F16_PHASE_RETURN(f16_scope, '+expression+');',count)

    # Invert every registered edit before accepting it as observation-only.
    restored=dict(pieces)
    for record in reversed(records):
        part=record['function'];after=record['after']
        require(restored[part].count(after)==record['occurrences'],'Nonreversible observation edit')
        restored[part]=restored[part].replace(after,record['before'])
    require(restored=={'decode':source[a:b],'prefill':source[c:]},'Original computation text must restore byte-for-byte')
    observed=source[:a]+pieces['decode']+source[b:c]+pieces['prefill']
    include='#include "akv_refill_schedule.h"\n'
    require(observed.count(include)==1,'Unique include insertion')
    observed=observed.replace(include,include+'#include "f16_phase_probe.h"\n')
    observed=rename(observed,NAMES)
    control=rename(source,CONTROL)
    return observed,control,dict(original_sha256=SOURCE_SHA,operations=records,
        original_text_reversibility_checked=True,renamed_exports=NAMES,control_exports=CONTROL,
        observed_sha256=sha(observed.encode()),control_sha256=sha(control.encode()),
        nested_observation_regions=0,
        scope='F16 D128 GQA2 Decode with NULL features; F16 KV/F32 Query Prefill M64 GQA2',
        gates=['Decode q_rows2/head_dim128/logical_dim128/segment1/F16/NULL features',
               'Prefill query_tokens64/head_dim128/query_heads=2*kv_heads',
               'Original native forwarder has no nested probe; only with_features entry is timed',
               'No reentrant/concurrent calls or external callbacks into probe clones'],
        untouched='All static helper bodies, D256/GQA6 kernels, callbacks, arithmetic and scheduling text retained',
        accounting=['Sum slots [0,F16_PHASE_EXCLUSIVE_COUNT) only; BARRIER is an overlapping subset',
                    'Barrier interval includes pending useful work; not a subtractable fixed-overhead estimate',
                    'Decode QUERY count is zero: query preparation belongs to external caller',
                    'KV bins observe FULL/REFILL issue/return spans, not independently proved DMA completion',
                    'Unchanged-original vs observed complete-call ABBA comparison is mandatory; renamed control is optional source/compile/ISA audit, not a third target run',
                    'Gate phase fractions on per-workload absolute perturbation <=5% and matching outputs/CSR/status/command counts; no speedup inference'])


def prepare(source,output):
    source=Path(source).resolve(strict=True);output=Path(output).absolute()
    require(output==output.resolve() and output.is_relative_to(RUNS),'Fresh sole-verification output required')
    raw=source.read_bytes();observed,control,report=transform(raw.decode())
    output.mkdir(parents=True,exist_ok=False)
    pins={str(source):sha(raw)}
    for name in ('prepare_f16_phase.py','test_f16_phase.py','f16_phase_probe.h'):
        path=HERE/name;pins[str(path)]=sha(path.read_bytes())
    for name,data in [('native-original.c',raw),('native-control.c',control.encode()),('native-observed.c',observed.encode()),('f16_phase_probe.h',(HERE/'f16_phase_probe.h').read_bytes())]:
        (output/name).write_bytes(data)
    report.update(quote_include_flags=['-iquote',str(output),'-iquote',str(source.parent)],
                  include_policy='Original relative includes retained. Builder must -M and bind actual resolved SDK headers; no live SDK substitution.',
                  required_caller_api=['uint64_t f16_phase_cycles[F16_PHASE_COUNT]', 'uint64_t f16_phase_calls[F16_PHASE_COUNT]', 'void f16_phase_reset(void)'],
                  reset_snapshot='Caller reset zeros both arrays before each isolated call; snapshot and print after completion only')
    (output/'transform.json').write_text(json.dumps(report,indent=2)+'\n')
    require(source.read_bytes()==raw,'Frozen input drift')
    for path,expected in pins.items():require(sha(Path(path).read_bytes())==expected,'Preparation source drift')
    (output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='F16_PHASE_OBSERVATION_CLONES_PREPARED_NOT_BUILT_NOT_EXECUTED',
                source_pins_sha256=sha((output/'source-pins.json').read_bytes()),
                artifacts={str(p):sha(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()},
                target_executed=False,performance_measured=False,rtl_changed=False,
                original_source_sha256=SOURCE_SHA,observed_sha256=report['observed_sha256'],control_sha256=report['control_sha256'])
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.source,args.output),indent=2))
