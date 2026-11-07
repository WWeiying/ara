"""Exact reversible integer-engine clone for an optional balanced matrix dot."""

import hashlib

from audit import require


INT_SHA = '6113e5366f72722491aeabb5478e3e20c89423988021c153126270c64077754d'

BALANCED_CORRECTIONS = '''  if (BalancedMatrixDot) begin : gen_balanced_corrections
    typedef struct packed {
      logic first_valid;
      logic [2:0] first_index;
      logic second_valid;
      logic [2:0] second_index;
    } row_selection_t;

    // Parallel prefix counts saturate at two over one row's eight owners.
    function automatic row_selection_t first_two_row(input logic [7:0] pending);
      logic [7:0] any_prefix [4];
      logic [7:0] two_prefix [4];
      row_selection_t selection;
      any_prefix[0] = pending;
      two_prefix[0] = '0;
      for (int level = 0; level < 3; level++) begin
        for (int bit_index = 0; bit_index < 8; bit_index++) begin
          any_prefix[level+1][bit_index] = any_prefix[level][bit_index];
          two_prefix[level+1][bit_index] = two_prefix[level][bit_index];
          if (bit_index >= (1 << level)) begin
            any_prefix[level+1][bit_index] |=
                any_prefix[level][bit_index-(1 << level)];
            two_prefix[level+1][bit_index] |=
                two_prefix[level][bit_index-(1 << level)] |
                (any_prefix[level][bit_index] &
                 any_prefix[level][bit_index-(1 << level)]);
          end
        end
      end
      selection = '0;
      selection.first_valid = any_prefix[3][7];
      selection.second_valid = two_prefix[3][7];
      for (int bit_index = 1; bit_index < 8; bit_index++) begin
        selection.first_index |= 3'(bit_index) & {3{pending[bit_index] &
            ~any_prefix[3][bit_index-1]}};
        selection.second_index |= 3'(bit_index) & {3{pending[bit_index] &
            any_prefix[3][bit_index-1] & ~two_prefix[3][bit_index-1]}};
      end
      return selection;
    endfunction : first_two_row

    logic [2:0] rr_q [4];
    logic [7:0] upper [4], lower [4];
    row_selection_t upper_selection [4], lower_selection [4];
    logic [1:0] selected_valid [4];
    logic [2:0] selected [4][2];
    for (genvar row = 0; row < 4; row++) begin : gen_row
      for (genvar entry = 0; entry < 8; entry++) begin : gen_mask
        wire pending = slot_valid_q[entry / 4][4*row + entry % 4];
        assign upper[row][entry] = pending && 3'(entry) >= rr_q[row];
        assign lower[row][entry] = pending && 3'(entry) < rr_q[row];
      end
      assign upper_selection[row] = first_two_row(upper[row]);
      assign lower_selection[row] = first_two_row(lower[row]);
      assign selected_valid[row][0] = upper_selection[row].first_valid ||
          lower_selection[row].first_valid;
      assign selected[row][0] = upper_selection[row].first_valid
          ? upper_selection[row].first_index : lower_selection[row].first_index;
      // Never skip an older pending legacy owner to use the extra port.
      assign selected[row][1] = upper_selection[row].second_valid
          ? upper_selection[row].second_index : upper_selection[row].first_valid
          ? lower_selection[row].first_index : lower_selection[row].second_index;
      assign selected_valid[row][1] = context_balanced_q[selected[row][1][2]] &&
          (upper_selection[row].second_valid ||
           (upper_selection[row].first_valid && lower_selection[row].first_valid) ||
           lower_selection[row].second_valid);
      always_ff @(posedge clk_i or negedge rst_ni)
        if (!rst_ni) rr_q[row] <= '0;
        else if (selected_valid[row][1]) rr_q[row] <= selected[row][1] + 1'b1;
        else if (selected_valid[row][0]) rr_q[row] <= selected[row][0] + 1'b1;
`ifndef SYNTHESIS
      always @(posedge clk_i)
        if (rst_ni && selected_valid[row][1]) begin
          assert (selected_valid[row][0] && selected[row][0] != selected[row][1] &&
                  context_balanced_q[selected[row][1][2]])
            else $fatal(1, "Balanced correction duplicate or legacy second grant");
        end
`endif
    end
    always_comb begin
      correction_consume = '{default:'0};
      correction_valid = '0;
      correction_context = '{default:'0};
      correction_stream = '{default:'0};
      correction_last_index = correction_rr_q;
      for (int row = 0; row < 4; row++) begin
        for (int port = 0; port < 2; port++) begin
          correction_valid[2*row+port] = selected_valid[row][port];
          correction_context[2*row+port] = selected[row][port][2];
          correction_stream[2*row+port] = {2'(row), selected[row][port][1:0]};
          if (selected_valid[row][port])
            correction_consume[selected[row][port][2]]
                [4*row + unsigned'(selected[row][port][1:0])] = 1'b1;
        end
      end
      correction_consume_any = |correction_valid;
    end
  end else '''


