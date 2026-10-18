#!/usr/bin/env python3
"""Matched exact-backend area ablations with frozen source and identical constraints."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--block', choices=['finalizer', 'accumulator'], default='finalizer')
    parser.add_argument('--accumulator-mechanism', choices=['update','normalize','both','representation','segments','direct-read','wide-segments'], default='update')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = root / 'hardware/build/synthesis/full_retry2'
    reference = json.loads((base / 'manifest.json').read_text())
    libraries = [x['path'] for x in reference['libraries']
                 if '/logic/' in x['path'] and x['path'].endswith('.db')]
    assert len(libraries) == 4
    module = 'fp32_exact_reduction_finalize' if args.block == 'finalizer' else 'fp32_exact_reduction_accum'
    source = out / (module + '.sv')
    shutil.copy2(root / 'hardware/src/lane' / source.name, source)
    manifest = {'scope': args.block + ' local ablation, no SoC timing claim',
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'libraries': libraries, 'accumulator_mechanism': args.accumulator_mechanism, 'results': {}}
    manifest['library_sha256'] = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in libraries}
    shutil.copy2(Path(__file__), out / 'runner.py')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for mode in (0, 1):
        directory = out / str(mode)
        directory.mkdir()
        cache = base / 'backend/syn/ara_soc/v1-dc/run/alib-52'
        if cache.is_dir():
            shutil.copytree(cache, directory / 'alib-52')
        if args.block == 'finalizer':
            parameters = f'SharedExtract={mode}'
            constraints = '''create_clock -name virtual_clk -period 1.0
set_clock_uncertainty .15 [get_clocks virtual_clk]
set_input_delay .1 -clock virtual_clk [all_inputs]
set_output_delay .1 -clock virtual_clk [all_outputs]
set_load .02 [all_outputs]
set_driving_cell -lib_cell BUFFD4BWP12T40P140 [all_inputs]'''
        else:
            parameters = f'ExponentSegmented=1,EmitRoundedResult=0,DeferSeed=1,SkipUnroundedRoundStage=1,SharedBeatUpdate={mode if args.accumulator_mechanism in ("update","both") else 0},SharedNormalize={mode if args.accumulator_mechanism in ("normalize","both") else 0}'
            if args.accumulator_mechanism == 'representation':
                # Same numeric/protocol contract and current area refinements;
                # change only four temporal banks vs exponent-local bins.
                parameters = f'ExponentSegmented={mode},EmitRoundedResult=0,DeferSeed=1,SkipUnroundedRoundStage=1,SharedBeatUpdate=0,SharedNormalize=1,CollisionForwardUpdate=1'
            if args.accumulator_mechanism == 'segments':
                parameters = f'ExponentSegmented=1,CompactSegments={mode},EmitRoundedResult=0,DeferSeed=1,SkipUnroundedRoundStage=1,SharedBeatUpdate=0,SharedNormalize=1,CollisionForwardUpdate=1'
            if args.accumulator_mechanism == 'direct-read':
                parameters = f'ExponentSegmented=1,CompactSegments=1,EmitRoundedResult=0,DeferSeed=1,SkipUnroundedRoundStage=1,SharedBeatUpdate=0,SharedNormalize=1,CollisionForwardUpdate=1,DirectBinRead={mode}'
            if args.accumulator_mechanism == 'wide-segments':
                parameters = f'ExponentSegmented=1,CompactSegments=1,EmitRoundedResult=0,DeferSeed=1,SkipUnroundedRoundStage=1,SharedBeatUpdate=0,SharedNormalize=1,CollisionForwardUpdate=1,DirectBinRead=0,WideSegments={mode}'
            constraints = '''create_clock -period 1.0 [get_ports clk_i]
set_clock_uncertainty .15 [get_clocks clk_i]
set_false_path -from [get_ports rst_ni]
set_input_delay .1 -clock clk_i [remove_from_collection [all_inputs] [get_ports {clk_i rst_ni}]]
set_output_delay .1 -clock clk_i [all_outputs]
set_load .02 [all_outputs]
set_driving_cell -lib_cell BUFFD4BWP12T40P140 [remove_from_collection [all_inputs] [get_ports {clk_i rst_ni}]]'''
        script = f'''set_app_var target_library {{{' '.join(libraries)}}}
set_app_var synthetic_library {{dw_foundation.sldb}}
set_app_var search_path [concat $search_path {{{reference['dc_home']}/libraries/syn}}]
set_app_var link_library [concat * $target_library $synthetic_library]
define_design_lib WORK -path ./work
set_host_options -max_cores 4
set compile_register_replication false
set compile_enable_register_merging false
{'set compile_seqmap_propagate_constants false' if args.accumulator_mechanism in ('direct-read', 'wide-segments') else ''}
if {{![analyze -format sverilog -define SYNTHESIS {{{source}}}]}} {{exit 1}}
if {{![elaborate {module} -parameters {parameters}]}} {{exit 1}}
current_design [get_designs {module}*]
if {{![link]}} {{exit 1}}
{constraints}
if {{![compile_ultra -no_autoungroup -no_seq_output_inversion]}} {{exit 1}}
report_area -hierarchy > area.rpt
report_qor > qor.rpt
report_timing -max_paths 10 -significant_digits 6 > timing.rpt
check_timing > check_timing.rpt
write -format ddc -hierarchy -output mapped.ddc
puts FINALIZE_PPA_COMPLETE
exit 0
'''
        (directory / 'run.tcl').write_text(script)
        manifest['results'][str(mode)] = {'state': 'RUNNING', 'parameters': parameters,
            'script_sha256': hashlib.sha256(script.encode()).hexdigest()}
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        cmd = ['docker', 'exec', '-u', f'{os.getuid()}:{os.getgid()}',
               '-e', 'SNPSLMD_LICENSE_FILE=27000@t7920', '-w', str(directory),
               reference['container'], reference['dc_home'] + '/bin/dc_shell-t',
               '-64bit', '-f', 'run.tcl']
        with (directory / 'console.log').open('w') as log:
            result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
        log = (directory / 'console.log').read_text()
        ok = result.returncode == 0 and 'FINALIZE_PPA_COMPLETE' in log.splitlines() and not re.search(r'^Error:', log, re.M)
        manifest['results'][str(mode)].update({'state': 'COMPLETE' if ok else 'FAILED',
            'returncode': result.returncode, 'complete': ok,
            'log_sha256': hashlib.sha256((directory / 'console.log').read_bytes()).hexdigest()})
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if not ok:
            raise SystemExit(f'Failed mode {mode}')
        print(f'Completed mode {mode}', flush=True)


if __name__ == '__main__':
    main()
