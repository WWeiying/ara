#!/usr/bin/env python3
"""Seal existing completed software/reference artifacts without executing them."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from prepare_prefix import OUT, base, save
from reference_check import require


def read(name):
    return json.loads((OUT/name).read_text())


def main():
    require(not (OUT/'READY.json').exists(), 'Already sealed')
    complete=read('preparation_complete.json')
    audit=read('audit01/audit.json')
    window=read('window_audit.json')
    ref=read('reference/reference.json')
    host=read('host/host_gate.json')
    require(complete['status']=='REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT', 'Reference not ready')
    require(audit['exact_calls']==window['calls']==98 and audit['fullcap_checks']==50176 and
            audit['guards']==196 and window['unused_helpers_executed']==0, 'Incomplete scope')
    require(ref['returncode']==0 and ref['firmware_retired_to_htif_store']==window['firmware_to_htif'] and
            len(host['tests'])==10 and all(t['status']=='PASS' for t in host['tests']), 'Incomplete measured gates')
    require(all(r['status']=='REJECTED_AS_EXPECTED' for r in audit['raw_trace_negative_results']) and
            len(audit['raw_trace_negative_results'])==5 and len(window['negative_tests'])==3, 'Offline negatives')
    baseline=read('baseline_pins.json')
    for p,d in baseline.items():
        require(base.sha(Path(p))==d, 'Baseline pin drift: '+p)
    require(base.sha(OUT/'reference/commits.log')==ref['commit_sha256']==window['trace_sha256'], 'Raw drift')
    owned={str(p):base.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
    save(OUT/'READY.json',dict(status='PREPARED_REFERENCE_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT',
        original_child='rvv_permute_restart_e16_m8_ops4',prefix_calls=98,predecessors=97,
        capacity=512,result_checks=50176,guard_checks=196,returned_vstart=98,
        target_encoding='5c880c57',actual_isa='rv64gcv_zvl1024b',reference_attempts=1,
        firmware_retired_to_htif=ref['firmware_retired_to_htif_store'],
        host_positive=1,host_negative=9,offline_negative=8,
        original_stopped_tuple=None,full_child_pass=False,full_parent_pass=False,linux_pass=False,
        vcs_started=False,rtl_modified=False,independent_review_accepted=False,
        soc_elf=complete['soc_elf'],spike_elf=complete['spike_elf'],
        baseline_pins=baseline,owned_pins=owned))
    print('SEALED_PENDING_INDEPENDENT_REVIEW',base.sha(OUT/'READY.json'),len(owned),len(baseline))


if __name__=='__main__':
    main()
