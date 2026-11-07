"""Successor of the accepted complete AXI/controller fixture, not its checker."""
from audit import require
from balanced_compute_source import patch
from run_wide_complete_engine import bench_source, wrapper_source


def wrapper(source, clone):
    text=wrapper_source(source)
    changes=[("    parameter bit WideMatrixDot = 1'b0,",
              "    parameter bit WideMatrixDot = 1'b0,\n    parameter bit BalancedMatrixDot = 1'b0,")]
    if clone:
        changes.extend([('  qbs_engine #(\n','  qbs_engine_balanced #(\n'),
                        ('.WideWeightIngress(WideWeight),',
                         '.WideWeightIngress(WideWeight), .BalancedMatrixDot(BalancedMatrixDot),')])
    text,edits=patch(text,changes)
    return text,dict(clone=bool(clone),edits=edits,original_reader_and_ownership_unchanged=True,
                     original_seed_interface_unchanged=True,physical_width=256)


def bench(source, clone):
    text=bench_source(source)
    mode='dut.i_engine.BalancedMatrixDot' if clone else '0'
    compute='dut.i_engine.i_compute_engine.BalancedMatrixDot' if clone else '0'
    changes=[('parameter int BusWidth = 128);',
              'parameter int BusWidth = 128, parameter bit Balanced = 0);'),
        ('    .WideMatrixDot(Wide),',
         '    .WideMatrixDot(Wide), .BalancedMatrixDot(Balanced),'),
        ('  initial $display("WIDE_ENGINE_CONFIG bits=%0d matrix=%0d", BusWidth, Wide);',
         '  initial $display("WIDE_ENGINE_CONFIG bits=%0d matrix=%0d", BusWidth, Wide);\n'
         f'  initial $display("BE_CONFIG clone={int(clone)} balanced=%0d controller=%0d compute=%0d bits=%0d matrix=%0d", Balanced,{mode},{compute},BusWidth,Wide);'),
        ('  integer fp_probe_fd = 0;', '  integer be_mixed=0,be_nx=0;\n  integer fp_probe_fd = 0;'),
        ('      fp_probe_blocked = 0;', '      be_mixed=0;be_nx=0;\n      fp_probe_blocked = 0;'),
        ('      $display("QBS engine PASS: %0d functional cases", case_count);',
         '      $display("WIDE_ENGINE_BUS bits=%0d narrow=%0d wide=%0d upper=%0d",\n'
         '               BusWidth,narrow_bus_count,wide_bus_count,upper_bus_count);\n'
         '      $display("QBS engine PASS: %0d functional cases", case_count);'),
    ]
    if clone:
        changes.extend([
            ("      fp_probe_issue += int'(`FP_PROBE.fp_fire) + int'(`FP_PROBE.cast_fire) + int'(`FP_PROBE.half_fire);",
             "      fp_probe_issue += int'(`FP_PROBE.fp_fire) + int'(`FP_PROBE.cast_fire) + int'(`FP_PROBE.half_fire) + int'(`FP_PROBE.mixed_fire);\n"
             '      if(`FP_PROBE.mixed_fire) be_mixed++;\n'
             '      if(`FP_PROBE.mixed_out_valid && `FP_PROBE.mixed_flags[0]) be_nx++;'),
            ('          !`FP_PROBE.half_found)', '          !`FP_PROBE.half_found && !`FP_PROBE.mixed_found)'),
        ])
    # Print the actual direct-command counters before any context or retry
    # changes them. All original golden/atomic/context assertions remain.
    anchor='      $display("WIDE_ENGINE_TRAFFIC case='
    report='''      $display("BE_WORK case=%0d tiles=%0d weights=%0d activation=%0d pairs=%0d capacity=%0d dot=%0d uops=%0d updates=%0d flags=%0d words=%0d mixed=%0d nx=%0d",
        case_id,tiles_computed,weight_bytes,activation_bytes,useful_pairs,pair_capacity,
        dot_active_cycles,fp_uop_issue,accumulator_updates,result_fflags,commit_word_count,be_mixed,be_nx);
      $display("BE_PHASE case=%0d cycles=%0d setup=%0d activation=%0d weight=%0d compute=%0d overlap=%0d drain=%0d scheduler=%0d commit=%0d fault=%0d terminal=%0d",
        case_id,command_cycles,phase_setup_cycles,phase_activation_cycles,phase_weight_cycles,
        phase_compute_cycles,phase_overlap_cycles,phase_drain_cycles,phase_scheduler_cycles,
        phase_commit_cycles,phase_fault_cycles,phase_terminal_cycles);
'''
    changes.append((anchor,report+anchor))
    text,edits=patch(text,changes)
    require(text.count('BE_WORK case=')==text.count('BE_PHASE case=')==1,'One direct observation per command')
    return text,dict(edits=edits,golden_fault_and_context_checks_retained=True,
                     direct_phase_and_work_observations=True,mixed_probe_accounting_updated=bool(clone),
                     source_parent='Accepted complete-AXI fixture transform; no sealed inputs modified')
