#!/usr/bin/env python3
"""Matched local requester PPA with every functional port retained.

Uses actual Lane request/queue types and byte-address width. Other inputs stay
dynamic; only physical Lane ID and root-cache specialization are fixed.
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
    p.add_argument('--arithmetic-forward', action='store_true', help='Compare arithmetic-only forwarding with root-cache refinement on')
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
    source = out/'operand_requester.sv'
    shutil.copy2(root/'hardware/src/lane/operand_requester.sv', source)
    lane = (root/'hardware/src/lane/lane.sv').read_text()
    begin = lane.index('  typedef struct packed {')
    end = lane.index('} operand_queue_cmd_t;', begin) + len('} operand_queue_cmd_t;')
    types = lane[begin:end]
    package = out/'requester_area_types.sv'
    package.write_text('package requester_area_types;\nimport ara_pkg::*; import rvv_pkg::*;\n'
        'localparam int VLEN=1024;\ntypedef logic [$clog2(VLEN+1)-1:0] vlen_t;\n'
        'typedef logic [$clog2((VLEN/4/8)*32)-1:0] vaddr_t;\n' + types + '\nendpackage\n')
    text = source.read_text()
    ports = text.split('  ) (', 1)[1].split('  );', 1)[0]
    ports = '\n'.join(line for line in ports.splitlines() if 'lane_id_i' not in line)
    port_names = re.findall(r'^\s*(?:input|output)\s+.*?\b(\w+)\s*,?\s*$', ports, re.M)
    assert len(port_names) >= 40 and len(port_names) == len(set(port_names))
    wrapper = out/'requester_area_top.sv'
    wrapper.write_text('module requester_area_top import ara_pkg::*; import rvv_pkg::*; '
        'import requester_area_types::*;\n'
        '#(parameter int LaneId=0, parameter bit RootCache=0, parameter bit ArithmeticOnly=0, '
        'localparam int NrLanes=4, NrBanks=8, StrbWidth=8, '
        'localparam type strb_t=logic[7:0]) (\n' + ports + '\n);\n'
        'operand_requester #(.NrLanes(4),.VLEN(1024),.NrBanks(8),'
        '.vaddr_t(vaddr_t),.operand_request_cmd_t(operand_request_cmd_t),'
        '.operand_queue_cmd_t(operand_queue_cmd_t),.RootOnlyReductionCache(RootCache),'
        '.ArithmeticOnlyForwarding(ArithmeticOnly)) dut (\n'
        '.lane_id_i(LaneId[1:0]),\n' + ',\n'.join('.'+name+'('+name+')' for name in port_names) + '\n);\nendmodule\n')
    lines = (ref/'backend/flist/ara_soc_dc.f').read_text().splitlines()
    matches = [i for i,s in enumerate(lines) if s.endswith('/operand_requester.sv')]
    assert len(matches) == 1
    lines[matches[0]] = str(source)
    lines += [str(package), str(wrapper)]
    filelist = out/'filelist'
    filelist.write_text('\n'.join(lines)+'\n')
    result = {'scope':'local requester with all ports dynamic/retained except Lane ID; 4Lane/VLEN1024; not SoC PPA',
              'reference_manifest_sha256':sha(ref/'manifest.json'), 'libraries':manifest['libraries'],
              'new_sources':{str(f):sha(f) for f in [source, package, wrapper]},
              'port_names':port_names, 'results':{}}
    jobs = []
    variants = [('root',0,0,0),('nonroot',1,0,0),('nonroot_compact',1,1,0)]
    if a.arithmetic_forward:
        variants = [('root_reference',0,1,0),('root_arithmetic',0,1,1),
                    ('nonroot_reference',1,1,0),('nonroot_arithmetic',1,1,1)]
    result['mechanism'] = 'arithmetic_forward' if a.arithmetic_forward else 'root_cache'
    for name,lane_id,cache,arithmetic in variants:
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
if {{![elaborate requester_area_top -parameters LaneId={lane_id},RootCache={cache},ArithmeticOnly={arithmetic}]}} {{exit 1}}
current_design [get_designs requester_area_top*]
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
report_timing -max_paths 10 -significant_digits 6 > timing.rpt
check_timing > check_timing.rpt
write -format ddc -hierarchy -output mapped.ddc
puts REQUESTER_PPA_COMPLETE
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
        ok = completed.returncode == 0 and 'REQUESTER_PPA_COMPLETE' in text.splitlines() and not re.search(r'^Error:',text,re.M)
        result['results'][name] = {'returncode':completed.returncode,'complete':ok,'log_sha256':sha(directory/'console.log')}
        (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
        if not ok:
            raise SystemExit('Failed '+name)
        print(name+' complete',flush=True)


if __name__ == '__main__':
    main()
