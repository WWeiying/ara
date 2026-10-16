"""Separate reset synchronization from replicable UI reset distribution."""

OLD = """    .rst_no(ui_resetn), .init_no()
  );"""
NEW = """    .rst_no(ui_resetn_sync), .init_no()
  );
  // Preserve all four ASYNC_REG stages. Only the extra distribution stage
  // drives UI loads and may be replicated by physical optimization.
  always_ff @(posedge dram_axi_clk or negedge ui_resetn_sync) begin
    if (!ui_resetn_sync) ui_resetn <= 1'b0;
    else ui_resetn <= 1'b1;
  end"""


def patch_ui_reset_distribution(text):
    declaration = "  logic ui_resetn;"
    if text.count(declaration) != 1 or text.count(OLD) != 1:
        raise RuntimeError("UI reset distribution requires one unmodified local reset")
    text = text.replace(declaration, declaration + "\n  logic ui_resetn_sync;", 1)
    return text.replace(OLD, NEW, 1)
