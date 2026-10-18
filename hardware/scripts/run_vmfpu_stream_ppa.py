#!/usr/bin/env python3
"""Matched local VMFPU background-stream pruning PPA with all ports retained.

Uses actual Lane operation type and byte-address width. All functional inputs,
including Lane ID and shared ordered ADD/RCE interfaces, stay dynamic.
These estimates are not an integrated SoC reduction or routed Fmax.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--reference', type=Path, default=root/'hardware/build/synthesis/area_final_shared1_v1')
    p.add_argument('--prepare-only', action='store_true')
    a = p.parse_args()
    out, ref = a.out.resolve(), a.reference.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((ref/'manifest.json').read_text())
    for f in manifest['frozen_files']:
        assert sha(ref/f['snapshot']) == f['sha256']
    for lib in manifest['libraries']:
        assert sha(Path(lib['path'])) == lib['sha256']
    libraries = [lib['path'] for lib in manifest['libraries'] if 'tcbn28' in lib['path']]
    assert len(libraries) == 4
    source = out/'vmfpu.sv'
    shutil.copy2(root/'hardware/src/lane/vmfpu.sv', source)
    lane = (root/'hardware/src/lane/lane.sv').read_text()
    end = lane.index('} vfu_operation_t;') + len('} vfu_operation_t;')
    begin = lane.rfind('  typedef struct packed {', 0, end)
    types = lane[begin:end]
    soc_sources = [ref/f['snapshot'] for f in manifest['frozen_files']
                   if str(f['snapshot']).endswith('/ara_soc.sv')]
    assert len(soc_sources) == 1
    soc = soc_sources[0].read_text()
    config_begin = soc.index('  function automatic config_pkg::cva6_user_cfg_t gen_usr_cva6_config(')
    config_end = soc.index('  endfunction', config_begin) + len('  endfunction')
    config_function = soc[config_begin:config_end]
    config_constants = '''
localparam int AxiAddrWidth=64, AxiNarrowDataWidth=64, AxiIdWidth=5, AxiUserWidth=1;
localparam fpu_support_e FPUSupport=FPUSupportHalfSingleDouble;
localparam logic[63:0] UARTBase=64'hC0000000, CTRLBase=64'hD0000000, DRAMBase=64'h80000000;
localparam logic[63:0] UARTLength=64'h1000, CTRLLength=64'h1000, DRAMLength=64'h40000000;
'''
    package = out/'vmfpu_area_types.sv'
    package.write_text('package vmfpu_area_types;\nimport ara_pkg::*; import rvv_pkg::*;\n'
        'localparam int VLEN=1024;\ntypedef logic [$clog2(VLEN+1)-1:0] vlen_t;\n'
        'typedef logic [$clog2((VLEN/4/8)*32)-1:0] vaddr_t;\n' + types + '\n'
        + config_constants + config_function + '\n'
        'localparam config_pkg::cva6_cfg_t CVA6Cfg = build_config_pkg::build_config('
        'gen_usr_cva6_config(cva6_config_pkg::cva6_cfg));\nendpackage\n')
    text = source.read_text()
    ports = text.split('  ) (', 1)[1].split('  );', 1)[0]
    port_names = re.findall(r'^\s*(?:input|output)\s+.*?\b(\w+)\s*,?\s*$', ports, re.M)
    assert len(port_names) >= 45 and len(port_names) == len(set(port_names))
    wrapper = out/'vmfpu_area_top.sv'
    wrapper.write_text('module vmfpu_area_top import ara_pkg::*; import rvv_pkg::*; '
        'import fpnew_pkg::*; import cf_math_pkg::idx_width; import vmfpu_area_types::*;\n'
        '#(localparam int NrLanes=4, StrbWidth=8, '
        'localparam type strb_t=logic[7:0]) (\n' + ports + '\n);\n'
        'vmfpu #(.NrLanes(4),.VLEN(1024),.CVA6Cfg(CVA6Cfg),.vaddr_t(vaddr_t),'
        '.vfu_operation_t(vfu_operation_t)) dut (\n'
        + ',\n'.join('.'+name+'('+name+')' for name in port_names) + '\n);\nendmodule\n')
    lines = (ref/'backend/flist/ara_soc_dc.f').read_text().splitlines()
    matches = [i for i,s in enumerate(lines) if s.endswith('/vmfpu.sv')]
    assert len(matches) == 1
    lines[matches[0]] = str(source)
    lines += [str(package), str(wrapper)]
    lines = [s for s in lines if not s.startswith('+define+ARA_RED_PRUNE_LEGACY_FP_STREAM')]
    assert '+define+ARA_RED_SHARED_ORDERED_ADD=1' in lines
    assert '+define+ARA_RED_RCE_EXACT_DIRECT=1' in lines
    assert '+define+ARA_RED_EXACT_FP16_4LANE=1' in lines
    result = {'scope':'local VMFPU; all ports dynamic, shared ADD external; 4Lane/VLEN1024; not SoC PPA',
              'reference_manifest_sha256':sha(ref/'manifest.json'), 'libraries':manifest['libraries'],
              'config_function_origin':str(soc_sources[0]),
              'config_function_origin_sha256':sha(soc_sources[0]),
              'new_sources':{str(f):sha(f) for f in [source, package, wrapper]},
              'port_names':port_names, 'results':{}}
    jobs = []
    for name, prune in [('baseline',0),('scalar',1)]:
        directory = out/name
        directory.mkdir()
        filelist = directory/'filelist'
        selected = lines + (['+define+ARA_RED_PRUNE_LEGACY_FP_STREAM=1'] if prune else [])
        filelist.write_text('\n'.join(selected)+'\n')
        alib = ref/'backend/syn/ara_soc/v1-dc/run/alib-52'
        if alib.exists():
            shutil.copytree(alib, directory/'alib-52')
        script = f'''set_app_var target_library {{{' '.join(libraries)}}}
set_app_var synthetic_library {{dw_foundation.sldb}}
set_app_var search_path [concat $search_path {{{manifest['dc_home']}/libraries/syn}}]
set_app_var link_library [concat * $target_library $synthetic_library]
define_design_lib WORK -path ./work
set_host_options -max_cores 2
set compile_register_replication false
set compile_enable_register_merging false
if {{![analyze -format sverilog -vcs {{-f {filelist}}}]}} {{exit 1}}
if {{![elaborate vmfpu_area_top]}} {{exit 1}}
current_design [get_designs vmfpu_area_top*]
if {{![link]}} {{exit 1}}
check_design > check_design_before.rpt
create_clock -period 1.0 [get_ports clk_i]
set_clock_uncertainty .15 [get_clocks clk_i]
set_false_path -from [get_ports rst_ni]
set_input_delay .1 -clock clk_i [remove_from_collection [all_inputs] [get_ports {{clk_i rst_ni}}]]
set_output_delay .1 -clock clk_i [all_outputs]
set_load .02 [all_outputs]
set_driving_cell -lib_cell BUFFD4BWP12T40P140 [remove_from_collection [all_inputs] [get_ports {{clk_i rst_ni}}]]
if {{![compile_ultra -no_autoungroup -no_seq_output_inversion]}} {{exit 1}}
check_design > check_design_after.rpt
report_area -hierarchy > area.rpt
report_qor > qor.rpt
report_timing -delay_type max -max_paths 10 -significant_digits 6 > timing.rpt
report_timing -delay_type min -max_paths 10 -significant_digits 6 > hold.rpt
check_timing > check_timing.rpt
write -format ddc -hierarchy -output mapped.ddc
puts VMFPU_STREAM_PPA_COMPLETE
exit 0
'''
        (directory/'run.tcl').write_text(script)
        jobs.append((name,directory))
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    if a.prepare_only:
        return
    for name,directory in jobs:
        command = ['docker','exec','-u',f'{os.getuid()}:{os.getgid()}',
                   '-e','SNPSLMD_LICENSE_FILE=27000@t7920','-w',str(directory),manifest['container'],
                   manifest['dc_home']+'/bin/dc_shell-t','-64bit','-f','run.tcl']
        with (directory/'console.log').open('w') as log:
            completed = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        text = (directory/'console.log').read_text(errors='replace')
        ok = completed.returncode == 0 and 'VMFPU_STREAM_PPA_COMPLETE' in text.splitlines() and not re.search(r'^Error:',text,re.M)
        result['results'][name] = {'returncode':completed.returncode,'complete':ok,'log_sha256':sha(directory/'console.log')}
        (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
        if not ok:
            raise SystemExit('Failed '+name)
        print(name+' complete',flush=True)


if __name__ == '__main__':
    main()
