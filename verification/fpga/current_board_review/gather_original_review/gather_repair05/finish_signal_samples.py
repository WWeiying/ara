#!/usr/bin/env python3
"""Read already converted waveforms for actual source grants and result writes."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / 'comparison'))
from decode_cycle import vcd
ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
MASK = ARA + '.i_masku'


for folder in sorted((HERE / 'focused01').glob('gather_probe_*')):
    iterator = iter(vcd(folder / 'normalized.vcd'))
    _, decl = next(iterator)
    clk = decl['ara_tb.clk']['code']
    cycle_code = decl['ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q']['code']
    def get(state, path):
        code = decl.get(path, {}).get('code')
        bits = state.get(code, 'x')
        return int(bits, 2) if set(bits) <= set('01') else None
    vids, grants, payloads, writes = {}, [], [], []
    for timestamp, before, after in iterator:
        if before.get(clk) != '0' or after.get(clk) != '1':
            continue
        cycle = int(before.get(cycle_code, '0'), 2)
        for lane in range(4):
            scope = ARA + '.gen_lanes[%d].i_lane' % lane
            req = scope + '.i_operand_requester'
            valid, ready = get(before, scope+'.operand_request_valid'), get(before, scope+'.operand_request_ready')
            if get(before,scope+'.operand_request[0].vs') == 16 and valid is not None and ready is not None and valid & ready & 1:
                vids[lane] = get(before,scope+'.operand_request[0].id')
            if lane in vids and get(before,req+'.requester_metadata_q[0].id') == vids[lane]:
                grant = get(before,req+'.operand_requester_gnt[0]')
                if grant:
                    grants.append(dict(cycle=cycle,lane=lane,grant=grant,
                        address=get(before,req+'.operand_payload[0].addr'),
                        metadata_address=get(before,req+'.requester_metadata_q[0].addr'),
                        remaining=get(before,req+'.requester_metadata_q[0].len'),
                        eew=get(before,req+'.requester_metadata_q[0].vew')))
                valid_payload = get(before,scope+'.operand_queue_input_valid')
                if valid_payload is not None and valid_payload & 1:
                    payloads.append(dict(cycle=cycle,lane=lane,
                        data=get(before,scope+'.operand_queue_input[0]')))
            valid_write, ready_write = get(before,MASK+'.masku_result_req_o'), get(before,MASK+'.masku_result_gnt_i')
            if valid_write is not None and ready_write is not None and valid_write & ready_write & (1 << lane):
                writes.append(dict(cycle=cycle,lane=lane,
                    address=get(before,MASK+'.masku_result_addr_o[%d]' % lane),
                    be=get(before,MASK+'.masku_result_be_o[%d]' % lane),
                    data=get(before,MASK+'.masku_result_wdata_o[%d]' % lane)))
    result = dict(name=folder.name, actual_alu_a_grants=grants, actual_index_payloads=payloads,
                  accepted_masku_writes=writes, sampling='pre-rising-edge, actual valid AND ready',
                  no_new_conversion_or_dut=True)
    with (folder / 'signal_samples.json').open('x') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')
    print(folder.name, 'first_grants', grants[:4], flush=True)
    print('lane0_writes', [record for record in writes if record['lane'] == 0], flush=True)
