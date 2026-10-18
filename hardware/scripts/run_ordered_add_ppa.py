#!/usr/bin/env python3
"""Frozen, matched local synthesis for ordered recurrence specialization."""
import argparse, hashlib, json, os, re, shutil, subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
p.add_argument('--modes',type=int,nargs='+',choices=range(4),default=[0,1,2])
a=p.parse_args()
root=Path(__file__).resolve().parents[2];out=a.out.resolve();out.mkdir(exist_ok=False,parents=True)
base=root/'hardware/build/synthesis/full_retry2';m=json.loads((base/'manifest.json').read_text())
libs=[x['path'] for x in m['libraries'] if '/logic/' in x['path'] and x['path'].endswith('.db')]
assert len(libs)==4
src=root/'hardware/tb/ordered_add_ppa_top.sv';shutil.copy2(src,out/src.name)
lines=[]
for l in (base/'backend/flist/ara_soc_dc.f').read_text().splitlines():
 if l.startswith('+') or '/common_cells/' in l or '/fpnew/' in l:lines.append(l)
lines.append(str(out/src.name));(out/'filelist').write_text('\n'.join(lines)+'\n')
manifest={'scope':'local ordered FPU; modes 0 original,1 constant ADD,2 scalar ADD,3 scalar ADD with output register; identical 8-bit tags',
 'libraries':libs,'source_sha256':{},'results':{}}
for l in lines:
 if l.startswith('/') and Path(l).is_file():manifest['source_sha256'][l]=hashlib.sha256(Path(l).read_bytes()).hexdigest()
for mode in a.modes:
 d=out/str(mode);d.mkdir()
 cache=base/'backend/syn/ara_soc/v1-dc/run/alib-52'
 if cache.is_dir():shutil.copytree(cache,d/'alib-52')
 t=f'''set_app_var target_library {{{' '.join(libs)}}}
set_app_var synthetic_library {{dw_foundation.sldb}}
set_app_var search_path [concat $search_path {{{m['dc_home']}/libraries/syn}}]
set_app_var link_library [concat * $target_library $synthetic_library]
define_design_lib WORK -path ./work
set_host_options -max_cores 4
set compile_register_replication false
set compile_enable_register_merging false
if {{![analyze -format sverilog -vcs "-f {out}/filelist"]}} {{exit 1}}
if {{![elaborate ordered_add_ppa_top -parameters Mode={mode}]}} {{exit 1}}
current_design [get_designs ordered_add_ppa_top*]
if {{![link]}} {{exit 1}}
create_clock -period 1.0 [get_ports clk_i]
set_clock_uncertainty .15 [get_clocks clk_i]
set_false_path -from [get_ports rst_ni]
set_input_delay .1 -clock clk_i [remove_from_collection [all_inputs] [get_ports {{clk_i rst_ni}}]]
set_output_delay .1 -clock clk_i [all_outputs]
set_load .02 [all_outputs]
set_driving_cell -lib_cell BUFFD4BWP12T40P140 [remove_from_collection [all_inputs] [get_ports {{clk_i rst_ni}}]]
if {{![compile_ultra -no_autoungroup -no_seq_output_inversion]}} {{exit 1}}
report_area -hierarchy > area.rpt
report_qor > qor.rpt
report_timing -max_paths 10 > timing.rpt
check_timing > check_timing.rpt
write -format ddc -hierarchy -output mapped.ddc
puts ORDERED_PPA_COMPLETE
exit 0
'''
 (d/'run.tcl').write_text(t)
 cmd=['docker','exec','-u',f'{os.getuid()}:{os.getgid()}','-e','SNPSLMD_LICENSE_FILE=27000@t7920','-w',str(d),m['container'],m['dc_home']+'/bin/dc_shell-t','-64bit','-f','run.tcl']
 with (d/'console.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 text=(d/'console.log').read_text();ok=r.returncode==0 and 'ORDERED_PPA_COMPLETE' in text.splitlines() and not re.search(r'^Error:',text,re.M)
 manifest['results'][str(mode)]={'returncode':r.returncode,'complete':ok}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 if not ok:raise SystemExit('Failed mode '+str(mode))
 print('Complete mode',mode,flush=True)
