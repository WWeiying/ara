#!/usr/bin/env python3
"""Post-run source/image/raw-result audits of completed attention and route studies."""
import argparse
import json
from pathlib import Path
import sys

from audit import digest, require, verify_pins

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def collect_preparation(run, report, pins):
    from preparation_census import check
    require(report['state'] == 'ACTUAL_QWEN3_PREPARATION_ROUTES_PASS' and not report['performance_measured'] and
            report['library_objects_rebuilt'] == 0 and report['only_existing_trace_flags_changed'], 'Incomplete census')
    require(digest(run/'test') == report['elf_sha256'] and digest(run/'qemu.log') == report['log_sha256'],
            'Census output/ELF drift')
    measured = check((run/'qemu.log').read_text()); require(measured == report['measured'], 'Census replay differs')
    commands = [c for c in json.loads((run/'commands.json').read_text()) if c['label'] == 'qemu']
    require(len(commands) == 1, 'QEMU command inventory'); argv = commands[0]['argv']
    require(argv[argv.index('-initrd')+1] == str(run/'initramfs.cpio') and
            'xaraqbs=true' in argv[argv.index('-cpu')+1], 'Wrong observed model execution')
    sys.path.insert(0,str(ROOT/'verification/qbs'))
    from run_ggml_segmented import verify_native_build
    for path in verify_native_build(Path(argv[0])):
        path = Path(path).resolve(strict=True)
        require(pins.get(str(path)) == digest(path), 'Native emulator provenance drift: '+str(path))
    return dict(model=measured['model'],per_mode=measured['per_mode'],measured_modes=measured['measured_modes'],
                all_route_rows_recomputed=True,native_emulator_postchecked=True,performance_measured=False)


def collect_gqa6(run, report, pins):
    from check_output_gqa6 import check
    from collect_matrix_soc import audit_build
    from run_output_native import s, accepted
    require(report['state'] == 'PASS' and report['performance_measured'] and report['independent_protocol_checked'] and
            report['post_pins_match'] and report['hardware_width'] == 1, 'Incomplete GQA6 run')
    build = Path(report['build']); program = json.loads((build/'build.json').read_text())
    require(program['state'] == 'GQA6_NATIVE_BUILT_NOT_EXECUTED' and
            pins.get(str(build/'build.json')) == digest(build/'build.json') and
            program['elf_sha256'] == report['elf_sha256'] == digest(program['elf']) and
            program['golden'] == report['golden'] and pins.get(str(Path(report['golden']))) == digest(report['golden']),
            'GQA6 build/golden identity')
    simv = Path(json.loads((run/'status.json').read_text())['simv']); soc = audit_build(simv.parent.parent)
    require(soc['wide'] == 1 and soc['image_pins'] == report['image_pins'] and
            s.hashes(s.image_files(simv)) == report['image_pins'], 'GQA6 actual image')
    measured = check((run/'work/run.vcs.log').read_text(),Path(report['golden']).read_bytes())
    require(measured == report['measured'], 'GQA6 raw replay differs')
    accepted.protocol(run/'work',report['elf_sha256'],report['image_pins'])
    return dict(measured=measured,performance_measured=True,protocol_reaudited=True,
                same_hardware_software_comparison=True,whole_model=False,
                log_sha256=digest(run/'work/run.vcs.log'),protocol_sha256=digest(run/'work/uvm_result.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',choices=('preparation','gqa6'),required=True)
    parser.add_argument('--run',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); run = args.run.resolve(strict=True); out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=False); result = dict(state='CHECKING',study=args.study)
    try:
        paths = [Path(__file__),HERE/'audit.py',run/'result.json',run/'source-pins.json',run/'status.json']
        paths.append(run/'commands.json' if args.study == 'preparation' else run/'work/run.vcs.log')
        audit_pins = {str(path):digest(path) for path in paths}
        report = json.loads((run/'result.json').read_text())
        require(digest(run/'source-pins.json') == report['source_pins_sha256'],'Pin-map drift')
        pins = json.loads((run/'source-pins.json').read_text()); checked = verify_pins(pins)
        measured = (collect_preparation if args.study == 'preparation' else collect_gqa6)(run,report,pins)
        for module in tuple(sys.modules.values()):
            path = getattr(module,'__file__',None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT):
                audit_pins[str(Path(path).resolve())] = digest(path)
        verify_pins(pins); verify_pins(audit_pins)
        result.update(state='PREPARATION_CENSUS_REAUDITED' if args.study == 'preparation' else 'GQA6_OUTPUT_CALL_REAUDITED',
                      run=str(run),checked=measured,checked_inputs=checked,
                      worker_result_sha256=digest(run/'result.json'),source_pins_sha256=digest(run/'source-pins.json'),
                      audit_pins=audit_pins,whole_model_hardware_performance=False,area_measured=False)
    except BaseException as exc: result.update(state='FAIL',error=repr(exc)); raise
    finally: (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__': main()
