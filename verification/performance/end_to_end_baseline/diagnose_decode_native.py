#!/usr/bin/env python3
"""Account real M1 SDK regions and service bounds without model-time extrapolation."""
import argparse
import json
from pathlib import Path

from audit import digest,require,verify_pins
from collect_decode_native import collect

NAMES=('Q','V','K','gate','up','down','vocabulary')


def explain(m):
    require(m['commands']==28 and m['useful_pairs']==2359296 and len(m['parts'])==len(m['activity'])==7,
            'Not the accepted real Decode SDK scope')
    totals=m['total'];outside=m['total']['execution']-m['qbs_busy_cycles']
    control=totals['region']-sum(totals[k] for k in ('preparation','admission','execution'))
    require(outside>=0 and control>=0,'Invalid CPU interval accounting')
    rows=[]
    for name,part,a in zip(NAMES,m['parts'],m['activity']):
        c=a['counters'];busy=c['busy_cycles'];floor=max(c['dot_active_cycles'],c['r_beats'])
        require(busy>=floor>0 and part['execution']>=busy and c['weight_bytes']+a['activation_axi_payload_bytes']+64==c['payload_bytes'],
                'Invalid service/byte accounting')
        rows.append(dict(name=name,k=part['k'],profile=part['profile'],sdk_execution=part['execution'],
            qbs_busy=busy,dot_issue=c['dot_active_cycles'],r_beats=c['r_beats'],ar=c['ar'],
            r_transfer_duty_in_busy=c['r_beats']/busy,weight_payload_bytes=c['weight_bytes'],
            activation_axi_payload_bytes=a['activation_axi_payload_bytes'],context_bytes_saved=c['activation_axi_bytes_saved'],
            strict_weight_wait=c['weight_prefetch_wait_cycles'],
            strict_wait_no_outstanding=c['probe_weight_wait_no_outstanding_cycles'],
            strict_wait_response_idle=c['probe_weight_wait_response_idle_cycles'],
            strict_wait_r_transfer=c['probe_weight_wait_r_transfer_cycles'],strict_wait_r_blocked=c['probe_weight_wait_r_blocked_cycles'],
            fp_input_blocked=c['probe_fp_input_blocked_cycles'],result_blocked=c['probe_profile_result_blocked_cycles'],
            sdk_outside_busy=part['execution']-busy,
            unchanged_service_cycle_floor=floor,
            ideal_busy_ratio_if_all_work_above_service_floor_disappeared=busy/floor))
    return dict(total=totals,parts=rows,cpu_outside_qbs_busy_cycles=outside,
        unclassified_region_control_cycles=control,
        context_counts={key:sum(a['counters'][key] for a in m['activity']) for key in
            ('context_fill_count','context_reuse_count','context_read_bytes','activation_axi_bytes_saved')},
        physical_reader_totals={key:sum(a['counters'][key] for a in m['activity']) for key in
            ('ar','r_beats','payload_bytes','weight_bytes')},
        activation_axi_payload_bytes=sum(a['activation_axi_payload_bytes'] for a in m['activity']),
        current_region_preparation_fraction=totals['preparation']/totals['region'],
        sdk_outside_busy_fraction=outside/totals['execution'],
        no_observed_fp_input_or_result_backpressure=all(r['fp_input_blocked']==r['result_blocked']==0 for r in rows),
        limitations=['N128 prefixes have different preparation/admission amortization from full N',
            'Same ELF/program counters; not complete GGML or whole-model timing',
            'R beats use the audited 128-bit AXI interface; bytes are not board DDR bandwidth',
            'max(dot,R) is a service lower bound, not an attainable schedule or an additive stall breakdown',
            'Strict weight-wait buckets observe the shared reader, not only weight responses'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();audit=args.audit.resolve(strict=True);out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result=dict(state='CHECKING',whole_model=False,area_measured=False)
    try:
        pins={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('audit.py'),
            Path(__file__).with_name('collect_decode_native.py'),Path(__file__).with_name('check_decode_native.py'),audit)}
        accepted=json.loads(audit.read_text())
        require(accepted['state']=='REAL_QWEN3_DECODE_SDK_BASELINE_REAUDITED','Unaccepted Decode audit')
        report=collect(Path(accepted['report']['run']));require(report==accepted['report'],'Independent audit replay differs')
        measured=explain(report['measured']);verify_pins(pins)
        result.update(state='REAL_QWEN3_DECODE_SERVICE_ACCOUNTING_PASS',diagnosis=measured,
                      audit=str(audit),audit_sha256=digest(audit),source_pins=pins)
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
