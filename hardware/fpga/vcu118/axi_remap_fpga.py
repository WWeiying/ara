"""FPGA-only local counters for the existing AXI ID remap table.

The original dynamic read/modify/write infers mux -> arithmetic -> demux.
Decoding enables per entry preserves every cycle, including same-entry push/pop.
"""

ORIGINAL = """  // Push and pop table entries.
  always_comb begin
    table_d = table_q;
    if (push_i) begin
      table_d[push_oup_id_i].inp_id  = push_inp_id_i;
      table_d[push_oup_id_i].cnt    += 1;
    end
    if (pop_i) begin
      table_d[pop_oup_id_i].cnt -= 1;
    end
  end
"""

LOCAL_COUNTERS = """  // Decode enables locally: no selected-counter arithmetic on the ID path.
  for (genvar i = 0; i < MaxUniqInpIds; i++) begin : gen_local_count
    logic push_entry, pop_entry;
    assign push_entry = push_i && push_oup_id_i == idx_t'(i);
    assign pop_entry = pop_i && pop_oup_id_i == idx_t'(i);
    always_comb begin
      table_d[i] = table_q[i];
      if (push_entry) table_d[i].inp_id = push_inp_id_i;
      case ({push_entry, pop_entry})
        2'b10: table_d[i].cnt = table_q[i].cnt + cnt_t'(1);
        2'b01: table_d[i].cnt = table_q[i].cnt - cnt_t'(1);
        default: ; // Simultaneous push/pop retains count but updates input ID.
      endcase
    end
  end
"""

def patch_axi_remap(text):
    if text.count(ORIGINAL) != 1 or LOCAL_COUNTERS in text:
        raise RuntimeError("AXI remap table source changed; review FPGA counter patch")
    return text.replace(ORIGINAL, LOCAL_COUNTERS, 1)


def restore_axi_remap(text):
    if text.count(LOCAL_COUNTERS) != 1 or ORIGINAL in text:
        raise RuntimeError("AXI remap FPGA patch missing or changed")
    return text.replace(LOCAL_COUNTERS, ORIGINAL, 1)
