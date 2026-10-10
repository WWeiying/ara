package ara_cvxif_uvm_pkg;
  import uvm_pkg::*;
  `include "uvm_macros.svh"

  class cvxif_transaction #(int unsigned Xlen = 64,
                            int unsigned TransIdW = 4) extends uvm_sequence_item;
    bit                reset;
    bit                req_fire;
    bit                resp_fire;
    int unsigned       cycle;
    int unsigned       reset_epoch;
    bit [TransIdW-1:0] req_trans_id;
    bit [TransIdW-1:0] resp_trans_id;
    bit [31:0]         insn;
    bit [Xlen-1:0]     rs1;
    bit [Xlen-1:0]     rs2;
    bit [Xlen-1:0]     result;
    bit                exception_valid;
    bit                backend_alloc;
    bit [2:0]          backend_alloc_id;
    bit [7:0]          backend_done;
    bit                axi_ar_fire;
    bit [7:0]          axi_ar_id;
    bit [7:0]          axi_ar_len;
    bit                axi_r_fire;
    bit [7:0]          axi_r_id;
    bit                axi_r_last;
    bit                axi_aw_fire;
    bit [7:0]          axi_aw_id;
    bit [7:0]          axi_aw_len;
    bit                axi_w_fire;
    bit                axi_w_last;
    bit                axi_b_fire;
    bit [7:0]          axi_b_id;

    `uvm_object_param_utils_begin(cvxif_transaction #(Xlen, TransIdW))
      `uvm_field_int(reset, UVM_DEFAULT)
      `uvm_field_int(req_fire, UVM_DEFAULT)
      `uvm_field_int(resp_fire, UVM_DEFAULT)
      `uvm_field_int(cycle, UVM_DEFAULT)
      `uvm_field_int(reset_epoch, UVM_DEFAULT)
      `uvm_field_int(req_trans_id, UVM_DEFAULT)
      `uvm_field_int(resp_trans_id, UVM_DEFAULT)
      `uvm_field_int(insn, UVM_DEFAULT)
      `uvm_field_int(rs1, UVM_DEFAULT)
      `uvm_field_int(rs2, UVM_DEFAULT)
      `uvm_field_int(result, UVM_DEFAULT)
      `uvm_field_int(exception_valid, UVM_DEFAULT)
      `uvm_field_int(backend_alloc, UVM_DEFAULT)
      `uvm_field_int(backend_alloc_id, UVM_DEFAULT)
      `uvm_field_int(backend_done, UVM_DEFAULT)
      `uvm_field_int(axi_ar_fire, UVM_DEFAULT)
      `uvm_field_int(axi_ar_id, UVM_DEFAULT)
      `uvm_field_int(axi_ar_len, UVM_DEFAULT)
      `uvm_field_int(axi_r_fire, UVM_DEFAULT)
      `uvm_field_int(axi_r_id, UVM_DEFAULT)
      `uvm_field_int(axi_r_last, UVM_DEFAULT)
      `uvm_field_int(axi_aw_fire, UVM_DEFAULT)
      `uvm_field_int(axi_aw_id, UVM_DEFAULT)
      `uvm_field_int(axi_aw_len, UVM_DEFAULT)
      `uvm_field_int(axi_w_fire, UVM_DEFAULT)
      `uvm_field_int(axi_w_last, UVM_DEFAULT)
      `uvm_field_int(axi_b_fire, UVM_DEFAULT)
      `uvm_field_int(axi_b_id, UVM_DEFAULT)
    `uvm_object_utils_end

    function new(string name = "cvxif_transaction");
      super.new(name);
    endfunction
  endclass

  class cvxif_monitor #(int unsigned Xlen = 64,
                        int unsigned TransIdW = 4) extends uvm_monitor;
    `uvm_component_param_utils(cvxif_monitor #(Xlen, TransIdW))

    virtual ara_cvxif_if #(Xlen, TransIdW) vif;
    uvm_analysis_port #(cvxif_transaction #(Xlen, TransIdW)) analysis_port;
    int unsigned cycle;
    int unsigned reset_epoch;
    int unsigned trace_limit;
    int unsigned trace_count;
    int unsigned backend_trace_count;
    int unsigned axi_write_trace_count;
    bit trace_axi_write;
    bit in_reset;
    bit [4:0] axi_stalled;
    logic [1023:0] axi_held_payload[5];
    int unsigned axi_stall_cycles[5];
    int unsigned axi_hold_checks[5];

    function new(string name, uvm_component parent);
      super.new(name, parent);
      analysis_port = new("analysis_port", this);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      if (!uvm_config_db#(virtual ara_cvxif_if #(Xlen, TransIdW))::get(
              this, "", "vif", vif)) begin
        `uvm_fatal("CVXIF/NOVIF", "CVXIF monitor virtual interface is not configured")
      end
      trace_limit = 0;
      trace_count = 0;
      backend_trace_count = 0;
      axi_write_trace_count = 0;
      trace_axi_write = $test$plusargs("ARA_UVM_TRACE_AXI_WRITE");
      void'($value$plusargs("ARA_UVM_TRACE_LIMIT=%d", trace_limit));
    endfunction

    task run_phase(uvm_phase phase);
      cvxif_transaction #(Xlen, TransIdW) item;
      bit [4:0] axi_valid;
      bit [4:0] axi_ready;
      logic [1023:0] axi_payload[5];
      string axi_channel;
      cycle = 0;
      reset_epoch = 0;
      in_reset = 0;
      axi_stalled = '0;
      for (int unsigned i = 0; i < 5; i++) begin
        axi_stall_cycles[i] = 0;
        axi_hold_checks[i] = 0;
      end
      forever begin
        @(vif.monitor_cb);
        cycle++;
        if (!vif.monitor_cb.rst_ni) begin
          axi_stalled = '0;
          if (!in_reset) begin
            reset_epoch++;
            `uvm_info("CVXIF/RESET", $sformatf(
                "cycle=%0d epoch=%0d", cycle, reset_epoch), UVM_NONE)
            item = cvxif_transaction#(Xlen, TransIdW)::type_id::create("reset");
            item.reset = 1'b1;
            item.cycle = cycle;
            item.reset_epoch = reset_epoch;
            analysis_port.write(item);
          end
          in_reset = 1'b1;
          continue;
        end
        in_reset = 1'b0;
        if ($isunknown({vif.monitor_cb.backend_alloc, vif.monitor_cb.backend_done}))
          `uvm_error("VID/X", "backend allocation/completion control is unknown")
        if (vif.monitor_cb.axi_enable &&
            $isunknown({vif.monitor_cb.axi_ar_valid, vif.monitor_cb.axi_ar_ready,
                        vif.monitor_cb.axi_r_valid, vif.monitor_cb.axi_r_ready,
                        vif.monitor_cb.axi_aw_valid, vif.monitor_cb.axi_aw_ready,
                        vif.monitor_cb.axi_w_valid, vif.monitor_cb.axi_w_ready,
                        vif.monitor_cb.axi_b_valid, vif.monitor_cb.axi_b_ready}))
          `uvm_error("AXI/X", "Ara AXI handshake control is unknown")
        axi_valid = {vif.monitor_cb.axi_b_valid, vif.monitor_cb.axi_w_valid,
                     vif.monitor_cb.axi_aw_valid, vif.monitor_cb.axi_r_valid,
                     vif.monitor_cb.axi_ar_valid};
        axi_ready = {vif.monitor_cb.axi_b_ready, vif.monitor_cb.axi_w_ready,
                     vif.monitor_cb.axi_aw_ready, vif.monitor_cb.axi_r_ready,
                     vif.monitor_cb.axi_ar_ready};
        axi_payload[0] = vif.monitor_cb.axi_ar_payload;
        axi_payload[1] = vif.monitor_cb.axi_r_payload;
        axi_payload[2] = vif.monitor_cb.axi_aw_payload;
        axi_payload[3] = vif.monitor_cb.axi_w_payload;
        axi_payload[4] = vif.monitor_cb.axi_b_payload;
        for (int unsigned i = 0; i < 5; i++) begin
          case (i)
            0: axi_channel = "AR";
            1: axi_channel = "R";
            2: axi_channel = "AW";
            3: axi_channel = "W";
            default: axi_channel = "B";
          endcase
          if (vif.monitor_cb.axi_enable && axi_stalled[i]) begin
            axi_hold_checks[i]++;
            if (!axi_valid[i] || axi_payload[i] !== axi_held_payload[i])
              `uvm_error("AXI/HOLD", $sformatf(
                  "%s payload or valid changed under backpressure at cycle %0d",
                  axi_channel, cycle))
          end
          axi_stalled[i] = vif.monitor_cb.axi_enable && axi_valid[i] && !axi_ready[i];
          if (axi_stalled[i]) begin
            axi_stall_cycles[i]++;
            axi_held_payload[i] = axi_payload[i];
          end
        end
        if ((vif.monitor_cb.req_valid && vif.monitor_cb.req_ready)
            || (vif.monitor_cb.resp_valid && vif.monitor_cb.resp_ready)
            || vif.monitor_cb.backend_alloc || (|vif.monitor_cb.backend_done)
            || (vif.monitor_cb.axi_enable &&
                ((vif.monitor_cb.axi_ar_valid && vif.monitor_cb.axi_ar_ready) ||
                 (vif.monitor_cb.axi_r_valid && vif.monitor_cb.axi_r_ready) ||
                 (vif.monitor_cb.axi_aw_valid && vif.monitor_cb.axi_aw_ready) ||
                 (vif.monitor_cb.axi_w_valid && vif.monitor_cb.axi_w_ready) ||
                 (vif.monitor_cb.axi_b_valid && vif.monitor_cb.axi_b_ready)))) begin
          item = cvxif_transaction#(Xlen, TransIdW)::type_id::create("cycle_sample");
          item.req_fire = vif.monitor_cb.req_valid && vif.monitor_cb.req_ready;
          item.resp_fire = vif.monitor_cb.resp_valid && vif.monitor_cb.resp_ready;
          item.cycle = cycle;
          item.reset_epoch = reset_epoch;
          item.req_trans_id = vif.monitor_cb.req_trans_id;
          item.resp_trans_id = vif.monitor_cb.resp_trans_id;
          item.insn = vif.monitor_cb.insn;
          item.rs1 = vif.monitor_cb.rs1;
          item.rs2 = vif.monitor_cb.rs2;
          item.result = vif.monitor_cb.result;
          item.exception_valid = vif.monitor_cb.exception_valid;
          item.backend_alloc = vif.monitor_cb.backend_alloc;
          item.backend_alloc_id = vif.monitor_cb.backend_alloc_id;
          item.backend_done = vif.monitor_cb.backend_done;
          item.axi_ar_fire = vif.monitor_cb.axi_enable &&
                             vif.monitor_cb.axi_ar_valid && vif.monitor_cb.axi_ar_ready;
          item.axi_r_fire = vif.monitor_cb.axi_enable &&
                            vif.monitor_cb.axi_r_valid && vif.monitor_cb.axi_r_ready;
          if (item.axi_ar_fire) begin
            if ($isunknown({vif.monitor_cb.axi_ar_id, vif.monitor_cb.axi_ar_len}))
              `uvm_error("AXI/AR_X", "accepted Ara AXI AR has unknown ID or length")
            item.axi_ar_id = vif.monitor_cb.axi_ar_id;
            item.axi_ar_len = vif.monitor_cb.axi_ar_len;
          end
          if (item.axi_r_fire) begin
            if ($isunknown({vif.monitor_cb.axi_r_id, vif.monitor_cb.axi_r_last}))
              `uvm_error("AXI/R_X", "accepted Ara AXI R has unknown ID or last")
            item.axi_r_id = vif.monitor_cb.axi_r_id;
            item.axi_r_last = vif.monitor_cb.axi_r_last;
          end
          item.axi_aw_fire = vif.monitor_cb.axi_enable &&
                             vif.monitor_cb.axi_aw_valid && vif.monitor_cb.axi_aw_ready;
          item.axi_w_fire = vif.monitor_cb.axi_enable &&
                            vif.monitor_cb.axi_w_valid && vif.monitor_cb.axi_w_ready;
          item.axi_b_fire = vif.monitor_cb.axi_enable &&
                            vif.monitor_cb.axi_b_valid && vif.monitor_cb.axi_b_ready;
          if (item.axi_aw_fire) begin
            if ($isunknown({vif.monitor_cb.axi_aw_id, vif.monitor_cb.axi_aw_len}))
              `uvm_error("AXI/AW_X", "accepted Ara AXI AW has unknown ID or length")
            item.axi_aw_id = vif.monitor_cb.axi_aw_id;
            item.axi_aw_len = vif.monitor_cb.axi_aw_len;
          end
          if (item.axi_w_fire) begin
            if ($isunknown(vif.monitor_cb.axi_w_last))
              `uvm_error("AXI/W_X", "accepted Ara AXI W has unknown last")
            item.axi_w_last = vif.monitor_cb.axi_w_last;
          end
          if (item.axi_b_fire) begin
            if ($isunknown(vif.monitor_cb.axi_b_id))
              `uvm_error("AXI/B_X", "accepted Ara AXI B has unknown ID")
            item.axi_b_id = vif.monitor_cb.axi_b_id;
          end
          analysis_port.write(item);
          if (trace_axi_write &&
              (item.axi_aw_fire || (item.axi_w_fire && item.axi_w_last) ||
               item.axi_b_fire) && axi_write_trace_count < trace_limit) begin
            axi_write_trace_count++;
            `uvm_info("AXI/WRITE_EVENT", $sformatf(
                "cycle=%0d aw=%0d aw_id=%0d aw_len=%0d w_last=%0d b=%0d b_id=%0d",
                item.cycle, item.axi_aw_fire, item.axi_aw_id, item.axi_aw_len,
                item.axi_w_fire && item.axi_w_last, item.axi_b_fire,
                item.axi_b_id), UVM_NONE)
          end
          if ((item.req_fire || item.resp_fire) && trace_count < trace_limit) begin
            trace_count++;
            `uvm_info("CVXIF/EVENT", $sformatf(
                "cycle=%0d req_fire=%0d req_id=%0d insn=%08h resp_fire=%0d resp_id=%0d exc=%0d",
                item.cycle, item.req_fire, item.req_trans_id, item.insn,
                item.resp_fire, item.resp_trans_id, item.exception_valid), UVM_NONE)
          end
          if ((item.backend_alloc || (|item.backend_done)) &&
              backend_trace_count < trace_limit) begin
            backend_trace_count++;
            `uvm_info("VID/EVENT", $sformatf(
                "cycle=%0d alloc=%0d alloc_id=%0d done=%02h",
                item.cycle, item.backend_alloc, item.backend_alloc_id,
                item.backend_done), UVM_NONE)
          end
        end
      end
    endtask

    function void check_phase(uvm_phase phase);
      `uvm_info("AXI/STALL_COUNT", $sformatf(
          "ar=%0d r=%0d aw=%0d w=%0d b=%0d hold_checks=%0d",
          axi_stall_cycles[0], axi_stall_cycles[1], axi_stall_cycles[2],
          axi_stall_cycles[3], axi_stall_cycles[4],
          axi_hold_checks[0] + axi_hold_checks[1] + axi_hold_checks[2] +
          axi_hold_checks[3] + axi_hold_checks[4]), UVM_LOW)
    endfunction
  endclass

  class cvxif_scoreboard #(int unsigned Xlen = 64,
                           int unsigned TransIdW = 4) extends uvm_scoreboard;
    `uvm_component_param_utils(cvxif_scoreboard #(Xlen, TransIdW))

    typedef struct packed {
      bit [7:0] id;
      bit [7:0] len;
    } axi_aw_item_t;

    uvm_analysis_imp #(cvxif_transaction #(Xlen, TransIdW),
                       cvxif_scoreboard #(Xlen, TransIdW)) analysis_export;
    bit outstanding [int unsigned];
    int unsigned request_count;
    int unsigned response_count;
    int unsigned aborted_count;
    int unsigned same_cycle_reuse_count;
    int unsigned immediate_response_count;
    bit backend_live [int unsigned];
    int unsigned backend_alloc_count;
    int unsigned backend_done_count;
    int unsigned backend_aborted_count;
    int unsigned backend_max_live;
    int unsigned axi_read_beats[256][$];
    int unsigned axi_ar_count;
    int unsigned axi_r_count;
    int unsigned axi_completed_count;
    int unsigned axi_aborted_count;
    int unsigned axi_max_pending;
    int unsigned axi_pending_count;
    axi_aw_item_t axi_aw_queue[$];
    int unsigned axi_w_completed[$];
    int unsigned axi_w_open_beats;
    int unsigned axi_b_pending[256];
    int unsigned axi_aw_count;
    int unsigned axi_w_beat_count;
    int unsigned axi_w_burst_count;
    int unsigned axi_w_matched_count;
    int unsigned axi_b_count;
    int unsigned axi_write_aborted_count;
    int unsigned axi_write_pending_count;
    int unsigned axi_write_max_pending;

    function new(string name, uvm_component parent);
      super.new(name, parent);
      analysis_export = new("analysis_export", this);
      request_count = 0;
      response_count = 0;
      aborted_count = 0;
      same_cycle_reuse_count = 0;
      immediate_response_count = 0;
      for (int unsigned id = 0; id < 256; id++)
        axi_b_pending[id] = 0;
    endfunction

    function void write(cvxif_transaction #(Xlen, TransIdW) item);
      bit immediate;
      bit old_response;
      int unsigned remaining;
      int unsigned w_beats;
      axi_aw_item_t aw;
      if (item.reset) begin
        aborted_count += outstanding.num();
        outstanding.delete();
        backend_aborted_count += backend_live.num();
        backend_live.delete();
        for (int unsigned id = 0; id < 256; id++)
          axi_read_beats[id].delete();
        axi_aborted_count += axi_pending_count;
        axi_pending_count = 0;
        axi_write_aborted_count += axi_write_pending_count;
        axi_write_pending_count = 0;
        axi_aw_queue.delete();
        axi_w_completed.delete();
        axi_w_open_beats = 0;
        for (int unsigned id = 0; id < 256; id++)
          axi_b_pending[id] = 0;
        return;
      end
      // AXI permits multiple ordered reads with the same ID and an AR/R
      // handshake in one cycle. Enqueue AR before consuming R.
      if (item.axi_ar_fire) begin
        axi_read_beats[item.axi_ar_id].push_back(int'(item.axi_ar_len) + 1);
        axi_ar_count++;
        axi_pending_count++;
        if (axi_pending_count > axi_max_pending)
          axi_max_pending = axi_pending_count;
      end
      if (item.axi_r_fire) begin
        axi_r_count++;
        if (axi_read_beats[item.axi_r_id].size() == 0) begin
          `uvm_error("AXI/ORPHAN_R", $sformatf(
              "read beat for ID %0d has no AR at cycle %0d", item.axi_r_id, item.cycle))
        end else begin
          remaining = axi_read_beats[item.axi_r_id][0];
          if (item.axi_r_last !== (remaining == 1))
            `uvm_error("AXI/RLAST", $sformatf(
                "ID %0d last=%0b with %0d beats remaining at cycle %0d",
                item.axi_r_id, item.axi_r_last, remaining, item.cycle))
          if (remaining == 1) begin
            void'(axi_read_beats[item.axi_r_id].pop_front());
            axi_pending_count--;
            axi_completed_count++;
          end else begin
            axi_read_beats[item.axi_r_id][0] = remaining - 1;
          end
        end
      end
      // AXI4 W has no ID and may lead AW. Complete W bursts are paired with
      // accepted AWs in address order before their B responses are eligible.
      if (item.axi_aw_fire) begin
        aw.id = item.axi_aw_id;
        aw.len = item.axi_aw_len;
        axi_aw_queue.push_back(aw);
        axi_aw_count++;
        axi_write_pending_count++;
        if (axi_write_pending_count > axi_write_max_pending)
          axi_write_max_pending = axi_write_pending_count;
      end
      if (item.axi_w_fire) begin
        axi_w_beat_count++;
        axi_w_open_beats++;
        if (item.axi_w_last) begin
          axi_w_completed.push_back(axi_w_open_beats);
          axi_w_burst_count++;
          axi_w_open_beats = 0;
        end
      end
      while (axi_aw_queue.size() != 0 && axi_w_completed.size() != 0) begin
        aw = axi_aw_queue.pop_front();
        w_beats = axi_w_completed.pop_front();
        if (w_beats != int'(aw.len) + 1)
          `uvm_error("AXI/WLAST", $sformatf(
              "AW ID %0d expected %0d W beats, observed %0d at cycle %0d",
              aw.id, int'(aw.len) + 1, w_beats, item.cycle))
        axi_b_pending[aw.id]++;
        axi_w_matched_count++;
      end
      if (item.axi_b_fire) begin
        axi_b_count++;
        if (axi_b_pending[item.axi_b_id] == 0)
          `uvm_error("AXI/ORPHAN_B", $sformatf(
              "write response ID %0d has no completed AW/W at cycle %0d",
              item.axi_b_id, item.cycle))
        else begin
          axi_b_pending[item.axi_b_id]--;
          axi_write_pending_count--;
        end
      end
      for (int unsigned id = 0; id < 8; id++) begin
        if (item.backend_done[id]) begin
          backend_done_count++;
          if (!backend_live.exists(id))
            `uvm_error("VID/ORPHAN_DONE", $sformatf(
                "completion for unallocated backend vid %0d at cycle %0d", id, item.cycle))
          else
            backend_live.delete(id);
        end
      end
      if (item.backend_alloc) begin
        backend_alloc_count++;
        if (backend_live.exists(item.backend_alloc_id))
          `uvm_error("VID/DUP_ALLOC", $sformatf(
              "backend vid %0d reused before completion at cycle %0d",
              item.backend_alloc_id, item.cycle))
        else
          backend_live[item.backend_alloc_id] = 1'b1;
        if (backend_live.num() > backend_max_live)
          backend_max_live = backend_live.num();
      end
      immediate = item.req_fire && item.resp_fire
                  && item.req_trans_id == item.resp_trans_id
                  && !outstanding.exists(item.resp_trans_id);
      old_response = item.resp_fire && outstanding.exists(item.resp_trans_id);
      if (item.resp_fire) begin
        response_count++;
        if (old_response) begin
          outstanding.delete(item.resp_trans_id);
        end else if (!immediate) begin
          `uvm_error("CVXIF/ORPHAN_RESP", $sformatf(
              "response has no outstanding request ID %0d at cycle %0d",
              item.resp_trans_id, item.cycle))
        end
      end
      if (item.req_fire) begin
        request_count++;
        if (outstanding.exists(item.req_trans_id)) begin
          `uvm_error("CVXIF/DUP_ID", $sformatf(
              "request reuses outstanding transaction ID %0d at cycle %0d",
              item.req_trans_id, item.cycle))
        end else if (!immediate) begin
          outstanding[item.req_trans_id] = 1'b1;
        end
        if (old_response && item.req_trans_id == item.resp_trans_id)
          same_cycle_reuse_count++;
        if (immediate)
          immediate_response_count++;
      end
    endfunction

    function void check_phase(uvm_phase phase);
      `uvm_info("CVXIF/COUNT", $sformatf(
          "observed requests=%0d responses=%0d aborted=%0d reused=%0d immediate=%0d",
          request_count, response_count, aborted_count,
          same_cycle_reuse_count, immediate_response_count), UVM_LOW)
      `uvm_info("VID/COUNT", $sformatf(
          "allocations=%0d completions=%0d aborted=%0d max_live=%0d",
          backend_alloc_count, backend_done_count,
          backend_aborted_count, backend_max_live), UVM_LOW)
      `uvm_info("AXI/READ_COUNT", $sformatf(
          "ar=%0d r_beats=%0d completed=%0d aborted=%0d pending=%0d max_pending=%0d",
          axi_ar_count, axi_r_count, axi_completed_count, axi_aborted_count,
          axi_pending_count, axi_max_pending), UVM_LOW)
      `uvm_info("AXI/WRITE_COUNT", $sformatf(
          "aw=%0d w_beats=%0d w_bursts=%0d matched=%0d b=%0d aborted=%0d pending=%0d max_pending=%0d",
          axi_aw_count, axi_w_beat_count, axi_w_burst_count,
          axi_w_matched_count, axi_b_count, axi_write_aborted_count,
          axi_write_pending_count, axi_write_max_pending), UVM_LOW)
      if (request_count == 0 || response_count == 0)
        `uvm_error("CVXIF/NO_TRAFFIC", "scoreboard observed no complete CVXIF traffic")
      if (request_count != response_count + aborted_count)
        `uvm_error("CVXIF/COUNT_MISMATCH", $sformatf(
            "request/response/aborted count mismatch: %0d/%0d/%0d",
            request_count, response_count, aborted_count))
      if (outstanding.num() != 0) begin
        `uvm_error("CVXIF/UNRETURNED", $sformatf(
            "%0d transaction IDs remain outstanding at end of test", outstanding.num()))
      end
      if (backend_live.num() != 0 ||
          backend_alloc_count != backend_done_count + backend_aborted_count)
        `uvm_error("VID/COUNT_MISMATCH", $sformatf(
            "backend allocation/completion accounting differs: %0d/%0d/%0d live=%0d",
            backend_alloc_count, backend_done_count,
            backend_aborted_count, backend_live.num()))
      if (axi_pending_count != 0)
        `uvm_error("AXI/UNRETURNED", $sformatf(
            "%0d Ara AXI read bursts remain outstanding", axi_pending_count))
      if (axi_ar_count != axi_completed_count + axi_aborted_count + axi_pending_count)
        `uvm_error("AXI/COUNT_MISMATCH", $sformatf(
            "read burst accounting differs: ar=%0d complete=%0d abort=%0d pending=%0d",
            axi_ar_count, axi_completed_count, axi_aborted_count, axi_pending_count))
      if (axi_write_pending_count != 0 || axi_aw_queue.size() != 0 ||
          axi_w_completed.size() != 0 || axi_w_open_beats != 0)
        `uvm_error("AXI/WRITE_UNRETURNED", $sformatf(
            "write pending=%0d AW queue=%0d W burst queue=%0d partial W=%0d",
            axi_write_pending_count, axi_aw_queue.size(),
            axi_w_completed.size(), axi_w_open_beats))
      if (axi_aw_count != axi_b_count + axi_write_aborted_count + axi_write_pending_count)
        `uvm_error("AXI/WRITE_COUNT_MISMATCH", $sformatf(
            "AW/B/reset accounting differs: aw=%0d b=%0d abort=%0d pending=%0d",
            axi_aw_count, axi_b_count, axi_write_aborted_count,
            axi_write_pending_count))
    endfunction
  endclass

  class cvxif_agent #(int unsigned Xlen = 64,
                      int unsigned TransIdW = 4) extends uvm_agent;
    `uvm_component_param_utils(cvxif_agent #(Xlen, TransIdW))
    cvxif_monitor #(Xlen, TransIdW) monitor;

    function new(string name, uvm_component parent);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      monitor = cvxif_monitor#(Xlen, TransIdW)::type_id::create("monitor", this);
    endfunction
  endclass

  class cvxif_env #(int unsigned Xlen = 64,
                    int unsigned TransIdW = 4) extends uvm_env;
    `uvm_component_param_utils(cvxif_env #(Xlen, TransIdW))
    cvxif_agent #(Xlen, TransIdW) agent;
    cvxif_scoreboard #(Xlen, TransIdW) scoreboard;

    function new(string name, uvm_component parent);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      agent = cvxif_agent#(Xlen, TransIdW)::type_id::create("agent", this);
      scoreboard = cvxif_scoreboard#(Xlen, TransIdW)::type_id::create("scoreboard", this);
    endfunction

    function void connect_phase(uvm_phase phase);
      agent.monitor.analysis_port.connect(scoreboard.analysis_export);
    endfunction
  endclass

  class ara_cvxif_smoke_test extends uvm_test;
    `uvm_component_utils(ara_cvxif_smoke_test)
    cvxif_env #(64, 4) env;
    virtual ara_cvxif_if #(64, 4) vif;

    function new(string name, uvm_component parent);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      if (!uvm_config_db#(virtual ara_cvxif_if #(64, 4))::get(this, "", "vif", vif)) begin
        `uvm_fatal("CVXIF/TEST_NOVIF", "CVXIF smoke test virtual interface is not configured")
      end
      env = cvxif_env#(64, 4)::type_id::create("env", this);
    endfunction

    task run_phase(uvm_phase phase);
      phase.raise_objection(this, "wait for the directed CVXIF transaction smoke");
      @(posedge vif.clk_i iff vif.smoke_done);
      repeat (2) @(posedge vif.clk_i);
      phase.drop_objection(this, "directed CVXIF transaction smoke completed");
    endtask
  endclass

  class ara_cvxif_dut_test extends uvm_test;
    `uvm_component_utils(ara_cvxif_dut_test)
    cvxif_env #(64, 4) env;
    virtual ara_cvxif_if #(64, 4) vif;
    bit observed_pass;

    function new(string name, uvm_component parent);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      if (!uvm_config_db#(virtual ara_cvxif_if #(64, 4))::get(this, "", "vif", vif))
        `uvm_fatal("CVXIF/TEST_NOVIF", "real DUT CVXIF interface is not configured")
      env = cvxif_env#(64, 4)::type_id::create("env", this);
    endfunction

    task run_phase(uvm_phase phase);
      phase.raise_objection(this, "wait for the real Ara program to complete");
      @(posedge vif.clk_i iff vif.smoke_done);
      observed_pass = (vif.smoke_pass === 1'b1);
      repeat (2) @(posedge vif.clk_i);
      phase.drop_objection(this, "real Ara program completed");
    endtask

    function void check_phase(uvm_phase phase);
      if (!observed_pass)
        `uvm_error("CVXIF/DUT_FAIL", "real Ara program did not report success")
      if (env.scoreboard.backend_alloc_count == 0)
        `uvm_error("VID/NO_TRAFFIC", "real Ara program did not allocate a backend vid")
    endfunction
  endclass
endpackage
