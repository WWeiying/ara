set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "START : 09_chipfinish $rundate" >> ../reports/runtime.log

setMultiCpuUsage -localCpu 8

#restoreDesign ../save/postRoute_final.enc.dat ara_soc

#===== add decap cell =====
set decap_cell "DCAP32BWP12T40P140 DCAP16BWP12T40P140 DCAP8BWP12T40P140"
setFillerMode -diffCellViol true -doDRC true -corePrefix DeCap -core {DCAP32BWP12T40P140 DCAP16BWP12T40P140 DCAP8BWP12T40P140}
addFiller
verifyGeometry
ecoRoute
addFiller -ecoMode true -fixDRC

checkPlace

#===== add filler cell =====
set filler_cell "FILL64BWP12T40P140 FILL32BWP12T40P140 FILL16BWP12T40P140 FILL8BWP12T40P140 FILL4BWP12T40P140 FILL3BWP12T40P140 FILL2BWP12T40P140"

setFillerMode -diffCellViol true -doDRC true -corePrefix Filler -core {FILL64BWP12T40P140 FILL32BWP12T40P140 FILL16BWP12T40P140 FILL8BWP12T40P140 FILL4BWP12T40P140 FILL3BWP12T40P140 FILL2BWP12T40P140}
addFiller

#===== connect pg net =====
globalNetConnect VDD -type pgpin -pin {VDD} -inst *
globalNetConnect VDD -type tiehi -pin {VDD} -inst *
globalNetConnect VDD -type net -net VDD
globalNetConnect VSS -type pgpin -pin {VSS} -inst *
globalNetConnect VSS -type tielo -pin {VSS} -inst *
globalNetConnect VSS -type net -net VSS

verifyConnectivity -type all -error 1000 -warning 50

saveDesign ../save/postRoute_fill_std.enc

#===== output def =====
file mkdir ../data

set leftDefOutVersion 5.8
defOut -floorplan -netlist -routing ../data/ara_soc.def



#==== output netlist====
saveNetlist ../data/ara_soc.vg
saveNetlist ../data/ara_soc_lvs.vg \
        -includePhysicalCell {DCAP32BWP12T40P140 DCAP16BWP12T40P140 DCAP8BWP12T40P140} \
        -excludeLeafCell \
        -includePowerGround \
        -flattenBus

set top_cell ara_soc 
set text_layer_number 139.0
set fid [open "create_text ${top_cell}.tcl" w+]
puts $fid "set L \[layout create ../data/ara_soc.merge.gds -dt_expand\]"
puts $fid "\$L create layer $text_layer_number"
#####add pg text
#
###VDD
set net VDD
set special_wires [dbGet [dbGet top.pgNets.name $net -p].sWires.layer.name M9 -p2]
foreach sw $special_wires {
    set llx [dbGet $sw.box_llx]
    set lly [dbGet $sw.box_lly]
    set urx [dbGet $sw.box_urx]
    set ury [dbGet $sw.box_ury]

    set x [expr ($llx + $ury) / 2.0 * 1000]
    set y [expr ($lly + $ury) / 2.0 * 1000]

    puts $fid "\$L create text ${top_cell} $text_layer_number $x $y $net"
}
##VSS
set net VSS
set special_wires [dbGet [dbGet top.pgNets.name $net -p].sWires.layer.name M9 -p2]
foreach sw $special_wires {
    set llx [dbGet $sw.box_llx]
    set lly [dbGet $sw.box_lly]
    set urx [dbGet $sw.box_urx]
    set ury [dbGet $sw.box_ury]
  
    set x [expr ($llx + $urx) / 2.0 * 1000]
    set y [expr ($lly + $ury) / 2.0 * 1000]
  
    puts $fid "\$L create text ${top_cell} $text_layer_number $x $y $net"
}

puts $fid "\$L gdsout ../data/ara_soc.merge_1.gds ${top_cell}"

close $fid



#===== output gds2 =====
setStreamOutMode -version 600
setStreamOutMode -textSize 0.1
setStreamOutMode -virtualConnection true
setStreamOutMode -uniquifyCellNamesPrefix true
setStreamOutMode -SEvianames true

streamOut ../data/ara_soc.gds2 \
	-mapFile ../library/innovus.map \
	-libName DesignLib \
	-units 1000 \
	-mode ALL

saveDesign ../save/chipfinish.enc

set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "END : 09_chipfinish $rundate" >> ../reports/runtime.log


#close
