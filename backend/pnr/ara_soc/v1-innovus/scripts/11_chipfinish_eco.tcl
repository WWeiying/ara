set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "START : 09_chipfinish $rundate" >> ../report/runtime.log

setMulticpuUsage -localcpu 2

restoreDesign ../save/eoc_vl.enc.dat cortexa7core

#===== add decap cell =====
set decap_cell "DCAP32BWP40P140 DCAP16BWP40P140 DCAPBBWP40P140"
setFillerMode -diffcellViol true -doDRc true -corePrefix DeCap -core {DCAP32BWP40P140 DCAP16BWP40P140 DCAP8BWP40P140}
addFiller
verifyGeometry
ecoRoute
addFiller -ecoMode true -fixDRc

checkPlace

#===== add filler cell =====
Set filler_cell "FILL64BWP4OP140 FILL32BWP40P140 FILL16BWP40P140 FILL8BWP4OP140 FILL4BWP4OP140 FILL3BWP4OP140 FILL2BWP40P140"

setFillerMode -diffcellViol true -doDRC true -coreprefix Filler -core {FILL64BWP4OP140 FILL32BWP40P140 FILL16BWP40P140 FILL8BWP4OP140 FILL4BWP4OP140 FILL3BWP4OP140 FILL2BWP40P140}
addFiller

globalNetConnect VDD -type pgpin -pin {VDD} -inst *
globalNetConnect VDD -type tiehi -pin {VDD} -inst *
globalNetConnect VDD -type net   -net VDD
globalNetConnect VSS -type pgpin -pin {VSS} -inst *
globalNetConnect VSS -type tielo -pin {VSS} -inst *
globalNetConnect VSS -type net   -net VSS

verifyConnectivity -type all -error 1000 -warning 50

saveDesign ../save/eco_fill_std.enc

#===== output netlist =====
file mkdir./data_eco
saveNetlist ../data_eco/cortexa7core.vg
saveNetlist ../data_eco/cortexa7core_lvs.Vg \
       -includePhysicaLCell {DCAP32BWP40P140 DCAP16BWP40P140 DCAP8BWP40P140} \
       -excluneLeafCell \
       -includePowerGround \
       -flattenBus

#===== output def =====
set lefDefOutVersion 5.8
defOut -floorplan -netlist -routing ../data_eco/cortexa7core.def

set top_cell cortexa7core
set text_layer_number 139.0
set fid [open "create text ${top_cell}.tcl" w+]
puts $fid "set L \layout create ../../innovus/data_eco/cortexa7core.merge.gds -dt expand\]"
puts $fid "\$LL create layer $text layer number"
####add pg text

###VDD
  set net VDD
  set special_wires [dbGet [dbGet top.pgNets.name $net -p].sWires.layer.name M9 -p2]
  foreach sw_$special_wires {
    set llx [dbGet $sw.box_llx]
    set lly [dbGet $sw.box_lly]
    set urx [dbGet $sw.box_urx]
    set ury [dbGet $sm.box_ury]

    set x [expr ($llx+$urx)/2.0*1000]
    set y [expr ($lly+$ury)/2.0*1000]

    puts $fid "\$L create text ${top_cell} $text_layer number $x $y $net"
  }
## VSS
set net VSS
set special_wires [dbGet [dbGet top.pgNets.name $net -p].sWires.layer.name M9 -p2]
foreach sw $sodcisl_wires {
  set llx [dbGet $sw.box_llx]
  set lly [dbGet $sw.box_lly]
  set urx [dbGet $sw.box_urx]
  set ury [dbGet $sw.box_ury]

  set x [expr($llx+$urx) / 2.0*1000]
  set y [expr($lly+$ury) / 2.0*1000]

  puts $fid "\$L create text ${top_cell} $text_layer_number $x $y $net"
}

puts $fid "\$L gdsout ../../innovus/data_eco/cortexa7core.merge 1.gds ${top_cell}"

close $fid



#===== output gds2 =====
setStreamOutMode -version 600
setStreamDutMode -textSize 0.1
setstreamDutMode -virtualConnection true
setStreamDutMode -uniquifycellNamesPrefix true
setStream0utMade -SEvianames true

streamOut ../data_eco/cortexa7core.gds2 \
        -mapFile /data/tech/gdsout_5X2Y2Z_innovus.map \
        -libName DesignLib \
        -units 1000 \
        -mode ALL

saveDesign ../save/chipfinish_eco.enc

set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "END :09_chipfinish $rundate" >> ../report/runtime.log


close
