#!/usr/bin/env python3
"""Discriminate a skipped-word RAW hazard from bad mask-load data/addressing."""
import sys

sys.dont_write_bytecode = True
import capture_current as original

base_profile = original.profile


def profile():
    signals = base_profile()
    lane = original.ARA + '.gen_lanes[0].i_lane'
    requester = lane + '.i_operand_requester'
    for field in ('requester_metadata_q', 'stall', 'vinsn_result_written_q',
                  'global_hazard_table_i', 'operand_requester_gnt',
                  'ldu_result_req_i', 'ldu_result_gnt_o', 'ldu_result_addr_i',
                  'ldu_result_wdata_i', 'ldu_result_be_i', 'ldu_result_id_i',
                  'ldu_result_gnt', 'ldu_result_addr', 'ldu_result_wdata',
                  'ldu_result_be', 'ldu_result_id', 'vrf_tgt_opqueue_o',
                  'vrf_addr_o', 'vrf_req_o', 'vrf_wen_o', 'vrf_be_o',
                  'vrf_wdata_o'):
        signals.append(requester + '.' + field)
    return signals


if __name__ == '__main__':
    original.profile = profile
    raise SystemExit(original.main())
