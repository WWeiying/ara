# Executed inside the full-design synthesis worker, not only its launcher.
source [file join [file dirname [info script]] .. scripts synth_pre.tcl]
set_param general.maxThreads 1
set_param synth.maxThreads 1
puts "FULL_SYNTH_THREADS general=[get_param general.maxThreads] synth=[get_param synth.maxThreads]"
