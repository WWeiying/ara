#!/usr/bin/env python3
"""Matched combined RCE/ordered-backend PPA with all functional ports retained.

Compares the private FP64 completion adder against an added shared client.
All completion and four Lane arithmetic inputs remain dynamic.
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
    source = out/'reduction_completion_engine.sv'
    shared = out/'shared_ordered_adder.sv'
    shutil.copy2(root/'hardware/src/reduction'/source.name, source)
    shutil.copy2(root/'hardware/src/reduction'/shared.name, shared)
    ports = source.read_text().split(') (',1)[1].split('\n);',1)[0]
    ports = re.sub(r'`ifdef ARA_RED_SHARED_RCE_ADD\n.*?`endif\n', '', ports, flags=re.S)
    port_names = re.findall(r'^\s*(?:input|output)\s+.*?\b(\w+)\s*,?\s*$',ports,re.M)
    assert len(port_names)>30 and len(port_names)==len(set(port_names))
    wrapper = out/'completion_area_top.sv'
    wrapper.write_text('module completion_area_top import ara_pkg::*; import rvv_pkg::*; import ara_rce_pkg::*;\n'
      '#(parameter bit Shared=0, localparam int NrLanes=4, ContextDepth=2, Clients=4+Shared) (\n'
      'input ordered_add_request_t[3:0] ordered_request_i,\n'
      'input logic[3:0] ordered_valid_i, output logic[3:0] ordered_ready_o,\n'
      'output ordered_add_response_t[3:0] ordered_response_o,\n'
      'output logic[3:0] ordered_response_valid_o, input logic[3:0] ordered_response_ready_i,\n'
      +ports+'\n);\n'
      'ordered_add_request_t[Clients-1:0] requests;\n'
      'ordered_add_response_t[Clients-1:0] responses;\n'
      'logic[Clients-1:0] valid,ready,out_valid,out_ready;\n'
      'ordered_add_request_t rce_request; ordered_add_response_t rce_response;\n'
      'logic rce_valid,rce_ready,rce_out_valid,rce_out_ready;\n'
      'assign requests[3:0]=ordered_request_i; assign valid[3:0]=ordered_valid_i;\n'
      'assign ordered_ready_o=ready[3:0]; assign ordered_response_o=responses[3:0];\n'
      'assign ordered_response_valid_o=out_valid[3:0]; assign out_ready[3:0]=ordered_response_ready_i;\n'
      'if(Shared) begin\n'
      ' assign requests[4]=rce_request; assign valid[4]=rce_valid; assign rce_ready=ready[4];\n'
      ' assign rce_response=responses[4]; assign rce_out_valid=out_valid[4]; assign out_ready[4]=rce_out_ready;\n'
      'end else begin assign rce_ready=0;assign rce_response=\'0;assign rce_out_valid=0;end\n'
      'shared_ordered_adder #(.NrClients(Clients),.NrUnits(1)) adder (\n'
      '.clk_i,.rst_ni,.request_i(requests),.valid_i(valid),.ready_o(ready),\n'
      '.response_o(responses),.response_valid_o(out_valid),.response_ready_i(out_ready));\n'
      'reduction_completion_engine #(.NrLanes(4),.ContextDepth(2),.UseSharedFp64Add(Shared)) completion (\n'
      '.shared_add_request_o(rce_request),.shared_add_valid_o(rce_valid),.shared_add_ready_i(rce_ready),\n'
      '.shared_add_response_i(rce_response),.shared_add_response_valid_i(rce_out_valid),.shared_add_response_ready_o(rce_out_ready),\n'
      +',\n'.join('.'+name+'('+name+')' for name in port_names)+'\n);\nendmodule\n')
    lines=(ref/'backend/flist/ara_soc_dc.f').read_text().splitlines()
    for local in [source,shared]:
        matches=[i for i,line in enumerate(lines) if line.endswith('/'+local.name)]
        assert len(matches)==1
        lines[matches[0]]=str(local)
    lines=[line for line in lines if not line.startswith('+define+ARA_RED_SHARED_RCE_ADD')]
    assert '+define+ARA_RED_SHARED_ORDERED_ADD=1' in lines
    lines+=['+define+ARA_RED_SHARED_RCE_ADD=1',str(wrapper)]
    filelist=out/'filelist';filelist.write_text('\n'.join(lines)+'\n')
    result = {'scope':'RCE plus ordered backend with all interfaces dynamic; private FP64 vs fifth-client sharing; local PPA only',
              'reference_manifest_sha256':sha(ref/'manifest.json'), 'libraries':manifest['libraries'],
              'new_sources':{str(f):sha(f) for f in [source, shared, wrapper]},
              'port_names':port_names, 'results':{}}
    jobs = []
    for name,mode in [('baseline',0),('scalar',1)]:
        directory = out/name
        directory.mkdir()
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
if {{![elaborate completion_area_top -parameters Shared={mode}]}} {{exit 1}}
current_design [get_designs completion_area_top*]
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
puts COMPLETION_PPA_COMPLETE
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
        ok = completed.returncode == 0 and 'COMPLETION_PPA_COMPLETE' in text.splitlines() and not re.search(r'^Error:',text,re.M)
        result['results'][name] = {'returncode':completed.returncode,'complete':ok,'log_sha256':sha(directory/'console.log')}
        (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
        if not ok:
            raise SystemExit('Failed '+name)
        print(name+' complete',flush=True)


if __name__ == '__main__':
    main()
