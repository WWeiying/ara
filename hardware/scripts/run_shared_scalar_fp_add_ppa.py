#!/usr/bin/env python3
"""Prepare matched runtime FP16/32/64 FMA, scalar slices, and shared ADD PPA."""
import argparse
import datetime
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
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--reference', type=Path, default=root/'hardware/build/synthesis/area_pair_timing_v4')
    parser.add_argument('--prepare-only', action='store_true', help='Prepare only (the default)')
    parser.add_argument('--run', action='store_true', help='Explicitly launch all three DC jobs after preparing')
    args = parser.parse_args()
    if args.run and args.prepare_only:
        parser.error('--run and --prepare-only are mutually exclusive')
    out, ref = args.out.resolve(), args.reference.resolve()
    out.mkdir(parents=True, exist_ok=False)
    original = json.loads((ref/'manifest.json').read_text())
    for entry in original['frozen_files']:
        assert sha(ref/entry['snapshot']) == entry['sha256'], entry['snapshot']
    libraries = [entry for entry in original['libraries'] if '/logic/' in entry['path'] and entry['path'].endswith('.db')]
    assert len(libraries) == 4
    for entry in libraries:
        assert sha(Path(entry['path'])) == entry['sha256'], entry['path']
    for src in (root/'hardware/src/reduction/scalar_fp_add.sv', root/'hardware/src/reduction/shared_scalar_fp_add.sv', root/'hardware/tb/shared_scalar_fp_add_ppa_top.sv', Path(__file__)):
        shutil.copy2(src, out/src.name)
    shutil.copy2(ref/'manifest.json', out/'reference_manifest.json')
    shutil.copy2(ref/'backend/flist/ara_soc_dc.f', out/'reference_filelist')
    lines = (out/'reference_filelist').read_text().splitlines()
    assert not any(line.endswith('/scalar_fp_add.sv') for line in lines)
    lines += [str(out/'scalar_fp_add.sv'), str(out/'shared_scalar_fp_add.sv'), str(out/'shared_scalar_fp_add_ppa_top.sv')]
    dependencies = {line: sha(Path(line)) for line in lines if Path(line).is_absolute() and Path(line).is_file()}
    for line in lines:
        if line.startswith('+incdir+'):
            for directory in line[len('+incdir+'):].split('+'):
                for path in Path(directory).rglob('*'):
                    if path.is_file() and path.suffix in ('.svh','.vh','.sv','.h'):
                        dependencies[str(path)] = sha(path)
    manifest = {'scope': 'local registered runtime-format FP16/32/64 adders; no SoC or routed Fmax claim',
                'prepared_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'reference': str(ref), 'reference_manifest_sha256': sha(ref/'manifest.json'),
                'libraries': libraries, 'dependencies': dependencies, 'results': {},
                'constraints': {'period_ns': 1.0, 'uncertainty_ns': .15, 'input_delay_ns': .1,
                                'output_delay_ns': .1, 'load_pf': .02, 'driving_cell': 'BUFFD4BWP12T40P140'},
                'contract': 'Three modes retain identical dynamic 64-bit a,b,format,rm and selected boxed result/fflags; same input/output registers. Only FP16/FP32/FP64 are tested; other format encodings select FP64 for this experiment.',
                'dc_started': False}
    for mode, value in [('fma_add',0),('scalar_slices',1),('shared_add',2)]:
        directory = out/mode
        directory.mkdir()
        cache = ref/'backend/syn/ara_soc/v1-dc/run/alib-52'
        if cache.is_dir():
            shutil.copytree(cache, directory/'alib-52')
        filelist = directory/'filelist'
        filelist.write_text('\n'.join(lines)+'\n')
        script = f'''set_app_var target_library {{{' '.join(e['path'] for e in libraries)}}}
set_app_var synthetic_library {{dw_foundation.sldb}}
set_app_var search_path [concat $search_path {{{original['dc_home']}/libraries/syn}}]
set_app_var link_library [concat * $target_library $synthetic_library]
define_design_lib WORK -path ./work
set_host_options -max_cores 2
set compile_seqmap_propagate_constants false
set compile_register_replication false
set compile_enable_register_merging false
if {{![analyze -format sverilog -vcs {{-f {filelist}}}]}} {{exit 1}}
if {{![elaborate shared_scalar_fp_add_ppa_top -parameters Mode={value}]}} {{exit 1}}
current_design [get_designs shared_scalar_fp_add_ppa_top*]
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
report_timing -delay_type max -max_paths 20 -significant_digits 6 > timing.rpt
report_timing -delay_type max -from [all_registers -clock clk_i -output_pins] -to [all_registers -clock clk_i -data_pins] -max_paths 20 -significant_digits 6 > register_timing.rpt
report_timing -delay_type min -max_paths 10 -significant_digits 6 > hold.rpt
report_cell [all_registers -edge_triggered -cells] > registers.rpt
set ff_report [open ff_count.rpt w]
puts $ff_report "FF_COUNT [sizeof_collection [all_registers -edge_triggered -cells]]"
puts $ff_report "LATCH_COUNT [sizeof_collection [all_registers -level_sensitive -cells]]"
close $ff_report
check_timing > check_timing.rpt
write -format ddc -hierarchy -output mapped.ddc
puts SHARED_SCALAR_FP_ADD_PPA_COMPLETE
exit 0
'''
        (directory/'run.tcl').write_text(script)
        command = ['docker','exec','-u',f'{os.getuid()}:{os.getgid()}','-e',
                   'SNPSLMD_LICENSE_FILE=27000@t7920','-w',str(directory),original['container'],
                   original['dc_home']+'/bin/dc_shell-t','-64bit','-f','run.tcl']
        manifest['results'][mode] = {'state': 'PREPARED', 'parameter': value, 'command': command}
    manifest['frozen_files'] = {str(path): sha(path) for path in out.rglob('*') if path.is_file() and 'alib-52' not in path.parts}
    manifest['alib_cache'] = {'reference': str(ref/'backend/syn/ara_soc/v1-dc/run/alib-52'),
                              'files': {str(path.relative_to(out/'fma_add')): sha(path) for path in (out/'fma_add/alib-52').rglob('*') if path.is_file()}}
    def save():
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    save()
    print(str(out),flush=True)
    if not args.run:
        return
    for mode in ('fma_add','scalar_slices','shared_add'):
        for path, digest in {**dependencies, **manifest['frozen_files']}.items():
            assert sha(Path(path)) == digest, 'Changed prepared input: '+path
        entry = manifest['results'][mode]
        manifest['dc_started'] = True
        entry['state'] = 'RUNNING'
        save()
        logpath = out/mode/'console.log'
        with logpath.open('w') as log:
            completed = subprocess.run(entry['command'],stdout=log,stderr=subprocess.STDOUT)
        text = logpath.read_text(errors='replace')
        errors = re.findall(r'^.*(?:Error:|Fatal:|\bFAIL\b).*$',text,re.M)
        passed = completed.returncode == 0 and not errors and 'SHARED_SCALAR_FP_ADD_PPA_COMPLETE' in text.splitlines()
        entry.update(state='COMPLETE' if passed else 'FAILED', returncode=completed.returncode,
                     errors=errors, log_sha256=sha(logpath))
        save()
        if not passed:
            raise SystemExit('Failed: '+str(logpath))


if __name__ == '__main__':
    main()
