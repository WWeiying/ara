# Tcl8.4. Only the pinned CSV procedure is installed, never the exporter main.
source [file join $env(DVE_COVERAGE_OUTPUT) csv-row-library.tcl]
if {[llength [info commands csv_row]]!=1} {error "Missing successor CSV writer"}
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/rvh_nine_policy_runtime.tcl}
