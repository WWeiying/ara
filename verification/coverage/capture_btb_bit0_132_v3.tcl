# Exact compiled generate-instance display alias; all v2 protocol/EL checks retained.
set ::btb_v2_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_btb_bit0_132_v2.tcl}
set btb_alias_old {($name eq "i_btb" || $name eq "btb")}
set btb_alias_new {($name eq "i_btb" || $name eq "btb" || $name eq "btb_gen.i_btb")}
set btb_alias_body [info body btb_root]
if {[string first $btb_alias_old $btb_alias_body] < 0 ||
    [string first $btb_alias_old $btb_alias_body] != [string last $btb_alias_old $btb_alias_body]} {
    error "Expected unique frozen v2 display predicate"
}
proc btb_root {} [string map [list $btb_alias_old $btb_alias_new] $btb_alias_body]
btb_main
