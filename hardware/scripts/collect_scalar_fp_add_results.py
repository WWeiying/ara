#!/usr/bin/env python3
"""Collect only completed, hash-verified matched local ADD synthesis evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re


NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_hash(path, expected):
    if not path.is_file() or sha(path) != expected:
        raise ValueError('Missing or changed frozen artifact: ' + str(path))


def values(text, label):
    return [float(value) for value in re.findall(re.escape(label)+r'\s*:\s*('+NUMBER+r')', text)]


def number(text, label):
    found = values(text, label)
    if not found:
        raise ValueError('Missing numeric report field: '+label)
    return found[0]


def total(text, label):
    found = values(text,label)
    if not found:
        raise ValueError('Missing numeric report field: '+label)
    return sum(found)


def slack(text):
    found = re.findall(r'slack\s+\((?:MET|VIOLATED)\)\s+('+NUMBER+r')', text)
    if not found:
        raise ValueError('No actual timing paths/slacks reported')
    return min(map(float, found))


def collect(directory):
    manifest = json.loads((directory/'manifest.json').read_text())
    mode_set = set(manifest['results'])
    if mode_set == {'fma_add','scalar_add'}:
        modes, parameter, marker, nominal = ('fma_add','scalar_add'), 'UseScalar', 'SCALAR_FP_ADD_PPA_COMPLETE', 360
    elif mode_set == {'fma_add','scalar_slices','shared_add'}:
        modes, parameter, marker, nominal = ('fma_add','scalar_slices','shared_add'), 'Mode', 'SHARED_SCALAR_FP_ADD_PPA_COMPLETE', 203
    else:
        raise ValueError('Unsupported or incomplete matched mode set: '+repr(mode_set))
    for mode in modes:
        entry = manifest['results'][mode]
        if entry.get('state') != 'COMPLETE' or entry.get('returncode') != 0 or entry.get('errors'):
            raise ValueError(mode+' has not completed successfully: '+entry.get('state','missing state'))
    dependencies = manifest.get('dependencies')
    frozen = manifest.get('frozen_files')
    if not isinstance(dependencies,dict) or not dependencies or not isinstance(frozen,dict) or not frozen:
        raise ValueError('Missing frozen source/include/filelist/script hashes')
    for path, digest in {**dependencies,**frozen}.items():
        require_hash(Path(path),digest)
    reference = Path(manifest['reference'])
    require_hash(reference/'manifest.json',manifest['reference_manifest_sha256'])
    original = json.loads((directory/'reference_manifest.json').read_text())
    require_hash(directory/'reference_manifest.json',manifest['reference_manifest_sha256'])
    original_libraries = {entry['path']:entry['sha256'] for entry in original['libraries']}
    library_hashes = {}
    for entry in manifest['libraries']:
        if original_libraries.get(entry['path']) != entry['sha256']:
            raise ValueError('Library differs from frozen reference: '+entry['path'])
        require_hash(Path(entry['path']),entry['sha256'])
        library_hashes[entry['path']] = entry['sha256']
    if len(library_hashes) != 4:
        raise ValueError('Expected the four matched standard-cell libraries')
    # Also validate the synthetic DesignWare library recorded by the reference.
    for path, digest in original_libraries.items():
        if path.endswith('dw_foundation.sldb'):
            require_hash(Path(path),digest)
            library_hashes[path] = digest
    scripts, filelists, rows = [], [], []
    required_reports = ('area.rpt','qor.rpt','timing.rpt','register_timing.rpt','hold.rpt',
                        'ff_count.rpt','registers.rpt','check_design_before.rpt',
                        'check_design_after.rpt','check_timing.rpt')
    for index,mode in enumerate(modes):
        run = directory/mode
        entry = manifest['results'][mode]
        for artifact in ('filelist','run.tcl'):
            if str(run/artifact) not in frozen:
                raise ValueError('Missing frozen '+artifact+' hash for '+mode)
        script = (run/'run.tcl').read_text()
        selectors = re.findall(r'-parameters\s+([A-Za-z_]\w*=\d+)',script)
        if selectors != [f'{parameter}={index}'] or entry['parameter'] != index:
            raise ValueError('Unexpected candidate parameter: '+repr(selectors))
        scripts.append(script.replace(str(run),'RUN_DIR').replace(f'{parameter}={index}',f'{parameter}=MODE'))
        filelist = (run/'filelist').read_text()
        filelists.append(filelist)
        for line in filelist.splitlines():
            path = Path(line)
            if path.is_absolute() and (str(path) not in dependencies or not path.is_file()):
                raise ValueError('Unhashed or missing filelist source: '+line)
        require_hash(run/'console.log',entry['log_sha256'])
        log = (run/'console.log').read_text(errors='replace')
        if marker not in log.splitlines() or re.search(r'^.*(?:Error:|Fatal:|\bFAIL\b).*$',log,re.M):
            raise ValueError('Missing completion marker or tool error: '+mode)
        report_text = {}
        for name in required_reports:
            path = run/name
            if not path.is_file() or not path.stat().st_size:
                raise ValueError('Missing/empty required report: '+str(path))
            report_text[name] = path.read_text(errors='replace')
        if not (run/'mapped.ddc').is_file() or not (run/'mapped.ddc').stat().st_size:
            raise ValueError('Missing mapped design: '+mode)
        area,qor = report_text['area.rpt'],report_text['qor.rpt']
        ff_text = report_text['ff_count.rpt']
        ff = re.findall(r'^FF_COUNT (\d+)$',ff_text,re.M)
        latch = re.findall(r'^LATCH_COUNT (\d+)$',ff_text,re.M)
        if len(ff)!=1 or len(latch)!=1:
            raise ValueError('Missing actual FF/LATCH counts: '+mode)
        if int(latch[0]):
            raise ValueError('Unexpected inferred latches: '+mode)
        row = {'mode':mode,'cell_area':number(area,'Total cell area'),
               'combinational_area':number(area,'Combinational area'),
               'sequential_area':number(area,'Noncombinational area'),
               'qor_cell_area':number(qor,'Cell Area'),
               'qor_sequential_cells':number(qor,'Sequential Cell Count'),
               'ff_count':int(ff[0]),'latch_count':int(latch[0]),
               'nominal_boundary_register_bits':nominal,
               'ff_count_matches_nominal':int(ff[0])==nominal,
               'worst_setup_slack_ns':slack(report_text['timing.rpt']),
               'worst_register_setup_slack_ns':slack(report_text['register_timing.rpt']),
               'worst_hold_slack_ns':slack(report_text['hold.rpt']),
               'setup_tns_ns':total(qor,'Total Negative Slack'),
               'setup_violating_paths':total(qor,'No. of Violating Paths'),
               'qor_worst_hold_violation_ns':number(qor,'Worst Hold Violation'),
               'hold_violating_paths':number(qor,'No. of Hold Violations'),
               'report_sha256':{name:sha(run/name) for name in required_reports+('run.tcl','filelist','console.log','mapped.ddc')}}
        if abs(row['cell_area']-row['qor_cell_area'])>max(.02,row['cell_area']*1e-4):
            raise ValueError('Area and QoR disagree: '+mode)
        rows.append(row)
    if len(set(scripts)) != 1 or len(set(filelists)) != 1:
        raise ValueError('Tcl/filelists differ beyond candidate selector and run directory')
    for row in rows[1:]:
        row['local_area_saved_vs_fma'] = rows[0]['cell_area']-row['cell_area']
        row['local_area_saved_percent_vs_fma'] = 100*(1-row['cell_area']/rows[0]['cell_area'])
    return {'directory':str(directory),'scope':manifest['scope'],'contract':manifest['contract'],
            'constraints':manifest['constraints'],'matched_scope':True,'constraints_match':True,
            'all_frozen_hashes_verified':True,'library_sha256':library_hashes,
            'manifest_sha256':sha(directory/'manifest.json'),'results':rows,
            'ff_counts_match_between_modes':len({row['ff_count'] for row in rows})==1,
            'interpretation':'Local registered arithmetic synthesis only. No multiplication by Lane count, no SoC area/Fmax claim. Any removed boundary register requires inspection of constant output bits.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories',nargs='+',type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args = parser.parse_args()
    try:
        reports = [collect(directory.resolve()) for directory in args.directories]
    except (ValueError,KeyError,OSError) as exc:
        raise SystemExit('REFUSED: '+str(exc))
    with args.out.open('x') as output:
        json.dump(reports,output,indent=2)
        output.write('\n')
    for report in reports:
        print(report['directory'])
        for row in report['results']:
            print(f"  {row['mode']}: area={row['cell_area']:.4f} comb={row['combinational_area']:.4f} seq={row['sequential_area']:.4f} FF={row['ff_count']} latch={row['latch_count']} setup={row['worst_setup_slack_ns']:.6f} hold={row['worst_hold_slack_ns']:.6f}")


if __name__ == '__main__':
    main()
