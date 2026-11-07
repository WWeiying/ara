"""Exact reversible, default-OFF clones for a 128-product matrix dot candidate.

Only returns build-input text. Does not write RTL, compile or execute anything.
The caller must also supply balanced profile correction and propagate the new
parameter through its isolated profile engine/controller clones.
"""
import hashlib


DOT_SHA = 'f0817108d4a20c619d5bfa6d61e9918f99d6d00df3561ee504ecd8d635c055d3'
DECODER_SHA = 'f27eb6596ade6cce3c4320cd01f08324a3e226aa10d519f93d8feebd20f0e251'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _clone(source, expected, changes, original_module, clone_module):
    require(isinstance(source, str) and sha(source) == expected, 'Exact original RTL SHA required: ' + original_module)
    changes = [
        ('module-name', 'module ' + original_module, 'module ' + clone_module),
        *changes,
        ('endmodule-name', 'endmodule : ' + original_module, 'endmodule : ' + clone_module),
    ]
    text, edits = source, []
    for label, before, after in changes:
        require(text.count(before) == 1, 'Exact anchor count: ' + label)
        text = text.replace(before, after, 1)
        edits.append(dict(label=label, before=before, after=after, count=1))
    restored = text
    for edit in reversed(edits):
        require(restored.count(edit['after']) == 1, 'Ambiguous reverse anchor: ' + edit['label'])
        restored = restored.replace(edit['after'], edit['before'], 1)
    require(restored == source, 'Nonreversible balanced clone')
    return text, dict(original_sha256=expected, generated_sha256=sha(text), edits=edits,
                      original_module=original_module, generated_module=clone_module,
                      source_reversible=True, default_disabled=True,
                      parameter='BalancedMatrixDot', requires='BalancedMatrixDot implies WideMatrixDot',
                      interfaces_unchanged=True, target_executed=False,
                      limits=['Source transformation and host mathematics only; not compiled RTL acceptance',
                              'Requires matching K cursor and 16-element-subgroup correction service in the caller'])


def dot(source):
    """Return (qbs_dot_array_balanced source, report), pinned to DOT_SHA."""
    parameter = "  parameter bit WideMatrixDot = 1'b0"
    guard = '''  initial begin
    assert (!BalancedMatrixDot || WideMatrixDot)
      else $fatal(1, "BalancedMatrixDot requires WideMatrixDot");
  end
'''
    declarations = '  logic [18:0] oct_sum_bits [4], oct_carry_bits [4];'
    tree_anchor = '  always_comb begin\n    for (int row = 0; row < 4; row++) begin'
    # Reuse each four-product carry-save tree. Two more CSA levels and a
    # single 19-bit carry-propagate sum combine a context's eight products.
    tree = '''  if (BalancedMatrixDot) begin : gen_balanced_octets
    for (genvar row = 0; row < 4; row++) begin : gen_row
      for (genvar ctx = 0; ctx < 4; ctx++) begin : gen_context
        wire [37:0] first = compress3(quad_sum_bits[row][2*ctx],
            quad_carry_bits[row][2*ctx], quad_sum_bits[row][2*ctx+1]);
        wire [37:0] second = compress3(first[18:0], first[37:19],
            quad_carry_bits[row][2*ctx+1]);
        assign balanced_oct_sum[row][ctx] = second[18:0] + second[37:19];
      end
    end
  end else begin : gen_no_balanced_octets
    assign balanced_oct_sum = '{default: '0};
  end

'''
    old_mapping = '''        if (quant_matrix_wide_q) begin
          ctx = slot >> 2;
          lane = slot & 3;'''
    new_mapping = '''        if (BalancedMatrixDot && quant_matrix_wide_q) begin
          ctx = slot >> 3;
          lane = slot & 7;
        end else if (quant_matrix_wide_q) begin
          ctx = slot >> 2;
          lane = slot & 3;'''
    old_selection = '''                if (WideMatrixDot && product_matrix_wide_q)
                  stream_sum_d[row * 4 + ctx] = quad_sum_d[row][ctx];'''
    new_selection = '''                if (BalancedMatrixDot && product_matrix_wide_q)
                  stream_sum_d[row * 4 + ctx] = balanced_oct_sum[row][ctx];
                else if (WideMatrixDot && product_matrix_wide_q)
                  stream_sum_d[row * 4 + ctx] = quad_sum_d[row][ctx];'''
    text, report = _clone(source, DOT_SHA, [
        ('optional-parameter', parameter, parameter + ",\n  parameter bit BalancedMatrixDot = 1'b0"),
        ('product-capacity', '  localparam int unsigned ProductsPerRow = WideMatrixDot ? 16 : 8;',
         '  localparam int unsigned ProductsPerRow = BalancedMatrixDot ? 32 : (WideMatrixDot ? 16 : 8);'),
        ('balanced-sum-wires', declarations, declarations + '\n  logic signed [18:0] balanced_oct_sum [4][4];'),
        ('balanced-eight-product-tree', tree_anchor, tree + tree_anchor),
        ('balanced-product-mapping', old_mapping, new_mapping),
        ('balanced-stream-selection', old_selection, new_selection),
        ('parameter-contract', '`ifndef SYNTHESIS\n', '`ifndef SYNTHESIS\n' + guard),
    ], 'qbs_dot_array', 'qbs_dot_array_balanced')
    report.update(matrix_products_per_row=32, matrix_products_per_cycle=128,
                  matrix_elements_per_stream=8, stream_sum_bits=19, pipeline_register_stages=3,
                  sequential_blocks_unchanged=True, narrow_reductions_unchanged=True,
                  input_qualification='matrix_wide_i; caller supplies M3/M4 and 256-element block qualification')
    return text, report


def decoder(source):
    """Return (qbs_profile_decoder_balanced source, report), pinned to DECODER_SHA."""
    parameter = "  parameter bit WideMatrixDot = 1'b0"
    old = '''    else if (WideMatrixDot && qbs_weight_block_elements(profile_i) == 256)
      k_per_context_o = 4'd4;'''
    new = '''    else if (BalancedMatrixDot && WideMatrixDot && m_i >= 3 &&
             qbs_weight_block_elements(profile_i) == 256)
      k_per_context_o = 4'd8;
    else if (WideMatrixDot && qbs_weight_block_elements(profile_i) == 256)
      k_per_context_o = 4'd4;'''
    guard = '''`ifndef SYNTHESIS
  initial begin
    assert (!BalancedMatrixDot || WideMatrixDot)
      else $fatal(1, "BalancedMatrixDot requires WideMatrixDot");
  end
`endif

'''
    text, report = _clone(source, DECODER_SHA, [
        ('optional-parameter', parameter, parameter + ",\n  parameter bit BalancedMatrixDot = 1'b0"),
        ('balanced-k-step', old, new),
        ('parameter-contract', 'endmodule : qbs_profile_decoder', guard + 'endmodule : qbs_profile_decoder'),
    ], 'qbs_profile_decoder', 'qbs_profile_decoder_balanced')
    report.update(matrix_elements_per_stream=8, profile_arithmetic_unchanged=True,
                  byte_decode_unchanged=True, metadata_unchanged=True, pipeline_stages_added=0,
                  unchanged_modes=['M1:8', 'M2:4', '32-element formats:2', 'BalancedMatrixDot=0:original'])
    return text, report
