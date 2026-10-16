set ::ara_mb_library_only 1
source [file join [file dirname [info script]] .. ethernet ara_mb_download.tcl]
proc connect {args} {}
proc disconnect {} { incr ::disconnected }
proc targets {args} {
    if {[lindex $args 0] eq "-target-properties"} { return $::targets }
    if {$args ne {-set -filter {name == "MicroBlaze #0"}}} { error "Unexpected target selection" }
    lappend ::calls select
}
proc rst {args} {
    if {$args ne {-processor -stop}} { error "System reset forbidden" }
    lappend ::calls reset
}
proc dow {args} { lappend ::calls download; if {$::fail} { error "download failed" } }
proc con {} { lappend ::calls continue }
foreach count {0 1 2} {
    set targets {}
    for {set i 0} {$i < $count} {incr i} { lappend targets {name {MicroBlaze #0} target_id 3} }
    set calls {}; set disconnected 0; set fail 0
    set failed [catch {ara_mb_download [info script] tcp:localhost:3121}]
    if {$count == 1} {
        if {$failed || $calls ne {select reset download continue}} { error "Sequence mismatch" }
    } elseif {!$failed || $calls ne {}} { error "Ambiguous target must not be touched" }
    if {$disconnected != 1} { error "Connection not closed" }
}
set targets {{name {MicroBlaze #0} target_id 3}}
set calls {}; set fail 1
if {![catch {ara_mb_download [info script] tcp:localhost:3121}] ||
    $calls ne {select reset download}} { error "Failed download must not continue" }
rename source original_source
proc source {path} {
    if {$path ne $::ara_mb_clock_helper} { error "Unexpected helper" }
    namespace eval ara_phy_clock {
        proc prepare {} {
            lappend ::calls prepare
            if {$::clock_fail} { error "clock failed" }
        }
    }
}
set fail 0
foreach clock_fail {0 1} {
    set calls {}; set disconnected 0
    set failed [catch {ara_mb_download [info script] tcp:localhost:3121 1}]
    set expected [expr {$clock_fail ? "select reset prepare" : "select reset prepare download continue"}]
    if {$failed != $clock_fail || $calls ne $expected || $disconnected != 1} {
        error "PHY preparation ordering/failure protection mismatch: $calls"
    }
}
puts "ARA_MB_DOWNLOAD_TEST_PASS"
