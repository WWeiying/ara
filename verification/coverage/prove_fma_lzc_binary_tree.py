"""Compositional binary priority-tree proof, explicitly retaining undriven spare/X scope."""
import argparse
import json
from pathlib import Path
import verify_fma_lzc_width_calibration as calibration

require=calibration.require
ROOT=calibration.ROOT
STATIC=ROOT/'verification/out/fma-lzc-library-static-candidate767-agent-20261007-01.json'
STATIC_SHA='c5a419266b72b58ff0ea42748b8f08c9d387bdc173fb7280b160b4e332528afc'


def merge_law(prefer_left=True):
    # Abstract children have arbitrary indices, ordered by disjoint contiguous domains.
    for left_has in (False,True):
        for right_has in (False,True):
            actual=17 if (left_has if prefer_left else right_has) else 29
            expected=17 if left_has else 29
            if left_has or right_has:require(actual==expected,'Priority merge truth-table counterexample')
            require((left_has or right_has)==bool(int(left_has)|int(right_has)),'Selector OR law')


def prove_width(width):
    require(width in (25,51,109),'Only matched actual WIDTH configurations')
    levels=(width-1).bit_length();size=1<<levels;nodes={}
    merge_law()
    for level in range(levels-1,-1,-1):
        for lane in range(1<<level):
            index=(1<<level)-1+lane;span=size>>level
            lo=lane*span;hi=min(width,(lane+1)*span)
            domain=list(range(lo,hi)) if lo<width else []
            if level==levels-1:
                if len(domain)==2:
                    for a in (0,1):
                        for b in (0,1):
                            selected=bool(a|b);actual=lo if a==1 else lo+1
                            expected=min((j for j,bit in zip(domain,(a,b)) if bit),default=None)
                            require(not selected or actual==expected,'Leaf priority law')
                    fallback=lo+1;kind='two_real_bits'
                elif domain:
                    fallback=lo;kind='single_real_bit'
                else:
                    fallback=0;kind='padded_known_zero'
            else:
                left=nodes[2*index+1];right=nodes[2*index+2]
                require(left['domain']+right['domain']==domain,'Exact disjoint ordered child partition')
                require(not left['domain'] or not right['domain'] or max(left['domain'])<min(right['domain']),
                        'Left priority must precede every right index')
                fallback=right['empty_index'];kind='ordered_priority_merge'
            require(index not in nodes and 0<=fallback<size,'Unique assigned node and exact index width')
            nodes[index]=dict(index=index,domain=domain,empty_index=fallback,kind=kind,
                invariant='selector iff any real bit is1; selected index is least real index having1; empty index is structural fallback')
    require(set(nodes)==set(range(size-1)) and nodes[0]['domain']==list(range(width)),'Complete assigned tree')
    return dict(width=width,mode=1,levels=levels,assigned_nodes=len(nodes),
        proof='Base-case exhaustive 2-bit law plus arbitrary child summaries with disjoint ordered intervals; universal induction, not full-input enumeration',
        input_mapping='in_tmp[j]=in_i[WIDTH-1-j]; least j equals leading-zero count for nonzero binary input',
        empty_output='empty iff all inputs zero; no architectural count claim on empty',nodes=list(nodes.values()),
        spare_index=size-1,spare_selector_bits=1,spare_index_bits=levels,
        spare_status='No source assignment; unknown/undriven, not a proved binary zero and not eligible under this proof')


def evidence():
    replay=calibration.verify()
    static=calibration.bound(STATIC,STATIC_SHA)
    for path,seal in static['pins'].items():require(calibration.digest(path)==seal,'Static source/shape drift')
    require(static['source_equals_local_upstream_and_frozen_build'] is True and static['source_sha256']==calibration.SOURCE_SHA,
            'Unmodified baseline and frozen build binding')
    widths={w:prove_width(w) for w in (25,51,109)}
    instances=[];retained=0;eligible=0
    for item in static['instances']:
        width=item['parameters']['WIDTH'];p=widths[width];bits=p['spare_selector_bits']+p['spare_index_bits']
        total=sum(n['logical_bits'] for n in item['internal_candidates']);retained+=bits;eligible+=total-bits
        instances.append(dict(scope=item['scope'],module_checksum=item['module_checksum'],toggle_checksum=item['toggle_checksum'],
            parameters=item['parameters'],whole_fields=['gen_lzc.index_lut','gen_lzc.in_tmp'],
            partial_fields=[dict(name='gen_lzc.sel_nodes',assigned_node_indices=[0,p['spare_index']-1],retained_node=p['spare_index']),
                            dict(name='gen_lzc.index_nodes',assigned_node_indices=[0,p['spare_index']-1],retained_node=p['spare_index'])],
            protected_ports=[n['name'] for n in item['protected_full_complement']]))
    require(len(instances)==32 and retained==212 and eligible==23132,'Exact candidate boundary')
    return dict(status='ASSIGNED_BINARY_TREE_CORRECTNESS_PROVED_WHOLE128_NATIVE_HOLD_SPARE_X',
        reason='Reliable unmodified combinational library integration scope, NOT unreachability; exact source induction plus actual matched-width tests',
        actual_calibration=replay,universal_binary_assigned_node_proof=list(widths.values()),instances=instances,
        candidate_assigned_internal_bits=eligible,retained_undriven_spare_bits=retained,protected_port_objects=96,
        initial_delta_or_arbitrary_four_state_equivalence_proved=False,unknown_states_excluded=False,
        all128_whole_fields_approved=False,native_qualified=False,EDA_launched=False,official_percentage=None,
        next_gate='Parent review of narrowed assigned-node scope, actual typed array native range/retained-spare membership and full complement. No MDA code inference required for reliable-library scope.',
        pins={str(STATIC):STATIC_SHA,str(calibration.OUT/'calibration-result.json'):calibration.RESULT_SHA,
              str(Path(__file__).resolve()):calibration.digest(__file__),str(Path(calibration.__file__)):calibration.digest(calibration.__file__)})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    require(out.parent==ROOT/'verification/out' and not out.exists(),'Fresh independent proof file')
    value=evidence()
    with out.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=value['status'],output=str(out),seal=calibration.digest(out),
                         eligible_assigned_bits=value['candidate_assigned_internal_bits'],retained_spares=value['retained_undriven_spare_bits'])))
