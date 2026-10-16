set ::scalar_connections_test 1
source [file join [file dirname [info script]] audit_scalar_connections.tcl]
proc get_nets {args} {
    if {[lrange $args 0 2] ne {-quiet -segments -of_objects}} { error "Wrong net query" }
    return [dict get $::nets [lindex $args 3]]
}
proc check {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error $message }
}
set ::nets [dict create source {source_alias shared} probe {probe_alias shared}]
check {[scalar_connections::connected source probe] eq "shared"} "Aliased electrical connection rejected"
dict set ::nets probe {same_suffix different_net}
check {[catch {scalar_connections::connected source probe}]} "Unconnected signals accepted"
dict set ::nets probe {}
check {[catch {scalar_connections::connected source probe}]} "Missing probe net accepted"
check {[catch {scalar_connections::one {} source}]} "Missing object accepted"
check {[catch {scalar_connections::one {a b} source}]} "Ambiguous object accepted"
check {[catch {scalar_connections::source_pin net cell name FDRE}]} "Unsupported net-name-only source accepted"
puts "SCALAR_CONNECTION_HELPERS_PASS (not a routed connectivity or hardware pass)"