def integer(source):
    """Return the isolated balanced clone and its exact inverse edit recipe."""
    require(hashlib.sha256(source.encode()).hexdigest() == INT_SHA,
            'Frozen integer engine identity differs')
    text = source
    edits = []

    def edit(old, new):
        nonlocal text
        require(text.count(old) == 1, 'Exact balanced integer anchor required: ' + old[:70])
        text = text.replace(old, new, 1)
        edits.append(dict(before=old, after=new))

    edit("  parameter bit WideMatrixDot = 1'b0",
         "  parameter bit WideMatrixDot = 1'b0,\n  parameter bit BalancedMatrixDot = 1'b0")
    edit('  localparam int unsigned CorrectionLanes = WideMatrixDot ? 4 : 2;',
         '''  localparam int unsigned ProductsPerRow = BalancedMatrixDot ? 32 : (WideMatrixDot ? 16 : 8);
  localparam int unsigned CorrectionLanes = BalancedMatrixDot ? 8 : (WideMatrixDot ? 4 : 2);

`ifndef SYNTHESIS
  initial begin
    assert (!BalancedMatrixDot || WideMatrixDot)
      else $fatal(1, "BalancedMatrixDot requires WideMatrixDot");
  end
`endif''')
    edit('  logic [NumContexts-1:0] context_valid_q;',
         '''  logic [NumContexts-1:0] context_valid_q;
  logic context_balanced_q [NumContexts];''')
    edit("        context_profile_q[context_index] <= QBS_WEIGHT_PROFILE_INVALID;",
         """        context_profile_q[context_index] <= QBS_WEIGHT_PROFILE_INVALID;
        context_balanced_q[context_index] <= 1'b0;""")
    edit('        context_profile_q[start_context] <= start_profile_i;',
         '''        context_profile_q[start_context] <= start_profile_i;
        context_balanced_q[start_context] <= BalancedMatrixDot && start_m_i >= 3 &&
            qbs_weight_block_elements(start_profile_i) == 256;''')
    edit('''  qbs_profile_decoder #(
    .CompactRead(CompactRead), .WideMatrixDot(WideMatrixDot)''',
         '''  qbs_profile_decoder_balanced #(
    .CompactRead(CompactRead), .WideMatrixDot(WideMatrixDot),
    .BalancedMatrixDot(BalancedMatrixDot)''')
    edit('  qbs_dot_array #(.WideMatrixDot(WideMatrixDot)) i_dot_array (',
         '''  qbs_dot_array_balanced #(.WideMatrixDot(WideMatrixDot),
      .BalancedMatrixDot(BalancedMatrixDot)) i_dot_array (''')
    edit('  if (!WideMatrixDot) begin : gen_two_corrections',
         BALANCED_CORRECTIONS + 'if (!WideMatrixDot) begin : gen_two_corrections')
    edit('''        k_per = m_q == 1 ? 8 : (m_q == 2 ? 4 :
            (WideMatrixDot && block_elements_q == 256 ? 4 : 2));''',
         '''        k_per = m_q == 1 ? 8 : (m_q == 2 ? 4 :
            (WideMatrixDot && block_elements_q == 256 ? (BalancedMatrixDot ? 8 : 4) : 2));''')
    edit('row_count_q * (WideMatrixDot ? 16 : 8)', 'row_count_q * ProductsPerRow')
    edit("assert (correction_stream[lane][3:2] == 2'(lane))",
         "assert (correction_stream[lane][3:2] == 2'(BalancedMatrixDot ? (lane >> 1) : lane))")
    edit('module qbs_profile_engine_int import qbs_pkg::*; #(',
         'module qbs_profile_engine_int_balanced import qbs_pkg::*; #(')
    edit('endmodule : qbs_profile_engine_int', 'endmodule : qbs_profile_engine_int_balanced')

    restored = text
    for change in reversed(edits):
        require(restored.count(change['after']) == 1, 'Nonreversible balanced integer edit')
        restored = restored.replace(change['after'], change['before'], 1)
    require(restored == source, 'Original integer engine must restore exactly')
    return text, dict(original_sha256=INT_SHA,
                     generated_sha256=hashlib.sha256(text.encode()).hexdigest(),
                     edits=edits, source_reversible=True, default_disabled=True,
                     balanced_requires_wide=True, correction_lanes=8,
                     correction_grants_per_row=2, dot_latency=3, result_ports=1,
                     extra_grant_requires_captured_balanced_wave=True,
                     extra_grant_never_skips_pending_legacy_owner=True,
                     legacy_correction_branches_unchanged=True,
                     pipeline_commit_and_tail_drain_unchanged=True,
                     capacity_counts_physical_slots=True,
                     limits=['Source transform and host policy tests only; no RTL execution or performance acceptance',
                             'Requires separately frozen balanced decoder/dot modules and compute integration'])
