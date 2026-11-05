# Read-only structural audit of a completed mapped ADDMUL design.
source $::env(FMA_INPUT)/library_env.tcl
set_app_var target_library $STD_LIBRARY_LIST(BWP12T,tc)
set_app_var synthetic_library dw_foundation.sldb
set_app_var link_library "* $target_library $synthetic_library"
read_ddc $::env(FMA_INPUT)/mapped.ddc
current_design shared_fma_timing
if {![link]} {exit 1}

proc dump_cells {path cells} {
  set f [open $path w]
  puts $f "name\tref\tarea_um2\tsequential"
  foreach_in_collection c [filter_collection $cells {is_hierarchical == false}] {
    set ref [get_attribute $c ref_name]
    if {$ref eq {**logic_0**} || $ref eq {**logic_1**}} {
      set area 0
    } else {
      set area [get_attribute $c area]
      if {$area eq ""} {error "Missing area on [get_object_name $c]"}
    }
    puts $f "[get_object_name $c]\t$ref\t$area\t[get_attribute $c is_sequential]"
  }
  close $f
}
dump_cells cells.tsv [get_cells -hierarchical *]
redirect resources_mapped.rpt {report_resources -hierarchy}
redirect area.rpt {report_area -hierarchy}
redirect combo_max.tim {report_timing -group COMBO -max_paths 10 -significant_digits 6 -input_pins -nets}
redirect hold_min.tim {report_timing -delay_type min -max_paths 10 -significant_digits 6}

set allnets [get_nets -hierarchical *]
set nf [open nets.txt w]
foreach_in_collection n $allnets {puts $nf [get_object_name $n]}
close $nf
set manifest [open cones.tsv w]
puts $manifest "lane\tboundary\tnets\tdriver_pins\tfile"
foreach lane {0 1 2 3} {
  set prefix [format {i_addmul/gen_lane[%d].i_fma/} $lane]
  foreach boundary {mantissa_a mantissa_b product addend_shifted product_shifted sum_raw sum_shifted final_mantissa} {
    set selected [get_nets -quiet __not_a_net__]
    foreach_in_collection n $allnets {
      set name [get_object_name $n]
      if {[string first $prefix $name] != 0} {continue}
      set tail [string range $name [string length $prefix] end]
      set base [lindex [split $tail {[}] 0]
      if {$base eq $boundary} {set selected [add_to_collection $selected $n]}
    }
    set drivers [get_pins -quiet -of_objects $selected -filter {direction == out}]
    set filename "lane${lane}_${boundary}.tsv"
    puts $manifest "$lane\t$boundary\t[sizeof_collection $selected]\t[sizeof_collection $drivers]\t$filename"
    if {[sizeof_collection $drivers] > 0} {
      # Stop at sequential boundaries; do not use -startpoints_only or cross registers.
      dump_cells $filename [all_fanin -to $drivers -flat -only_cells]
    }
  }
  set sumregs [get_cells -quiet __not_a_cell__]
  foreach_in_collection c [get_cells -hierarchical -filter {full_name =~ */mid_pipe_sum_q_reg*}] {
    if {[string first $prefix [get_object_name $c]] == 0} {
      set sumregs [add_to_collection $sumregs $c]
    }
  }
  set dpins [get_pins -quiet -of_objects $sumregs -filter {direction == in && full_name =~ */D}]
  set filename "lane${lane}_mid_sum_input.tsv"
  puts $manifest "$lane\tmid_sum_input\t0\t[sizeof_collection $dpins]\t$filename"
  if {[sizeof_collection $dpins] > 0} {
    dump_cells $filename [all_fanin -to $dpins -flat -only_cells]
  }
}
close $manifest
puts "FMA_STRUCTURE_REPORT_COMPLETE"
exit
