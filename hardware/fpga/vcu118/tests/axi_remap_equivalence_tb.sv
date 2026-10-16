module remap_case #(parameter int N = 16, T = 32)(output bit done = 0);
  localparam int I = (N > 1) ? $clog2(N) : 1;
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  logic push = 0, pop = 0;
  logic [8:0] input_id = 0, query_id = 0;
  logic [I-1:0] push_id = 0, pop_id = 0;
  wire [N-1:0] free_new, free_old;
  wire [I-1:0] free_id_new, free_id_old, match_id_new, match_id_old;
  wire full_new, full_old, exists_new, exists_old, limit_new, limit_old;
  wire [8:0] popped_new, popped_old;
  int count[N];
  int simultaneous = 0;
  axi_id_remap_table #(.InpIdWidth(9), .MaxUniqInpIds(N), .MaxTxnsPerId(T)) candidate (
    .clk_i(clk), .rst_ni(rst_n), .free_o(free_new), .free_oup_id_o(free_id_new),
    .full_o(full_new), .push_i(push), .push_inp_id_i(input_id), .push_oup_id_i(push_id),
    .exists_inp_id_i(query_id), .exists_o(exists_new), .exists_oup_id_o(match_id_new),
    .exists_full_o(limit_new), .pop_i(pop), .pop_oup_id_i(pop_id), .pop_inp_id_o(popped_new)
  );
  axi_id_remap_table_reference #(.InpIdWidth(9), .MaxUniqInpIds(N), .MaxTxnsPerId(T)) reference_i (
    .clk_i(clk), .rst_ni(rst_n), .free_o(free_old), .free_oup_id_o(free_id_old),
    .full_o(full_old), .push_i(push), .push_inp_id_i(input_id), .push_oup_id_i(push_id),
    .exists_inp_id_i(query_id), .exists_o(exists_old), .exists_oup_id_o(match_id_old),
    .exists_full_o(limit_old), .pop_i(pop), .pop_oup_id_i(pop_id), .pop_inp_id_o(popped_old)
  );
  task automatic compare();
    if (candidate.table_q !== reference_i.table_q || candidate.table_d !== reference_i.table_d ||
        {free_new, free_id_new, match_id_new, full_new, exists_new, limit_new, popped_new} !==
        {free_old, free_id_old, match_id_old, full_old, exists_old, limit_old, popped_old})
      $fatal(1, "Remap mismatch N=%0d T=%0d push=%b pop=%b push_id=%0d pop_id=%0d", N,T,push,pop,push_id,pop_id);
  endtask
  task automatic cycle(int a, int b, bit add, bit sub, int query);
    @(negedge clk);
    push_id = I'(a); pop_id = I'(b);
    input_id = 9'(a + 256); query_id = 9'(query);
    push = add; pop = sub;
    #1; compare();
    @(posedge clk);
    if (push) count[a]++;
    if (pop) count[b]--;
    if (push && pop && a == b) simultaneous++;
    #1; compare();
  endtask
  initial begin
    int a, b;
    foreach (count[i]) count[i] = 0;
    repeat (3) @(negedge clk); rst_n = 1;
    // Fill every entry to its limit, query it, then drain it completely.
    for (int i = 0; i < N; i++)
      for (int t = 0; t < T; t++) cycle(i, i, 1, 0, i + 256);
    for (int i = 0; i < N; i++)
      for (int t = 0; t < T; t++) cycle(i, i, 0, 1, i + 256);
    for (int c = 0; c < 10000; c++) begin
      a = $urandom_range(N-1, 0);
      b = (c % 3 == 0) ? a : $urandom_range(N-1, 0);
      cycle(a, b, count[a] < T && c % 7 != 0,
            count[b] > 0 && c % 5 != 0, c % 2 ? a + 256 : a);
    end
    if (T > 1 && simultaneous == 0) $fatal(1, "Missing same-entry push/pop coverage");
    @(negedge clk); rst_n = 0; push = 0; pop = 0;
    #1; compare();
    $display("PASS remap equivalence N=%0d T=%0d simultaneous=%0d", N, T, simultaneous);
    done = 1;
  end
endmodule

module tb;
  wire [4:0] done;
  remap_case #(.N(1), .T(1)) c0(done[0]);
  remap_case #(.N(3), .T(24)) c1(done[1]);
  remap_case #(.N(8), .T(24)) c2(done[2]);
  remap_case #(.N(16), .T(32)) c3(done[3]);
  remap_case #(.N(5), .T(3)) c4(done[4]);
  initial begin wait (&done); $display("PASS: remap cycle equivalence"); $finish; end
  initial begin #200000; $fatal(1, "Equivalence watchdog"); end
endmodule
