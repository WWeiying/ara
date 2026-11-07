"""Retain compute goldens; add timing and separate mixed-pipeline fault probes."""
from audit import require


def fixture(source, clone):
    text=source;edits=[]
    def edit(old,new):
        nonlocal text
        require(text.count(old)==1,'Exact compute fixture anchor: '+old[:70])
        text=text.replace(old,new,1);edits.append(dict(before=old,after=new))
    edit('module qbs_wide_compute_tb #(parameter bit Wide = 0);',
         'module qbs_mixed_compute_tb #(parameter bit Wide = 0, parameter bit Mixed = 0);')
    if clone:
        edit("  qbs_compute_engine #(.WideWeightIngress(Wide),.WideMatrixDot(1'b1)) dut (",
             "  qbs_compute_engine_mixed #(.WideWeightIngress(Wide),.WideMatrixDot(1'b1),.MixedScaleIssue(Mixed)) dut (")
    edit('  bit checking=0,tracing=0,probe_enabled=0;', '''  bit checking=0,tracing=0,probe_enabled=0;
  longint unsigned tick=0, command_tick=0;
  int mixed_issues=0,mixed_returns=0,mixed_nx=0,multi_returns=0,union_nx=0,legacy_muls=0;
  always @(posedge clk) tick++;
''')
    if clone:
        anchor="        if(`FP.half_fire) fp_event(int'(`FP.half_index),2,0,0,int'(RNE),"
        edit(anchor,"""        if(`FP.mixed_fire) fp_event(int'(`FP.mixed_index),1,int'(MUL),0,int'(RNE),
          `FP.mixed_weight,`FP.entry_work_value_q[`FP.mixed_index],0);
"""+anchor)
        anchor='      owned_probe=Wide && probe_enabled && wvalid && wbank==0 && wrows==1 &&'
        edit(anchor,'''      if(`FP.mixed_fire) mixed_issues++;
      if(`FP.mixed_out_valid) begin
        mixed_returns++;
        mixed_nx+=`FP.mixed_flags[0];
        if(`FP.fp_out_valid || `FP.cast_out_valid || `FP.half_out_valid) multi_returns++;
        if(`FP.mixed_flags[0] && ((`FP.fp_out_valid && `FP.fp_status.NX) ||
            (`FP.cast_out_valid && `FP.cast_status.NX))) union_nx++;
      end
      if(`FP.fp_fire && `FP.fp_operation == MUL) legacy_muls++;
'''+anchor)
    else:
        anchor='      owned_probe=Wide && probe_enabled && wvalid && wbank==0 && wrows==1 &&'
        edit(anchor,'      if(`FP.fp_fire && `FP.fp_operation == MUL) legacy_muls++;\n'+anchor)
    edit('    wbytes=0;abytes=0;wbeats=0;stalls=0;overlap=0;result_wait=0;probe_edges=0;probe_bytes=0;',
         '''    wbytes=0;abytes=0;wbeats=0;stalls=0;overlap=0;result_wait=0;probe_edges=0;probe_bytes=0;
    mixed_issues=0;mixed_returns=0;mixed_nx=0;multi_returns=0;union_nx=0;legacy_muls=0;''')
    edit('    @(negedge clk);command_valid=0;tracing=trace_on;',
         '    @(negedge clk);command_valid=0;tracing=trace_on;command_tick=tick;')
    edit('    $display("WC_CONFIG version=1 wide=%0d weight_bits=%0d matrix=1",Wide,WB*8);',
         '    $display("WC_CONFIG version=1 wide=%0d weight_bits=%0d matrix=1",Wide,WB*8);\n'
         f'    $display("MC_CONFIG clone={int(clone)} mixed=%0d width=%0d",Mixed,WB*8);')
    anchor="    if(flags!==5'(expected_flags) || tiles!==32'(expected_c[0]) || weights!==32'(expected_c[1]) ||"
    edit(anchor,'''    $display("MC_TIME episode=%0d cycles=%0d mixed_issue=%0d mixed_return=%0d mixed_nx=%0d multi_return=%0d union_nx=%0d legacy_mul=%0d",
      id,tick-command_tick,mixed_issues,mixed_returns,mixed_nx,multi_returns,union_nx,legacy_muls);
'''+anchor)
    if clone:
        anchor='          4:reached=dut.i_profile_engine_int.correction_product_q[0].valid===1\'b1;'
        edit(anchor,anchor+'''
          5:reached=dut.i_fp_accumulator.mixed_fire===1'b1;
          6:reached=dut.i_fp_accumulator.mixed_out_valid===1'b1;''')
        edit('    fault=1;bound=0;', '''    if(kind>=5) begin
      if(!Mixed || !dut.fp_busy) $fatal(1,"MC_FAULT_NOT_IN_MIXED_LIFETIME");
      $display("MC_FAULT_TRIGGER kind=%0d issue=%0d response=%0d mixed_busy=%0d entries=%0d",
        kind,dut.i_fp_accumulator.mixed_fire,dut.i_fp_accumulator.mixed_out_valid,
        dut.i_fp_accumulator.mixed_busy,$countones(dut.i_fp_accumulator.entry_valid_q));
    end
    fault=1;bound=0;''')
        anchor='    for(int ordinal=0;ordinal<cases;ordinal++) begin'
        edit(anchor,'''    if($test$plusargs("MC_FAULT_ONLY")) begin
      if(!Mixed) $fatal(1,"Mixed fault worker requires enabled candidate");
      read_case(fd,0);
      for(int kind=5;kind<=6;kind++) fault_case(kind);
      if(normal_count!=0 || recovery_count!=2 || fault_count!=2)
        $fatal(1,"MC_FAULT_COVERAGE");
      $display("MC_FAULT_PASS recovery=2 faults=2 drain_before_clear=1");
      $fclose(fd);$finish;
    end
'''+anchor)
    restored=text
    for e in reversed(edits):
        require(restored.count(e['after'])==1,'Nonreversible compute fixture edit')
        restored=restored.replace(e['after'],e['before'],1)
    require(restored==source,'Original compute fixture must restore exactly')
    return text,dict(edits=edits,source_reversible=True,original_goldens_checks_retained=True,
                     mixed_only_faults_separate=True,component_cycles_not_model_cycles=True)
