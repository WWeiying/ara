# Pulse the VIO-controlled CPU reset without changing boot-mode probes.
set vios [get_hw_vios -quiet]
if {[llength $vios] != 1} {
  error "expected one connected VIO, found [llength $vios]"
}
set vio [lindex $vios 0]
set reset_probe [get_hw_probes -quiet probe_out0 -of_objects $vio]
if {[llength $reset_probe] != 1} {
  error "expected VIO probe_out0, found [llength $reset_probe]"
}
set_property OUTPUT_VALUE 1 $reset_probe
commit_hw_vio $vio
after 100
set_property OUTPUT_VALUE 0 $reset_probe
commit_hw_vio $vio
puts "VIO CPU reset pulsed; boot-mode probes were unchanged."
