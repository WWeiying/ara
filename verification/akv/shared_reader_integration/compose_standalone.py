"""Test-only composition preserving legacy engine testbench port contracts."""
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE_PARAMS = ('AxiDataWidth', 'AxiAddrWidth', 'VAddrWidth', 'PAddrWidth', 'NrLanes', 'VLEN')
TYPE_PARAMS = ('vid_t', 'vaddr_t', 'axi_ar_t', 'axi_r_t', 'exception_t')
PROBES = {
    'reader_probe_plan_state_i': 'i_shared_reader.i_read_engine.plan_state_q',
    'reader_probe_range_count_i': 'i_shared_reader.i_read_engine.range_fifo_count_q',
    'reader_probe_burst_count_i': 'i_shared_reader.i_read_engine.burst_fifo_count_q',
    'reader_probe_ar_valid_i': 'axi_ar_valid_o',
    'reader_probe_ar_ready_i': 'axi_ar_ready_i',
    'reader_probe_r_valid_i': 'axi_r_valid_i',
    'reader_probe_r_ready_i': 'axi_r_ready_o',
}
COUNTERS = {
    'read_range_count_o': 'range_count',
    'read_translation_count_o': 'translation_count',
    'read_ar_count_o': 'ar_count',
    'read_beat_count_o': 'r_beat_count',
    'read_payload_bytes_o': 'payload_byte_count',
    'read_store_wait_cycles_o': 'store_wait_cycles',
    'read_backpressure_cycles_o': 'r_backpressure_cycles',
    'read_outstanding_occupancy_sum_o': 'outstanding_occupancy_sum',
    'read_outstanding_max_o': 'outstanding_max',
    'read_outstanding_full_cycles_o': 'outstanding_full_cycles',
}


def compose(source, kind):
    if kind not in ('qbs', 'akv'):
        raise ValueError('Known engine required')
    header = source[:source.index('\n  );') + len('\n  );')]
    anchor = 'module ' + kind + '_engine'
    if header.count(anchor) != 1 or 'reader_req_t' in header:
        raise ValueError('Need original sealed engine header, not an already extracted interface')
    header = header.replace(anchor, anchor + '_composed', 1)
    parameters = BASE_PARAMS + (('ActivationLookahead', 'SeedRestoreEnable') if kind == 'qbs' else ()) + TYPE_PARAMS
    declared = tuple(re.findall(r'^\s*parameter\s+.+?\s+(\w+)\s*=', header, re.M))
    if declared != parameters:
        raise ValueError('Legacy parameter contract changed')
    lines = [header, '', '  // Test harness only: no alternate production engine implementation.',
        '  `include "shared_reader_types.svh"',
        '  `QBS_AKV_SHARED_READER_TYPEDEF_REQ_T(unit_req_t, VAddrWidth)',
        '  `QBS_AKV_SHARED_READER_TYPEDEF_RSP_T(unit_rsp_t, AxiDataWidth, VAddrWidth, exception_t)',
        '  unit_req_t client_req[2];', '  unit_rsp_t client_rsp[2];', '  logic owner_q;',
        *(f"  logic [{'1' if p == 'read_outstanding_max_o' else '31'}:0] observed_{p};"
          for p in COUNTERS),
        "  assign client_req[1] = '0;",
        '  always_ff @(posedge clk_i or negedge rst_ni) begin',
        "    if (!rst_ni) owner_q <= 1'b0;",
        "    else if (command_valid_i && command_ready_o) owner_q <= 1'b1;",
        "    else if ((success_valid_o || fault_valid_o) && terminal_ready_i) owner_q <= 1'b0;",
        '  end', '', '  ' + kind + '_engine #(',
        *('    .' + p + '(' + p + '),' for p in parameters),
        '    .reader_req_t(unit_req_t), .reader_rsp_t(unit_rsp_t)',
        '  ) i_engine (', '    .reader_req_o(client_req[0]), .reader_rsp_i(client_rsp[0]),',
        *(f'    .{p}(observed_{p}),' for p in COUNTERS)]
    if kind == 'qbs':
        lines += ['`ifndef SYNTHESIS', *(f'    .{p}({value}),' for p, value in PROBES.items()), '`endif']
    lines += ['    .*', '  );', '', '  qbs_akv_shared_reader #(',
        '    .AxiDataWidth(AxiDataWidth), .AxiAddrWidth(AxiAddrWidth),',
        '    .VAddrWidth(VAddrWidth), .PAddrWidth(PAddrWidth),',
        '    .req_t(unit_req_t), .rsp_t(unit_rsp_t),',
        '    .axi_ar_t(axi_ar_t), .axi_r_t(axi_r_t), .exception_t(exception_t)',
        '  ) i_shared_reader (', "    .owner_i({1'b0, owner_q}),",
        "    .command_fire_i({1'b0, command_valid_i && command_ready_o}),",
        '    .client_req_i(client_req), .client_rsp_o(client_rsp),',
        '    .clk_i, .rst_ni, .core_st_pending_i, .en_ld_st_translation_i,',
        '    .mmu_req_o, .mmu_vaddr_o, .mmu_is_store_o, .mmu_valid_i, .mmu_paddr_i,',
        '    .mmu_exception_valid_i, .mmu_exception_i, .physical_check_valid_o,',
        '    .physical_check_addr_o, .physical_check_bytes_o, .physical_range_allowed_i,',
        '    .axi_ar_o, .axi_ar_valid_o, .axi_ar_ready_i,',
        '    .axi_r_i, .axi_r_valid_i, .axi_r_ready_o', '  );', '',
        '  // Old benches read last-command statistics after terminal acknowledgement.',
        '  // During ownership check actual engine outputs; after release expose the',
        '  // real single-client reader counters, never a synthesized/fitted value.',
        *(f'  assign {p} = owner_q ? observed_{p} : i_shared_reader.reader_rsp.{field};'
          for p, field in COUNTERS.items()), 'endmodule', '']
    return '\n'.join(lines)


def adapt_tb(source, kind):
    if kind not in ('qbs', 'akv'):
        raise ValueError('Known engine required')
    anchor = '  ' + kind + '_engine #(\n'
    if source.count(anchor) != 1 or source.count('  ) dut (') != 1:
        raise ValueError('Unexpected DUT instance contract')
    result = source.replace(anchor, '  ' + kind + '_engine_composed #(\n', 1)
    # Hierarchy-only migration; ports, assertions, expected data and tasks stay intact.
    result = re.sub(r'\bdut\.', 'dut.i_engine.', result)
    restored = result.replace('dut.i_engine.', 'dut.').replace(
        '  ' + kind + '_engine_composed #(\n', anchor, 1)
    if restored != source:
        raise ValueError('Adaptation changed more than hierarchy/module naming')
    return result
