set ::stall_ila_test 1
source [file join [file dirname [info script]] prepare_stall_ila.tcl]
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error $message }
}
proc get_clocks {args} { return $::clocks }
proc get_property {property object} {
    if {$property ne "PERIOD"} { error "Unexpected property" }
    return $::period
}
set ::clocks core50
set ::period 20.0
assert {![catch {stall_clock cell/C core50}]} "Valid clock rejected"
set ::period 10.0
assert {[catch {stall_clock cell/C core50}]} "Wrong period accepted"
set ::period 20.0
assert {[catch {stall_clock cell/C other50}]} "Different same-frequency domain accepted"
set ::clocks {}
assert {[catch {stall_clock cell/C core50}]} "Missing clock accepted"
set ::clocks {core50 unrelated}
assert {[catch {stall_clock cell/C core50}]} "Ambiguous clock accepted"
assert {[catch {stall_one {} source}]} "Missing source accepted"
assert {[catch {stall_one {a b} source}]} "Ambiguous source accepted"
assert {[stall_one a source] eq "a"} "Single source rejected"
puts "STALL_ILA_VALIDATION_HELPERS_PASS (not an implementation or hardware pass)"
