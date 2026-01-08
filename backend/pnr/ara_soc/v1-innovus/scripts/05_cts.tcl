set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "START : 05_cts $rundate" >> ../reports/runtime.log

setMultiCpuUsage -localCpu 8

#restoreDesign ../save/preCTS.enc.dat ara_soc


set cts_buffer_cells   [list CKBD2BWP12T40P140 CKBD3BWP12T40P140 CKBD4BWP12T40P140 CKBD6BWP12T40P140 CKBD8BWP12T40P140 CKBD12BWP12T40P140 CKBD16BWP12T40P140 ]
set cts_inv_cells            [list CKND2BWP12T40P140 CKND3BWP12T40P140 CKND4BWP12T40P140 CKND6BWP12T40P140 CKND8BWP12T40P140 CKND12BWP12T40P140 CKND16BWP12T40P140 ]
set cts_gate_cells          [list CKLNQD3BWP12T40P140 CKLNQD4BWP12T40P140 CKLNQD6BWP12T40P140 CKLNQD8BWP12T40P140 CKLNQD12BWP12T40P140 CKLNQD16BWP12T40P140]


foreach libraryname $cts_inv_cells {
echo "setDontUse $libraryname false"
setDontUse $libraryname false
}

foreach libraryname $cts_gate_cells {
echo "setDontUse $libraryname false"
setDontUse $libraryname false
}


set_ccopt_property use_inverters true
set_ccopt_property inverter_cells $cts_inv_cells
set_ccopt_property clock_gating_cells $cts_gate_cells

set_ccopt_property target_max_trans 0.12
set_ccopt_property target_skew 0.02
set_ccopt_property max_fanout 24
set_ccopt_property target_insertion_delay 0.3

#setOptMode -usefulSkew true
#setOptMode -usefulSkewCCopt standard

add_ndr -name cts_w2s2 -width_multiplier {M5:M8 2} -spacing_multiplier {M5:M8 2}
create_route_type -name trunk_rule -non_default_rule cts_w2s2 -top_preferred_layer M8 -bottom_preferred_layer M5
set_ccopt_property route_type trunk_rule -net_type trunk


setNanoRouteMode -quiet -routeTopRoutingLayer 9 -routeBottomRoutingLayer 2

create_ccopt_clock_tree_spec -file clock.spec
source clock.spec

ccopt_design -cts

saveDesign ../save/CTS.enc

set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "END : 05_cts $rundate" >> ../reports/runtime.log

#close
