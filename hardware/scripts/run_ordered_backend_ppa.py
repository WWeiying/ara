#!/usr/bin/env python3
"""Matched local shared ADD PPA, with five fully dynamic clients and one unit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reference', type=Path, default=root/'hardware/build/synthesis/area_pair_arithmetic_v2')
    args = parser.parse_args()
    out, ref = args.out.resolve(), args.reference.resolve()
    out.mkdir(parents=True, exist_ok=False)
    original = json.loads((ref/'manifest.json').read_text())
    for entry in original['frozen_files']:
        assert sha(ref/entry['snapshot']) == entry['sha256']
    for library in original['libraries']:
        assert sha(Path(library['path'])) == library['sha256']
    libraries = [x['path'] for x in original['libraries'] if 'tcbn28' in x['path']]
    assert len(libraries) == 4
    module = out/'shared_ordered_adder.sv'
    shutil.copy2(root/'hardware/src/reduction/shared_ordered_adder.sv', module)
    lines = (ref/'backend/flist/ara_soc_dc.f').read_text().splitlines()
    assert sum(l.endswith('/shared_ordered_adder.sv') for l in lines) == 1
    lines = [str(module) if l.endswith('/shared_ordered_adder.sv') else l for l in lines]
    manifest = {'scope': 'local shared ordered ADD; five dynamic clients, one unit; not SoC area or routed Fmax',
                'reference': str(ref), 'libraries': original['libraries'],
                'sources': {l: sha(Path(l)) for l in lines if l.startswith('/') and Path(l).is_file()},
                'results': {}}
    for mode in ('baseline', 'scalar'):
        directory = out/mode
        directory.mkdir()
        flags = [] if mode == 'baseline' else ['+define+ARA_RED_STATIC_ORDERED_ARBITER=1',
                                              '+define+ARA_RED_COMPACT_ORDERED_BACKEND=1']
        filelist = directory/'filelist'
        filelist.write_text('\n'.join(lines+flags)+'\n')
        script = f'''set_app_var target_library {{{' '.join(libraries)}}}
set_app_var synthetic_library {{dw_foundation.sldb}}
set_app_var search_path [concat $search_path {{{original['dc_home']}/libraries/syn}}]
set_app_var link_library [concat * $target_library $synthetic_library]
define_design_lib WORK -path ./work
set_host_options -max_cores 2
set compile_seqmap_propagate_constants false
set compile_register_replication false
set compile_enable_register_merging false
if {{![analyze -format sverilog -vcs {{-f {filelist}}}]}} {{exit 1}}
if {{![elaborate shared_ordered_adder -parameters NrClients=5,NrUnits=1]}} {{exit 1}}
current_design [get_designs shared_ordered_adder*]
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
puts ORDERED_BACKEND_PPA_COMPLETE
exit 0
'''
        (directory/'run.tcl').write_text(script)
    manifest['frozen_files'] = {str(p): sha(p) for mode in ('baseline', 'scalar')
                                for p in (out/mode/'filelist', out/mode/'run.tcl')}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    for mode in ('baseline', 'scalar'):
        directory = out/mode
        command = ['docker', 'exec', '-u', f'{os.getuid()}:{os.getgid()}', '-e',
                   'SNPSLMD_LICENSE_FILE=27000@t7920', '-w', str(directory),
                   original['container'], original['dc_home']+'/bin/dc_shell-t', '-64bit', '-f', 'run.tcl']
        with (directory/'console.log').open('w') as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        text = (directory/'console.log').read_text(errors='replace')
        ok = completed.returncode == 0 and 'ORDERED_BACKEND_PPA_COMPLETE' in text.splitlines() and not re.search(r'^Error:', text, re.M)
        manifest['results'][mode] = {'complete': ok, 'returncode': completed.returncode,
                                     'log_sha256': sha(directory/'console.log')}
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        if not ok:
            raise SystemExit('Failed '+mode)
        print(mode+' complete', flush=True)


if __name__ == '__main__':
    main()
