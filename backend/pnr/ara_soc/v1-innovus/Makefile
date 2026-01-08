.PHONY: cpfiles import floorplan power_routing placeopt cts ctsopt route routeopt chipfinish pteco chipfinisheco clean

cpfiles:
	cd inputs && cp ara_soc_dc.v ara_soc_pnr.v && cp ara_soc_dc.sdc ara_soc_pnr.sdc 
	
import:
	cd work && innovus -files ../scripts/01_innovus_import_design.tcl

floorplan: import
	cd work && innovus -files ../scripts/02_create_floorplan.tcl

power_routing: floorplan
	cd work && innovus -files ../scripts/03_power_routing.tcl

placeopt: power_routing
	cd work && innovus -files ../scripts/04_placeopt.tcl

cts: placeopt
	cd work && innovus -files ../scripts/05_cts.tcl

ctsopt: cts
	cd work && innovus -files ../scripts/06_ctsopt.tcl

route: ctsopt
	cd work && innovus -files ../scripts/07_route.tcl

routeopt: route
	cd work && innovus -files ../scripts/08_routeopt.tcl

chipfinish: routeopt
	cd work && innovus -files ../scripts/09_chipfinish.tcl

pteco: chipfinish
	cd work && innovus -files ../scripts/10_pteco.tcl

chipfinisheco: pteco
	cd work && innovus -files ../scripts/11_chipfinish_eco.tcl

clean:
	rm -r ./save/* ./work/*	
