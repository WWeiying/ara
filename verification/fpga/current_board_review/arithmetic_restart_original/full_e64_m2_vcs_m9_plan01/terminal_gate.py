"""Bind actual accepted reference terminal schema, not a Boolean attestation."""
from pathlib import Path
import checker as c
def verify(binding,ready):
    p=Path(binding['path']);t=c.read(p)
    c.require(c.sha(p)==binding['sha256']=='4036aa11044c2e07f19435b6d84b27bb8c843f1b16ed72f5ff8fcc6a68a2ae0d','Exact actual independent terminal')
    c.require(t['status']=='ACCEPTED_REFERENCE_TERMINAL_METADATA_ONLY_NOT_DUT' and t['accepted'] and not t['DUT_admission'] and not t['DUT_acceptance'] and not t['Linux_closure'],'Actual accepted source-only schema')
    c.require([t[k] for k in ('actual_reference_exit','actual_audit_exit','reference_attempts','firmware_to_HTIF','calls','results','guards','helper_instructions','output_reads','FP_calls','FP_input_stores','mask_groups','mask_clear_stores','mask_bit_stores','seed_stores')]==[0,0,1,2263782,5985,191520,11970,77805,203490,1890,120960,2205,35280,38955,276],'Actual reference counts/outcomes')
    c.require(t['producer_EOF_checked'] and not t['reviewer_raw_read_or_parse'] and t['sha256']['READY.json']==c.READY_SHA and binding['READY_sha256']==c.READY_SHA,'Actual terminal READY/EOF identity')
    for n,h in t['sha256'].items():c.require(c.sha(c.REF/n)==h,'Terminal artifact exact hash '+n)
    result=c.read(c.REF/'reference01/result.json')
    c.require(result['raw_sha256']==t['producer_raw_sha256'] and result['raw_bytes']==t['producer_raw_bytes'] and result['whole_raw_rows']==t['producer_whole_raw_rows'],'Same raw artifact metadata, not cross-artifact hashes')
