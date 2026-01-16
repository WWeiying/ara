################
## This proc takes up the "report_timing -options" as an arguments and can highlight datapath (by default) and launch_clock_path and capture_clock_path in GUI.
################

proc hilitePath_1 {args} {

  set launch_clock_path 0
  set capture_clock_path 0
  
  set results(-help) "none"
  set results(-report_timing_args) "none"
  set results(-deselectAll) "none"
  set results(-launch_clock_path) "none"
  set results(-capture_clock_path) "none"
  
  parse_proc_arguments -args $args results
  
  if {$results(-help)==""} {
    help -verbose hilitePath_1
    return 1
  }
  
  if {$results(-deselectAll)!="none"} {deselectAll}
  if {$results(-launch_clock_path)!="none"} {set launch_clock_path 1}
  if {$results(-capture_clock_path)!="none"} {set capture_clock_path 1}
  if {$results(-report_timing_args)!="none"} {
    set report_timing_args $results(-report_timing_args)
    if {![regexp full_clock $report_timing_args]} {set timing_path [eval "$report_timing_args -collection -path_type full_clock"]} else {
    set timing_path [eval "$report_timing_args -collection"]}
    } else {
    set timing_path [eval "report_timing -collection -path_type full_clock"]
  }
  
  foreach_in_collection path $timing_path {
    if {$launch_clock_path} {set path [get_property $path launch_clock_path]}
    if {$capture_clock_path} {set path [get_property $path capture_clock_path]}
    set t_points [get_property $path timing_points]
      foreach_in_collection point $t_points {
      set pin [get_object_name [get_property $point pin]]
      selectPin $pin
      if {[catch {dbIsTermFTerm $pin}]} {
        catch {selectInst [dbTermInstName [dbGetTermByInstTermName $pin]]}
        #puts [dbTermInstName [dbGetTermByInstTermName $pin]]
      }
      puts $pin
    }
  }
}



define_proc_arguments hilitePath_1 \
  -info "Highlight the combinational logic between startpoint and endpoint" \
  -define_args {\
  {-report_timing_args "Specifies the arguments of the report_timing" "string" string optional}
  {-deselectAll "deselects all previously selected objects" "" boolean optional}
  {-launch_clock_path "Highlights the launch clock path" "" boolean optional}
  {-capture_clock_path "Highlights the capture clock path" "" boolean optional}
  }

#####
