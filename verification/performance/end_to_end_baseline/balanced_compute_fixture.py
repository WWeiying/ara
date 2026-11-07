"""Balanced compute observations without weakening the inherited C goldens."""
from balanced_compute_source import patch
from mixed_compute_fixture import fixture as mixed_fixture


def fixture(source, clone):
    intermediate,parent=mixed_fixture(source,clone)
    name='qbs_balanced_compute_tb'
    changes=[('qbs_mixed_compute_tb',name),
        ('parameter bit Mixed = 0','parameter bit Balanced = 0')]
    # The module identifier occurs only once; Mixed is a parameter reference,
    # whereas MIXED in diagnostics/plusargs names is intentionally retained.
    text,edits=patch(intermediate,changes)
    import re
    text=re.sub(r'\bMixed\b','Balanced',text)
    if clone:
        text,extra=patch(text,[
            ('qbs_compute_engine_mixed','qbs_compute_engine_balanced'),
            ('.MixedScaleIssue(Balanced)','.BalancedMatrixDot(Balanced)'),
            ('          6:reached=dut.i_fp_accumulator.mixed_out_valid===1\'b1;',
             '''          6:reached=dut.i_fp_accumulator.mixed_out_valid===1'b1;
          7:reached=$bits(dut.i_profile_engine_int.correction_valid)==8 &&
            dut.i_profile_engine_int.correction_product_q[$bits(dut.i_profile_engine_int.correction_valid)-1].valid===1'b1;'''),
            ('    if(kind>=5) begin','    if(kind==5 || kind==6) begin'),
            ('    fault=1;bound=0;', '''    if(kind==7) begin
      if(!Balanced || !dut.integer_busy) $fatal(1,"BC_FAULT_NOT_IN_LAST_CORRECTION");
      $display("BC_FAULT_TRIGGER kind=7 last_correction=%0d lanes=%0d integer_busy=%0d",
        dut.i_profile_engine_int.correction_product_q[$bits(dut.i_profile_engine_int.correction_valid)-1].valid,
        $bits(dut.i_profile_engine_int.correction_valid),dut.integer_busy);
    end
    fault=1;bound=0;'''),
            ('      read_case(fd,0);\n      for(int kind=5;kind<=6;kind++) fault_case(kind);',
             '      read_case(fd,0);read_case(fd,1);\n      for(int kind=5;kind<=7;kind++) fault_case(kind);'),
            ('normal_count!=0 || recovery_count!=2 || fault_count!=2',
             'normal_count!=0 || recovery_count!=3 || fault_count!=3'),
            ('MC_FAULT_PASS recovery=2 faults=2 drain_before_clear=1',
             'MC_FAULT_PASS recovery=3 faults=3 drain_before_clear=1'),
        ]);edits.extend(extra)
    observations='''  int bc_dots=0,bc_corrections=0,bc_last=0;
  int bc_fp_input=0,bc_fp_slot=0,bc_fp_acc=0,bc_corr_pending=0,bc_fp_no_uop=0;
'''
    collect='''      if(dut.i_profile_engine_int.s0_valid_q) bc_dots++;
      bc_corrections+=$countones(dut.i_profile_engine_int.correction_valid);
      if(Balanced && $bits(dut.i_profile_engine_int.correction_valid)==8 &&
          dut.i_profile_engine_int.correction_valid[$bits(dut.i_profile_engine_int.correction_valid)-1]) bc_last++;
      if(dut.integer_result_valid && !dut.fp_request_ready) begin
        bc_fp_input++;
        if(`FP.entry_valid_q[dut.integer_result_stream]) bc_fp_slot++;
        else if(`FP.request_accumulator_conflict) bc_fp_acc++;
      end
      if(|dut.i_profile_engine_int.slot_valid_q[0] || |dut.i_profile_engine_int.slot_valid_q[1]) bc_corr_pending++;
      if(`FP.entry_occupancy!=0 && !`FP.fp_in_valid && !`FP.cast_found && !`FP.half_found'''
    collect+=(' && !`FP.mixed_found' if clone else '')+') bc_fp_no_uop++;\n'
    text,extra=patch(text,[
        ('  int mixed_issues=0,mixed_returns=0,mixed_nx=0,multi_returns=0,union_nx=0,legacy_muls=0;',
         '  int mixed_issues=0,mixed_returns=0,mixed_nx=0,multi_returns=0,union_nx=0,legacy_muls=0;\n'+observations),
        ('      owned_probe=Wide && probe_enabled && wvalid && wbank==0 && wrows==1 &&',
         collect+'      owned_probe=Wide && probe_enabled && wvalid && wbank==0 && wrows==1 &&'),
        ('    mixed_issues=0;mixed_returns=0;mixed_nx=0;multi_returns=0;union_nx=0;legacy_muls=0;',
         '    mixed_issues=0;mixed_returns=0;mixed_nx=0;multi_returns=0;union_nx=0;legacy_muls=0;\n'
         '    bc_dots=0;bc_corrections=0;bc_last=0;bc_fp_input=0;bc_fp_slot=0;bc_fp_acc=0;bc_corr_pending=0;bc_fp_no_uop=0;'),
        ('    $display("MC_TIME episode=',
         '''    $display("BC_PHYSICAL episode=%0d dot_issues=%0d corrections=%0d last_correction=%0d fp_input_blocked=%0d fp_slot_blocked=%0d fp_acc_blocked=%0d correction_pending=%0d fp_no_uop=%0d",
      id,bc_dots,bc_corrections,bc_last,bc_fp_input,bc_fp_slot,bc_fp_acc,bc_corr_pending,bc_fp_no_uop);
    $display("MC_TIME episode='''),
    ]);edits.extend(extra)
    return text,dict(parent=parent,edits=edits,original_goldens_checks_retained=True,
        additional_fault_case=1,additional_faults=[5,6,7],component_observations_only=True,
        no_original_testbench_or_checker_modified=True)
